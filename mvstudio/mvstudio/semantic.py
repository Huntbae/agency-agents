"""Semantic image-to-song matching (Phase 2b).

Uses a local Ollama server: a vision model describes each photo (caption/
tags/mood), then a text model assigns photos to song sections — matching
lyric lines and section energy — and EXCLUDES photos unrelated to the song.
This is what stops random screenshots from ending up in the video.

Defaults: vision "qwen3-vl:8b", text "qwen3:8b" (both Apache-2.0).
Everything degrades gracefully: callers catch SemanticUnavailable and fall
back to energy-based matching with a warning.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.request
from typing import Any

OLLAMA_URL = "http://localhost:11434"
DEFAULT_VISION_MODEL = "qwen3-vl:8b"
DEFAULT_TEXT_MODEL = "qwen3:8b"

# An image must land in at least one section pool to be used; models are
# asked to exclude anything unrelated to the song's story/mood.
_VISION_PROMPT = (
    'Describe this photo for music-video editing. Reply with JSON only: '
    '{"caption": "<one short sentence>", "tags": ["<5-10 short tags>"], '
    '"mood": "<one word>"}')


class SemanticUnavailable(RuntimeError):
    pass


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _chat(model: str, messages: list[dict[str, Any]],
          timeout: float = 600.0) -> str:
    payload = {"model": model, "stream": False, "format": "json",
               "messages": messages, "options": {"temperature": 0.2}}
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["message"]["content"]


def check_available(vision_model: str, text_model: str) -> None:
    """Raise SemanticUnavailable with actionable instructions unless Ollama
    is running and both models are pulled."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        raise SemanticUnavailable(
            "Ollama is not running. Install & start it:\n"
            "  brew install ollama && brew services start ollama\n"
            f"  ollama pull {vision_model} && ollama pull {text_model}")
    missing = [m for m in (vision_model, text_model)
               if not any(n == m or n.startswith(m + ":") or m.startswith(n.split(":")[0])
                          and n.split(":")[0] == m.split(":")[0] for n in names)]
    if missing:
        raise SemanticUnavailable(
            "Missing Ollama model(s): " + ", ".join(missing) + "\n"
            + "".join(f"  ollama pull {m}\n" for m in missing))


def _encode_image(path: str, max_side: int = 512) -> str:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def describe_images(images: list[dict[str, Any]],
                    vision_model: str = DEFAULT_VISION_MODEL) -> int:
    """Add caption/tags/mood to each image record in place. Returns the
    number successfully described; records that fail keep working via
    their vibrance stats."""
    done = 0
    for i, rec in enumerate(images):
        try:
            content = _chat(vision_model, [{
                "role": "user", "content": _VISION_PROMPT,
                "images": [_encode_image(rec["path"])],
            }])
            data = json.loads(content)
            rec["caption"] = str(data.get("caption", ""))[:300]
            rec["tags"] = [str(t) for t in data.get("tags", [])][:10]
            rec["mood"] = str(data.get("mood", ""))[:40]
            done += 1
            _log(f"[mvstudio] image {i + 1}/{len(images)}: {rec['caption'][:60]}")
        except Exception as exc:
            _log(f"[mvstudio] vision failed for {rec['path']}: {exc}")
    if done == 0:
        raise SemanticUnavailable("vision model produced no descriptions")
    return done


def _section_briefs(analysis: dict[str, Any],
                    lyrics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    briefs = []
    for i, s in enumerate(analysis["sections"]):
        lines = [ln["text"] for ln in (lyrics or [])
                 if s["start"] <= ln["start"] < s["end"]]
        briefs.append({"index": i, "energy": s["energy"], "label": s["label"],
                       "lyrics": lines[:8]})
    return briefs


_MATCH_PROMPT = """You are a music video director choosing which photos fit a song.
Given song sections (with energy and lyric lines) and photos (with captions/tags),
reply with JSON only:
{"exclude": [<indices of photos UNRELATED to the song's story, mood or lyrics —
screenshots, documents, unrelated random photos>],
 "sections": [{"index": <section index>, "images": [<photo indices that fit this
section, best first, 3-8 items>]}]}
Every section must get at least one image. Prefer matching lyric meaning; break
ties with mood/energy (bright energetic photos -> high-energy sections)."""


def match_images(analysis: dict[str, Any], images: list[dict[str, Any]],
                 lyrics: list[dict[str, Any]] | None,
                 text_model: str = DEFAULT_TEXT_MODEL,
                 ) -> tuple[list[list[str]], list[str]]:
    """Return (pools, excluded): pools[i] = ordered image paths for section i;
    excluded = paths judged unrelated to the song. Output is sanitized —
    a confused model can degrade ranking but never empty the video."""
    brief = {
        "song": {"bpm": analysis["bpm"], "duration": analysis["duration"]},
        "sections": _section_briefs(analysis, lyrics),
        "photos": [{"index": i, "caption": r.get("caption", ""),
                    "tags": r.get("tags", []), "mood": r.get("mood", ""),
                    "brightness": r["brightness"]}
                   for i, r in enumerate(images)],
    }
    raw = json.loads(_chat(text_model, [
        {"role": "system", "content": _MATCH_PROMPT},
        {"role": "user", "content": json.dumps(brief, ensure_ascii=False)},
    ]))

    n = len(images)
    excluded_idx = {i for i in raw.get("exclude", [])
                    if isinstance(i, int) and 0 <= i < n}
    if len(excluded_idx) >= n:  # refuse to exclude everything
        excluded_idx = set()

    allowed = [i for i in range(n) if i not in excluded_idx]
    by_section: dict[int, list[int]] = {}
    for entry in raw.get("sections", []):
        try:
            si = int(entry["index"])
            imgs = [i for i in entry.get("images", [])
                    if isinstance(i, int) and 0 <= i < n and i not in excluded_idx]
        except (KeyError, TypeError, ValueError):
            continue
        if imgs:
            by_section[si] = list(dict.fromkeys(imgs))

    pools = []
    for i in range(len(analysis["sections"])):
        idxs = by_section.get(i) or allowed
        pools.append([images[j]["path"] for j in idxs])
    excluded = [images[j]["path"] for j in sorted(excluded_idx)]
    return pools, excluded


def semantic_match(analysis: dict[str, Any], images: list[dict[str, Any]],
                   lyrics: list[dict[str, Any]] | None,
                   vision_model: str = DEFAULT_VISION_MODEL,
                   text_model: str = DEFAULT_TEXT_MODEL,
                   ) -> tuple[list[list[str]], list[str]]:
    """Full pipeline: availability check -> describe -> match."""
    check_available(vision_model, text_model)
    described = describe_images(images, vision_model)
    _log(f"[mvstudio] described {described}/{len(images)} images")
    return match_images(analysis, images, lyrics, text_model)

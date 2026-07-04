"""Directors: turn (analysis, image pool) into a storyboard.

Two directors share one output contract (the storyboard schema):

- rule:   deterministic, seedable, always available. Cut length follows
          section energy (high energy -> short beat-multiples), images are
          matched to sections by vibrance, presets by energy affinity.
- ollama: optional local LLM (e.g. qwen3) proposes the storyboard; its
          output is advisory and passes through the same sanitizer, so a
          bad model can degrade quality but never break a render.
"""

from __future__ import annotations

import json
import random
import sys
import urllib.request
from typing import Any

from . import __version__
from .presets import pick_preset
from .schema import MIN_CUT_SECONDS, SCHEMA_VERSION, validate_storyboard

# Beats per cut by section label; the rule director occasionally doubles
# the length for variety so cuts don't feel metronomic.
_BEATS_PER_CUT = {"high": 2, "mid": 4, "low": 8}

OLLAMA_URL = "http://localhost:11434/api/chat"


def make_storyboard(analysis: dict[str, Any], images: list[dict[str, Any]],
                    presets: dict[str, dict[str, Any]],
                    width: int = 1920, height: int = 1080, fps: int = 30,
                    seed: int = 42, director: str = "rule",
                    model: str = "qwen3:8b") -> dict[str, Any]:
    if director == "rule":
        cuts, name = _rule_cuts(analysis, images, presets, seed), "rule"
    elif director == "ollama":
        cuts, name = _ollama_cuts(analysis, images, presets, seed, model)
    else:
        raise ValueError(f"unknown director: {director!r}")

    sb = {
        "version": SCHEMA_VERSION,
        "meta": {"director": name, "seed": seed, "engine": f"mvstudio/{__version__}"},
        "audio": {"path": analysis["path"], "duration": analysis["duration"],
                  "bpm": analysis["bpm"]},
        "output": {"width": width, "height": height, "fps": fps},
        "sections": analysis["sections"],
        "cuts": cuts,
    }
    return validate_storyboard(sb, known_presets=set(presets))


# ---------------------------------------------------------------- rule

def _rule_cuts(analysis: dict[str, Any], images: list[dict[str, Any]],
               presets: dict[str, dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    duration = analysis["duration"]
    beats = [b for b in analysis["beats"] if 0.0 <= b < duration]

    # Rank images by vibrance; each section draws from the slice of the
    # ranking that matches its energy, so bright/colorful images land on
    # choruses and muted ones on quiet parts.
    ranked = sorted(images, key=lambda r: r["vibrance"])
    n = len(ranked)

    cuts: list[dict[str, Any]] = []
    last_image: str | None = None
    last_preset: str | None = None

    for section in analysis["sections"]:
        s_beats = [b for b in beats if section["start"] <= b < section["end"]]
        grid = sorted(set([section["start"]] + s_beats))
        step = _BEATS_PER_CUT.get(section["label"], 4)

        center = section["energy"] * (n - 1)
        spread = max(2, n // 2)
        pool = [ranked[int(min(max(center + off, 0), n - 1))]
                for off in range(-spread, spread + 1)]
        pool_paths = list(dict.fromkeys(r["path"] for r in pool))

        i = 0
        while i < len(grid):
            start = grid[i]
            hop = step * 2 if rng.random() < 0.2 else step  # occasional long hold
            j = i + hop
            end = grid[j] if j < len(grid) else section["end"]
            if section["end"] - end < MIN_CUT_SECONDS:
                end = section["end"]

            choices = [p for p in pool_paths if p != last_image] or pool_paths
            image = rng.choice(choices)
            preset = pick_preset(presets, section["energy"], rng, avoid=last_preset)

            cuts.append({"start": round(start, 3), "end": round(end, 3),
                         "image": image, "preset": preset})
            last_image, last_preset = image, preset
            if end >= section["end"]:
                break
            i = j
        else:
            # Grid exhausted before reaching the section end: extend the tail.
            if cuts and cuts[-1]["end"] < section["end"]:
                cuts[-1]["end"] = round(section["end"], 3)

    return _sanitize_cuts(cuts, duration)


# ---------------------------------------------------------------- ollama

_SYSTEM_PROMPT = """You are a music video director. Given song analysis and an
image pool, output ONLY a JSON object: {"cuts": [{"start": <sec>, "end": <sec>,
"image_index": <int>, "preset": "<preset id>"}]}.
Rules: cuts must be contiguous from 0 to the song duration; cut boundaries
should land on the provided beat times; short cuts (1-2 beats) for high-energy
sections, long cuts (4-8 beats) for calm sections; never repeat the same image
in adjacent cuts; pick presets whose feel matches the section energy.
No prose, no markdown fences — JSON only."""


def _ollama_cuts(analysis: dict[str, Any], images: list[dict[str, Any]],
                 presets: dict[str, dict[str, Any]], seed: int,
                 model: str) -> tuple[list[dict[str, Any]], str]:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "duration": analysis["duration"],
                "bpm": analysis["bpm"],
                "beats": analysis["beats"],
                "sections": analysis["sections"],
                "presets": [{"id": p["id"], "energy": p["energy"]}
                            for p in presets.values()],
                "images": [{"index": i, "brightness": r["brightness"],
                            "colorfulness": r["colorfulness"]}
                           for i, r in enumerate(images)],
            })},
        ],
        "options": {"temperature": 0.4, "seed": seed},
    }
    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            content = json.loads(resp.read())["message"]["content"]
        raw = json.loads(content)["cuts"]
        cuts = []
        for c in raw:
            idx = int(c["image_index"]) % len(images)
            preset = c.get("preset") if c.get("preset") in presets else None
            cuts.append({"start": float(c["start"]), "end": float(c["end"]),
                         "image": images[idx]["path"],
                         "preset": preset or sorted(presets)[0]})
        cuts = _snap_to_beats(cuts, analysis["beats"], analysis["duration"])
        cuts = _sanitize_cuts(cuts, analysis["duration"])
        if not cuts:
            raise ValueError("LLM produced no usable cuts")
        return cuts, f"ollama:{model}"
    except Exception as exc:  # any failure degrades to the rule director
        print(f"[mvstudio] ollama director failed ({exc}); falling back to "
              "rule director", file=sys.stderr, flush=True)
        return _rule_cuts(analysis, images, presets, seed), "rule(fallback)"


# ---------------------------------------------------------------- sanitizer

def _snap_to_beats(cuts: list[dict[str, Any]], beats: list[float],
                   duration: float) -> list[dict[str, Any]]:
    if not beats:
        return cuts

    def snap(t: float) -> float:
        return min(beats, key=lambda b: abs(b - t)) if 0 < t < duration else t

    for c in cuts:
        c["start"], c["end"] = snap(c["start"]), snap(c["end"])
    return cuts


def _sanitize_cuts(cuts: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    """Force contiguity/coverage so the storyboard always validates."""
    cuts = sorted((c for c in cuts if c["end"] > c["start"]),
                  key=lambda c: c["start"])
    fixed: list[dict[str, Any]] = []
    cursor = 0.0
    for c in cuts:
        if cursor >= duration:
            break
        start = cursor
        end = min(max(c["end"], start + MIN_CUT_SECONDS), duration)
        if fixed and end - start < MIN_CUT_SECONDS:
            fixed[-1]["end"] = round(end, 3)  # merge slivers into the previous cut
        else:
            fixed.append({**c, "start": round(start, 3), "end": round(end, 3)})
        cursor = end
    if fixed:
        if duration - fixed[-1]["end"] >= MIN_CUT_SECONDS:
            last = fixed[-1]
            fixed.append({**last, "start": last["end"], "end": round(duration, 3)})
        else:
            fixed[-1]["end"] = round(duration, 3)
    return fixed

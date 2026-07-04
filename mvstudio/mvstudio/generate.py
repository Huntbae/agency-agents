"""Lyrics-to-visuals generation (Phase 2b-2).

Turns the song's sections and lyric lines into visual scene prompts, then
generates images locally with FLUX.2-klein-4B (Apache-2.0) via mflux
(MIT, Apple Silicon). Because each image is generated FOR a specific
section, the section pools are exact — no matching heuristics involved.
This is the mode that makes "visuals that fit the lyrics" true even when
the user supplies no photos.

Prompt building prefers a local Ollama text model; without it, a template
fallback still produces usable prompts offline. The mflux call itself is a
thin wrapper (same pattern as transcribe/semantic): install with
`pip install "mvstudio[gen]"` and verify on a real Apple Silicon machine.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

DEFAULT_GEN_MODEL = "flux2-klein-4b"
DEFAULT_STYLE = "cinematic music video still, film grain, atmospheric lighting"

_MOOD_BY_LABEL = {
    "low": "calm, moody, soft light, muted colors",
    "mid": "warm, steady, golden hour tones",
    "high": "energetic, vivid, dramatic light, saturated colors",
}

_PROMPT_SYSTEM = """You write image-generation prompts for a music video.
Given song sections (energy label + lyric lines) and a style, reply JSON only:
{"sections": [{"index": <i>, "prompts": ["<prompt>", ...]}]}
Write {per_section} English prompts per section. Each prompt describes ONE
concrete visual scene (place, subject, light, camera feel) that expresses the
lyric meaning and the section's energy. No text/typography in the scene.
Keep the given style consistent across all prompts."""


class GenerationUnavailable(RuntimeError):
    pass


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------ prompts

def build_scene_prompts(analysis: dict[str, Any],
                        lyrics: list[dict[str, Any]] | None,
                        style: str = DEFAULT_STYLE,
                        per_section: int = 3,
                        text_model: str | None = "qwen3:8b",
                        ) -> list[list[str]]:
    """prompts[i] = image prompts for section i. Tries the local LLM first,
    falls back to deterministic templates so this works with no models."""
    if text_model:
        try:
            return _llm_prompts(analysis, lyrics, style, per_section, text_model)
        except Exception as exc:
            _log(f"[mvstudio] LLM prompt writer unavailable ({exc}); "
                 "using template prompts")
    return _template_prompts(analysis, lyrics, style, per_section)


def _section_lyrics(analysis: dict[str, Any],
                    lyrics: list[dict[str, Any]] | None) -> list[list[str]]:
    out = []
    for s in analysis["sections"]:
        out.append([ln["text"] for ln in (lyrics or [])
                    if s["start"] <= ln["start"] < s["end"]])
    return out


def _template_prompts(analysis: dict[str, Any],
                      lyrics: list[dict[str, Any]] | None,
                      style: str, per_section: int) -> list[list[str]]:
    per_lyrics = _section_lyrics(analysis, lyrics)
    prompts = []
    for section, lines in zip(analysis["sections"], per_lyrics):
        mood = _MOOD_BY_LABEL.get(section.get("label", "mid"), _MOOD_BY_LABEL["mid"])
        base = [f'scene expressing the lyric "{line}"' for line in lines]
        if not base:
            base = [f"abstract scene for a {section.get('label', 'mid')}-energy "
                    "instrumental passage"]
        # cycle lyric lines until we have enough prompts, varying the shot
        shots = ["wide establishing shot", "intimate close-up", "slow motion detail",
                 "aerial view", "silhouette against the light"]
        prompts.append([f"{style}, {mood}, {shots[k % len(shots)]}, "
                        f"{base[k % len(base)]}, no text"
                        for k in range(per_section)])
    return prompts


def _llm_prompts(analysis: dict[str, Any], lyrics: list[dict[str, Any]] | None,
                 style: str, per_section: int, text_model: str) -> list[list[str]]:
    from .semantic import _chat  # same local Ollama transport
    per_lyrics = _section_lyrics(analysis, lyrics)
    brief = {
        "style": style,
        "sections": [{"index": i, "label": s.get("label", "mid"),
                      "energy": s["energy"], "lyrics": lines[:8]}
                     for i, (s, lines) in enumerate(
                         zip(analysis["sections"], per_lyrics))],
    }
    raw = json.loads(_chat(text_model, [
        {"role": "system",
         "content": _PROMPT_SYSTEM.replace("{per_section}", str(per_section))},
        {"role": "user", "content": json.dumps(brief, ensure_ascii=False)},
    ]))
    fallback = _template_prompts(analysis, lyrics, style, per_section)
    prompts = list(fallback)
    for entry in raw.get("sections", []):
        try:
            i = int(entry["index"])
            got = [str(p) for p in entry.get("prompts", []) if str(p).strip()]
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < len(prompts) and got:
            prompts[i] = got[:per_section]
    return prompts


# ------------------------------------------------------------ generation

def _mflux_generator(gen_model: str, width: int, height: int
                     ) -> Callable[[str, int, str], None]:
    """Returns generate(prompt, seed, out_path). Thin mflux wrapper."""
    try:
        from mflux.models.flux2.variants import Flux2Klein
        try:
            from mflux import ModelConfig
        except ImportError:
            from mflux.config.model_config import ModelConfig
    except ImportError:
        raise GenerationUnavailable(
            "mflux not installed (Apple Silicon required). Run:\n"
            "  pip install 'mvstudio[gen]'\n"
            "First generation downloads FLUX.2-klein-4B (~9GB).")

    config = (ModelConfig.flux2_klein_4b() if "4b" in gen_model
              else ModelConfig.flux2_klein_9b())
    try:
        model = Flux2Klein(model_config=config, quantize=8)
    except TypeError:
        model = Flux2Klein(model_config=config)

    def generate(prompt: str, seed: int, out_path: str) -> None:
        image = model.generate_image(seed=seed, prompt=prompt,
                                     num_inference_steps=4,
                                     width=width, height=height)
        image.save(out_path)

    return generate


def generate_visuals(analysis: dict[str, Any],
                     lyrics: list[dict[str, Any]] | None,
                     outdir: str,
                     style: str = DEFAULT_STYLE,
                     per_section: int = 3,
                     gen_model: str = DEFAULT_GEN_MODEL,
                     text_model: str | None = "qwen3:8b",
                     width: int = 1280, height: int = 720,
                     seed: int = 42,
                     generator: Callable[[str, int, str], None] | None = None,
                     ) -> tuple[str, list[list[str]]]:
    """Generate per-section images into outdir. Returns (outdir, pools)
    where pools[i] = generated image paths for section i (exact, no
    matching needed). `generator` is injectable for tests."""
    prompts = build_scene_prompts(analysis, lyrics, style, per_section, text_model)
    os.makedirs(outdir, exist_ok=True)
    if generator is None:
        generator = _mflux_generator(gen_model, width, height)

    total = sum(len(p) for p in prompts)
    pools: list[list[str]] = []
    done = 0
    for i, section_prompts in enumerate(prompts):
        pool = []
        for j, prompt in enumerate(section_prompts):
            path = os.path.join(outdir, f"s{i:02d}_{j}.png")
            done += 1
            _log(f"[mvstudio] generating image {done}/{total} "
                 f"(section {i}): {prompt[:70]}...")
            generator(prompt, seed + i * 100 + j, path)
            pool.append(path)
        pools.append(pool)

    with open(os.path.join(outdir, "prompts.json"), "w", encoding="utf-8") as f:
        json.dump({"style": style,
                   "sections": [{"index": i, "prompts": p, "images": pools[i]}
                                for i, p in enumerate(prompts)]},
                  f, ensure_ascii=False, indent=2)
    return outdir, pools

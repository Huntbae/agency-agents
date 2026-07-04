"""Storyboard JSON schema and validation.

The storyboard is the single contract between directors (rule-based, LLM)
and the deterministic renderer. Directors may be swapped freely; anything
that passes ``validate_storyboard`` must render identically.

Schema (version 1):

{
  "version": 1,
  "meta":    {"director": "rule", "seed": 42},
  "audio":   {"path": "song.wav", "duration": 212.3, "bpm": 120.0},
  "output":  {"width": 1920, "height": 1080, "fps": 30},
  "sections":[{"start": 0.0, "end": 31.2, "energy": 0.71, "label": "high"}],
  "cuts": [
    {"start": 0.0, "end": 2.0, "image": "imgs/a.jpg", "preset": "zoom_in"}
  ]
}

Cuts must be contiguous, start at 0, and end at audio.duration.
"""

from __future__ import annotations

import json
import os
from typing import Any

SCHEMA_VERSION = 1

# Cut boundaries are considered aligned when within this many seconds.
TIME_EPS = 0.02

MIN_CUT_SECONDS = 0.25


class StoryboardError(ValueError):
    pass


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise StoryboardError(msg)


def validate_storyboard(sb: dict[str, Any], known_presets: set[str] | None = None,
                        check_files: bool = True) -> dict[str, Any]:
    """Validate a storyboard dict. Returns it unchanged on success."""
    _require(isinstance(sb, dict), "storyboard must be an object")
    _require(sb.get("version") == SCHEMA_VERSION,
             f"unsupported storyboard version: {sb.get('version')!r}")

    audio = sb.get("audio") or {}
    _require(isinstance(audio.get("path"), str) and audio["path"],
             "audio.path is required")
    duration = audio.get("duration")
    _require(isinstance(duration, (int, float)) and duration > 0,
             "audio.duration must be a positive number")
    if check_files:
        _require(os.path.isfile(audio["path"]),
                 f"audio file not found: {audio['path']}")

    out = sb.get("output") or {}
    for key in ("width", "height", "fps"):
        _require(isinstance(out.get(key), int) and out[key] > 0,
                 f"output.{key} must be a positive integer")
    _require(out["width"] % 2 == 0 and out["height"] % 2 == 0,
             "output.width/height must be even (yuv420p)")

    cuts = sb.get("cuts")
    _require(isinstance(cuts, list) and len(cuts) > 0,
             "cuts must be a non-empty list")

    prev_end = 0.0
    for i, cut in enumerate(cuts):
        _require(isinstance(cut, dict), f"cuts[{i}] must be an object")
        start, end = cut.get("start"), cut.get("end")
        _require(isinstance(start, (int, float)) and isinstance(end, (int, float)),
                 f"cuts[{i}] start/end must be numbers")
        _require(end - start >= MIN_CUT_SECONDS - TIME_EPS,
                 f"cuts[{i}] shorter than {MIN_CUT_SECONDS}s: {start}..{end}")
        _require(abs(start - prev_end) <= TIME_EPS,
                 f"cuts[{i}] not contiguous: starts at {start}, previous ended {prev_end}")
        _require(isinstance(cut.get("image"), str) and cut["image"],
                 f"cuts[{i}].image is required")
        if check_files:
            _require(os.path.isfile(cut["image"]),
                     f"cuts[{i}] image not found: {cut['image']}")
        preset = cut.get("preset")
        _require(isinstance(preset, str) and preset, f"cuts[{i}].preset is required")
        if known_presets is not None:
            _require(preset in known_presets,
                     f"cuts[{i}] unknown preset: {preset!r}")
        prev_end = end

    _require(abs(prev_end - duration) <= max(TIME_EPS, 0.05),
             f"cuts end at {prev_end}, audio duration is {duration}")
    return sb


def load_storyboard(path: str, **kwargs: Any) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return validate_storyboard(json.load(f), **kwargs)


def save_storyboard(sb: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sb, f, ensure_ascii=False, indent=2)

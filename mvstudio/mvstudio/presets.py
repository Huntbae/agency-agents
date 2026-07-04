"""Camera preset registry.

Presets live in presets_data/camera_presets.json (shipped as package data)
so that (a) new motion styles ship without code changes, (b) higher tiers
(t2 depth-parallax, t3 generative Wan2.2 Fun Camera) can extend the same
records, and (c) a community preset ecosystem has a stable unit of sharing.
"""

from __future__ import annotations

import json
import random
from importlib import resources
from typing import Any


def load_presets(path: str | None = None) -> dict[str, dict[str, Any]]:
    if path is not None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        ref = resources.files("mvstudio") / "presets_data" / "camera_presets.json"
        data = json.loads(ref.read_text(encoding="utf-8"))
    presets = {p["id"]: p for p in data["presets"]}
    if not presets:
        raise ValueError("no presets defined")
    return presets


def pick_preset(presets: dict[str, dict[str, Any]], energy: float,
                rng: random.Random, avoid: str | None = None) -> str:
    """Pick a preset whose energy affinity contains `energy`.

    `avoid` prevents the same motion twice in a row.
    """
    pool = [p for p in presets.values()
            if p["energy"][0] <= energy <= p["energy"][1] and p["id"] != avoid]
    if not pool:
        pool = [p for p in presets.values() if p["id"] != avoid] or list(presets.values())
    return rng.choice(sorted(pool, key=lambda p: p["id"]))["id"]

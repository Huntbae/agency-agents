"""Image pool: scan a folder and compute cheap perceptual stats.

Phase 0 has no VLM; brightness/colorfulness stand in for "mood" so the
rule director can pair bright, saturated images with high-energy sections.
The VLM (Qwen3-VL) slots in here later by enriching the same records.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_STAT_SIZE = 64


def scan_images(folder: str) -> list[dict[str, Any]]:
    from PIL import Image

    if not os.path.isdir(folder):
        raise FileNotFoundError(f"image folder not found: {folder}")

    records = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.splitext(name)[1].lower() not in IMAGE_EXTS:
            continue
        try:
            with Image.open(path) as im:
                width, height = im.size
                small = np.asarray(
                    im.convert("RGB").resize((_STAT_SIZE, _STAT_SIZE)),
                    dtype=np.float32) / 255.0
        except Exception:
            continue  # unreadable/corrupt file: skip, don't abort the run
        brightness = float(small.mean())
        # Hasler-Süsstrunk-style colorfulness, cheap approximation.
        rg = small[..., 0] - small[..., 1]
        yb = 0.5 * (small[..., 0] + small[..., 1]) - small[..., 2]
        colorfulness = float(np.hypot(rg.std(), yb.std())
                             + 0.3 * np.hypot(abs(rg.mean()), abs(yb.mean())))
        records.append({
            "path": path,
            "width": width,
            "height": height,
            "brightness": round(brightness, 3),
            "colorfulness": round(colorfulness, 3),
            # Single scalar the director sorts by; VLM tags refine this later.
            "vibrance": round(0.5 * brightness + 0.5 * min(colorfulness * 3, 1.0), 3),
        })

    if not records:
        raise FileNotFoundError(f"no readable images in: {folder}")
    return records

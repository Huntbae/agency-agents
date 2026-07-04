"""Synthetic demo assets: a copyright-free test song (kick/hat/bass with a
quiet intro and a louder groove) plus gradient images. Ships inside the
package so `mvstudio doctor` can self-test on any installed machine.
"""

from __future__ import annotations

import os

import numpy as np

SR = 22050
BPM = 120.0


def make_song(path: str, bars: int = 12) -> str:
    """Write a `bars`-bar (2s each at 120 BPM) synthetic track to `path`."""
    import soundfile as sf

    beat = 60.0 / BPM
    total = bars * 4 * beat
    t = np.arange(int(total * SR)) / SR
    audio = np.zeros_like(t)

    def add(start: float, sound: np.ndarray, gain: float = 1.0) -> None:
        i = int(start * SR)
        j = min(i + len(sound), len(audio))
        audio[i:j] += sound[: j - i] * gain

    dur = np.arange(int(0.12 * SR)) / SR
    kick = np.sin(2 * np.pi * (120 - 300 * dur) * dur) * np.exp(-dur * 28)
    hat = np.random.default_rng(0).normal(0, 0.22, int(0.03 * SR)) * np.exp(
        -np.arange(int(0.03 * SR)) / SR * 180)

    for bar in range(bars):
        # first third = quiet intro, middle = full groove, last third = chorus
        section_gain = 0.45 if bar < bars // 3 else (1.0 if bar < 2 * bars // 3 else 1.4)
        for b in range(4):
            start = (bar * 4 + b) * beat
            add(start, kick, 0.9 * section_gain)
            add(start + beat / 2, hat, 0.5 * section_gain)
            if bar >= bars // 3:
                note = 55.0 * (2 ** ((b % 4) / 12))
                seg = np.arange(int(beat * 0.9 * SR)) / SR
                add(start, np.sin(2 * np.pi * note * seg) * np.exp(-seg * 3),
                    0.25 * section_gain)

    audio /= max(np.abs(audio).max(), 1e-9)
    sf.write(path, (audio * 0.9).astype(np.float32), SR)
    return path


def make_images(folder: str, count: int = 6) -> str:
    """Write `count` gradient test images (dark -> bright palettes)."""
    from PIL import Image, ImageDraw

    palettes = [
        ((10, 12, 40), (40, 20, 90)),      # dark blue -> for quiet parts
        ((30, 30, 30), (90, 90, 100)),     # grey
        ((60, 20, 60), (160, 60, 120)),    # magenta
        ((200, 90, 30), (255, 180, 60)),   # orange -> bright
        ((220, 40, 60), (255, 120, 40)),   # red/orange
        ((240, 200, 60), (255, 240, 160)), # yellow -> brightest
    ]
    os.makedirs(folder, exist_ok=True)
    for i, (c0, c1) in enumerate(palettes[:max(2, min(count, len(palettes)))]):
        im = Image.new("RGB", (1280, 720))
        draw = ImageDraw.Draw(im)
        for y in range(720):
            f = y / 719
            row = tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
            draw.line([(0, y), (1280, y)], fill=row)
        draw.ellipse([540 + i * 20, 260, 740 + i * 20, 460],
                     outline=(255, 255, 255), width=6)
        draw.text((60, 620), f"demo image {i + 1}", fill=(255, 255, 255))
        im.save(os.path.join(folder, f"img_{i + 1}.png"))
    return folder

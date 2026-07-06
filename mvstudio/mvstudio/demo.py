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


def make_showcase_song(path: str) -> str:
    """48s track with a real arrangement — intro / verse / chorus / outro —
    so segmentation, cut pacing, grading and dips are all visible."""
    import soundfile as sf

    beat = 60.0 / BPM
    bars = 24  # 4 intro / 8 verse / 8 chorus / 4 outro
    total = bars * 4 * beat
    t = np.arange(int(total * SR)) / SR
    audio = np.zeros_like(t)
    rng = np.random.default_rng(7)

    def add(start: float, sound: np.ndarray, gain: float = 1.0) -> None:
        i = int(start * SR)
        j = min(i + len(sound), len(audio))
        audio[i:j] += sound[: j - i] * gain

    dur = np.arange(int(0.12 * SR)) / SR
    kick = np.sin(2 * np.pi * (120 - 300 * dur) * dur) * np.exp(-dur * 28)
    hat = rng.normal(0, 0.22, int(0.03 * SR)) * np.exp(
        -np.arange(int(0.03 * SR)) / SR * 180)
    snare = rng.normal(0, 0.3, int(0.09 * SR)) * np.exp(
        -np.arange(int(0.09 * SR)) / SR * 45)

    def pad(freqs: list[float], seconds: float) -> np.ndarray:
        seg = np.arange(int(seconds * SR)) / SR
        wave = sum(np.sin(2 * np.pi * f * seg) for f in freqs)
        env = np.minimum(seg / 0.4, 1.0) * np.exp(-seg / (seconds * 0.9))
        return wave * env / len(freqs)

    chords = [[110.0, 165.0, 220.0], [98.0, 147.0, 196.0],
              [87.3, 131.0, 174.6], [98.0, 147.0, 196.0]]
    melody = [440.0, 494.0, 523.3, 587.3, 523.3, 494.0, 440.0, 392.0]

    for bar in range(bars):
        part = ("intro" if bar < 4 else "verse" if bar < 12
                else "chorus" if bar < 20 else "outro")
        gain = {"intro": 0.4, "verse": 1.0, "chorus": 1.45, "outro": 0.45}[part]
        bar_t = bar * 4 * beat
        add(bar_t, pad(chords[bar % 4], 4 * beat),
            0.35 if part in ("intro", "outro") else 0.15)
        for b in range(4):
            start = bar_t + b * beat
            if part != "intro" or b == 0:
                add(start, kick, 0.9 * gain)
            if part in ("verse", "chorus"):
                add(start + beat / 2, hat, 0.5 * gain)
                note = 55.0 * (2 ** ((b % 4) / 12))
                seg = np.arange(int(beat * 0.9 * SR)) / SR
                add(start, np.sin(2 * np.pi * note * seg) * np.exp(-seg * 3),
                    0.25 * gain)
            if part == "chorus":
                if b in (1, 3):
                    add(start, snare, 0.5 * gain)
                f = melody[(bar * 4 + b) % len(melody)]
                seg = np.arange(int(beat * 0.8 * SR)) / SR
                lead = (np.sin(2 * np.pi * f * seg)
                        + 0.4 * np.sin(2 * np.pi * 2 * f * seg))
                add(start, lead * np.exp(-seg * 2.2), 0.16 * gain)

    audio /= max(np.abs(audio).max(), 1e-9)
    sf.write(path, (audio * 0.9).astype(np.float32), SR)
    return path


def make_scene_images(folder: str) -> str:
    """Ten procedural 'photo-like' scenes spanning dark/calm -> bright/loud
    so both energy and semantic matching have something meaningful to sort."""
    from PIL import Image, ImageDraw

    os.makedirs(folder, exist_ok=True)
    W, H = 1280, 720
    rng = np.random.default_rng(11)

    def gradient(c0, c1):
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        for y in range(H):
            f = y / (H - 1)
            d.line([(0, y), (W, y)],
                   fill=tuple(int(a + (b - a) * f) for a, b in zip(c0, c1)))
        return im, d

    def save(im, name):
        im.save(os.path.join(folder, name))

    im, d = gradient((4, 6, 24), (22, 18, 58))           # 1 night sky
    for _ in range(90):
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H * 0.8))
        d.ellipse([x, y, x + 2, y + 2], fill=(255, 255, 240))
    d.ellipse([W - 300, 80, W - 180, 200], fill=(235, 235, 210))
    save(im, "01_night_sky.png")

    im, d = gradient((250, 130, 60), (110, 35, 90))      # 2 sunset sea
    d.ellipse([W // 2 - 90, 250, W // 2 + 90, 430], fill=(255, 220, 120))
    d.rectangle([0, 430, W, H], fill=(70, 25, 70))
    for y in range(450, H, 28):
        d.line([(0, y), (W, y)], fill=(255, 180, 110), width=2)
    save(im, "02_sunset_sea.png")

    im, d = gradient((60, 40, 90), (20, 15, 40))         # 3 city dusk
    x = 0
    while x < W:
        w, h = int(rng.integers(60, 140)), int(rng.integers(180, 460))
        d.rectangle([x, H - h, x + w, H], fill=(12, 10, 22))
        for wx in range(x + 10, x + w - 10, 24):
            for wy in range(H - h + 15, H - 20, 34):
                if rng.random() < 0.5:
                    d.rectangle([wx, wy, wx + 8, wy + 12], fill=(255, 210, 110))
        x += w + int(rng.integers(5, 30))
    save(im, "03_city_dusk.png")

    im, d = gradient((150, 185, 225), (235, 240, 250))   # 4 morning mountains
    d.polygon([(0, H), (W * 0.35, 250), (W * 0.7, H)], fill=(105, 120, 145))
    d.polygon([(W * 0.4, H), (W * 0.75, 180), (W * 1.1, H)], fill=(75, 90, 115))
    save(im, "04_mountains.png")

    for idx, (name, colors, bg) in enumerate([
            ("05_bokeh_warm.png", [(255, 180, 90), (255, 120, 80),
                                   (255, 220, 140)], (40, 18, 12)),
            ("06_bokeh_cool.png", [(110, 180, 255), (150, 120, 255),
                                   (120, 230, 220)], (10, 16, 36))]):
        base = Image.new("RGB", (W, H), bg)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for _ in range(26):
            r = int(rng.integers(25, 110))
            x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
            c = colors[int(rng.integers(0, len(colors)))]
            od.ellipse([x - r, y - r, x + r, y + r], fill=c + (80,))
        base.paste(overlay, (0, 0), overlay)
        save(base, name)

    im = Image.new("RGB", (W, H), (16, 6, 30))           # 7 neon grid
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, int(H * 0.45)
    for i in range(-12, 13):
        d.line([(cx, cy), (cx + i * 160, H)], fill=(255, 60, 180), width=2)
    for k in range(1, 9):
        y = cy + int((H - cy) * (k / 9) ** 2)
        d.line([(0, y), (W, y)], fill=(70, 230, 255), width=2)
    save(im, "07_neon_grid.png")

    im = Image.new("RGB", (W, H), (255, 205, 70))        # 8 sun burst (brightest)
    d = ImageDraw.Draw(im)
    cx, cy = W // 2, H // 2
    for ang in range(0, 360, 12):
        rad = np.deg2rad(ang)
        d.line([(cx, cy), (cx + 900 * np.cos(rad), cy + 900 * np.sin(rad))],
               fill=(255, 240, 160), width=14)
    d.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], fill=(255, 250, 210))
    save(im, "08_sun_burst.png")

    im, d = gradient((165, 205, 240), (215, 235, 250))   # 9 pastel clouds
    for _ in range(14):
        x, y = int(rng.integers(0, W)), int(rng.integers(60, int(H * 0.7)))
        w, h = int(rng.integers(120, 320)), int(rng.integers(40, 90))
        d.ellipse([x, y, x + w, y + h], fill=(252, 252, 255))
    save(im, "09_pastel_clouds.png")

    im, d = gradient((14, 14, 20), (30, 30, 44))         # 10 night road
    d.polygon([(W * 0.42, int(H * 0.45)), (W * 0.58, int(H * 0.45)),
               (W * 0.95, H), (W * 0.05, H)], fill=(38, 38, 48))
    for k in range(1, 8):
        y0 = int(H * 0.45) + int((H * 0.55) * (k / 8) ** 1.6)
        d.rectangle([W // 2 - 6, y0, W // 2 + 6, y0 + 22], fill=(240, 220, 130))
    save(im, "10_night_road.png")
    return folder


def make_showcase_lrc(path: str) -> str:
    lines = [
        (1.0, "a quiet night begins"), (5.0, "stars over the empty street"),
        (9.5, "we start to move"), (13.5, "every step falls on the beat"),
        (17.5, "hold on to this moment"), (21.5, "the lights are getting louder"),
        (25.5, "this is our chorus"), (29.5, "burning like a summer sun"),
        (33.5, "nothing else matters now"), (37.5, "we sing it one more time"),
        (41.5, "the night is fading out"), (45.0, "see you in the morning light"),
    ]
    with open(path, "w", encoding="utf-8") as f:
        for t, text in lines:
            m, s = divmod(t, 60.0)
            f.write(f"[{int(m):02d}:{s:05.2f}] {text}\n")
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

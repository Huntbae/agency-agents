"""Lyric video support: LRC parsing and subtitle overlays.

Text is rasterized with Pillow onto transparent PNGs and composited by
FFmpeg's core `overlay` filter — no drawtext/freetype/libass dependency,
so it works with any FFmpeg build (incl. minimal LGPL ones) and any
script Pillow can shape (Korean included, given a suitable font).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

_LRC_TAG = re.compile(r"\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?\]")

MAX_LINE_SECONDS = 6.0
MIN_LINE_SECONDS = 0.8

# First existing font wins. Korean-capable fonts first on macOS.
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",          # macOS, Hangul
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",  # macOS, Hangul
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # no Hangul
    "C:/Windows/Fonts/malgun.ttf",                           # Windows, Hangul
]


def parse_lrc(path: str, duration: float | None = None) -> list[dict[str, Any]]:
    """Parse an .lrc file into [{"start", "end", "text"}], sorted by time.

    Supports multiple timestamps per line; metadata tags ([ar:..], [ti:..])
    and empty lines are skipped. Line end = next line's start, capped at
    MAX_LINE_SECONDS (and at `duration` when given).
    """
    entries: list[tuple[float, str]] = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            tags = list(_LRC_TAG.finditer(raw))
            if not tags:
                continue
            text = _LRC_TAG.sub("", raw).strip()
            if not text:
                continue
            for m in tags:
                frac = (m.group(3) or "0").ljust(3, "0")[:3]
                t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / 1000.0
                entries.append((t, text))

    entries.sort(key=lambda e: e[0])
    lines: list[dict[str, Any]] = []
    for i, (start, text) in enumerate(entries):
        if duration is not None and start >= duration:
            break
        end = entries[i + 1][0] if i + 1 < len(entries) else start + MAX_LINE_SECONDS
        end = min(end, start + MAX_LINE_SECONDS)
        if duration is not None:
            end = min(end, duration)
        if end - start < MIN_LINE_SECONDS:
            end = start + MIN_LINE_SECONDS
            if duration is not None:
                end = min(end, duration)
        if end > start:
            lines.append({"start": round(start, 3), "end": round(end, 3),
                          "text": text})
    return lines


def find_font(custom: str | None = None) -> str | None:
    for candidate in ([custom] if custom else []) + \
            [os.environ.get("MVSTUDIO_FONT")] + FONT_CANDIDATES:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _wrap(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def render_line_png(text: str, width: int, height: int, out_path: str,
                    font_path: str | None = None) -> str:
    """Rasterize one lyric line onto a transparent full-frame canvas
    (lower third, centered, black outline for readability)."""
    from PIL import Image, ImageDraw, ImageFont

    size = max(height // 14, 16)
    font_file = find_font(font_path)
    if font_file:
        font = ImageFont.truetype(font_file, size)
    else:
        print("[mvstudio] no scalable font found; using built-in bitmap font "
              "(set MVSTUDIO_FONT for Korean lyrics)", file=sys.stderr)
        font = ImageFont.load_default()

    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    rows = _wrap(draw, text, font, int(width * 0.9))
    line_h = int(size * 1.25)
    y = height - int(height * 0.08) - line_h * len(rows)
    for row in rows:
        x = (width - draw.textlength(row, font=font)) / 2
        draw.text((x, y), row, font=font, fill=(255, 255, 255, 235),
                  stroke_width=max(size // 12, 2), stroke_fill=(0, 0, 0, 200))
        y += line_h
    im.save(out_path)
    return out_path

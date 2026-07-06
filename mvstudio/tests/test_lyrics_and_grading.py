"""Tests for Phase 2 features: color grading, section-dip fades, LRC lyrics
overlay, and the whisper segments->LRC conversion logic."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mvstudio.analyze import analyze_audio
from mvstudio.director import make_storyboard
from mvstudio.images import scan_images
from mvstudio.lyrics import parse_lrc, render_line_png
from mvstudio.presets import load_grades, load_presets
from mvstudio.render import find_ffmpeg, render
from mvstudio.transcribe import segments_to_lrc

LRC = """\
[ar: demo artist]
[00:01.00] first line of lyrics
[00:04.50] second line, a bit longer than the first one
[00:04.50] (this duplicate timestamp line is kept too)
[00:20.00] line beyond a short song
"""


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    from mvstudio.demo import make_images, make_song
    root = tmp_path_factory.mktemp("lyr_assets")
    song = make_song(str(root / "demo.wav"), bars=6)  # 12 seconds
    images = make_images(str(root / "images"))
    lrc = str(root / "demo.lrc")
    with open(lrc, "w", encoding="utf-8") as f:
        f.write(LRC)
    return song, images, lrc


def test_parse_lrc(assets):
    _, _, lrc = assets
    lines = parse_lrc(lrc, duration=12.0)
    # metadata skipped; the 20s line is beyond duration and dropped
    assert [ln["start"] for ln in lines] == [1.0, 4.5, 4.5]
    assert lines[0]["end"] == 4.5           # ends when the next line starts
    assert all(ln["end"] <= 12.0 for ln in lines)
    assert lines[1]["text"].startswith("second line")


def test_grades_table():
    grades = load_grades()
    assert set(grades["by_label"].values()) <= set(grades["grades"])
    assert grades["grades"]["punchy"]["saturation"] > 1.0


def test_director_assigns_grades_and_dips(assets):
    song, images, _ = assets
    analysis = analyze_audio(song)
    assert len(analysis["sections"]) >= 2
    sb = make_storyboard(analysis, scan_images(images), load_presets(),
                         width=640, height=360, fps=24, seed=5)
    cuts = sb["cuts"]
    assert cuts[0]["fade_in"] > 0.3          # long fade-in at the start
    assert cuts[-1].get("fade_out", 0) > 0.3
    # every cut in a labelled section gets a grade
    assert all("grade" in c for c in cuts)
    # a dip exists at each internal section boundary
    boundaries = [s["end"] for s in sb["sections"][:-1]]
    for b in boundaries:
        assert any(abs(c["end"] - b) < 0.05 and c.get("fade_out") == 0.15
                   for c in cuts), f"no dip before boundary {b}"


def test_segments_to_lrc():
    segs = [{"start": 0.0, "text": " hello "}, {"start": 65.34, "text": "world"},
            {"start": 70.0, "text": "  "}]
    lrc = segments_to_lrc(segs)
    assert lrc.splitlines() == ["[00:00.00] hello", "[01:05.34] world"]
    assert segments_to_lrc([]) == ""


def test_render_line_png(tmp_path):
    from PIL import Image
    p = render_line_png("a rather long lyric line that should wrap nicely "
                        "across the frame", 640, 360, str(tmp_path / "l.png"))
    with Image.open(p) as im:
        assert im.size == (640, 360) and im.mode == "RGBA"
        assert im.getextrema()[3][1] > 0     # something was drawn (alpha > 0)


def test_lyric_video_render(assets, tmp_path):
    song, images, lrc = assets
    analysis = analyze_audio(song)
    lyrics = parse_lrc(lrc, duration=analysis["duration"])
    sb = make_storyboard(analysis, scan_images(images), load_presets(),
                         width=640, height=360, fps=24, seed=5, lyrics=lyrics)
    out = str(tmp_path / "lyric.mp4")
    render(sb, load_presets(), out)
    assert os.path.getsize(out) > 50_000

    ffmpeg = find_ffmpeg()
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", out],
                           capture_output=True, text=True).stderr
    assert "Video:" in probe and "Audio:" in probe

    # the lyric overlay must actually change pixels: compare a frame at t=2
    # (line visible) between lyric and no-lyric renders
    sb_plain = {k: v for k, v in sb.items() if k != "lyrics"}
    plain = str(tmp_path / "plain.mp4")
    render(sb_plain, load_presets(), plain)
    import numpy as np
    from PIL import Image

    def frame_at(video, t):
        png = str(tmp_path / f"f_{os.path.basename(video)}.png")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", str(t),
                        "-i", video, "-frames:v", "1", png], check=True)
        with Image.open(png) as im:
            return np.asarray(im.convert("L"), dtype=np.int16)

    diff = np.abs(frame_at(out, 2.0) - frame_at(plain, 2.0)).mean()
    assert diff > 1.0, f"lyric overlay had no visible effect (diff={diff})"

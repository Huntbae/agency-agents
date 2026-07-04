"""Unit + end-to-end tests. Run from mvstudio/:  pytest -q"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mvstudio.analyze import analyze_audio
from mvstudio.director import _sanitize_cuts, make_storyboard
from mvstudio.images import scan_images
from mvstudio.presets import load_presets
from mvstudio.render import find_ffmpeg, render
from mvstudio.schema import StoryboardError, validate_storyboard


@pytest.fixture(scope="session")
def assets(tmp_path_factory):
    from mvstudio.demo import make_images, make_song
    root = tmp_path_factory.mktemp("assets")
    song = make_song(str(root / "demo.wav"))
    images = make_images(str(root / "images"))
    return song, images


def test_presets_load():
    presets = load_presets()
    assert "zoom_in" in presets and "static" in presets
    for spec in presets.values():
        assert len(spec["z"]) == 2 and len(spec["energy"]) == 2


def test_sanitize_fixes_gaps_and_overlaps():
    cuts = [
        {"start": 0.0, "end": 2.0, "image": "a", "preset": "static"},
        {"start": 2.5, "end": 4.0, "image": "b", "preset": "static"},  # gap
        {"start": 3.5, "end": 6.0, "image": "c", "preset": "static"},  # overlap
    ]
    fixed = _sanitize_cuts(cuts, 8.0)
    assert fixed[0]["start"] == 0.0
    for prev, cur in zip(fixed[:-1], fixed[1:]):
        assert cur["start"] == prev["end"]
    assert fixed[-1]["end"] == 8.0


def test_analysis_and_storyboard(assets):
    song, images = assets
    analysis = analyze_audio(song)
    assert 100 <= analysis["bpm"] <= 140  # synthetic track is 120 BPM
    assert len(analysis["beats"]) > 10
    assert analysis["sections"][0]["start"] == 0.0
    # the demo track has a quiet 8s intro then a groove: segmentation must
    # find at least 2 sections and rank the intro's energy lowest
    assert len(analysis["sections"]) >= 2
    energies = [s["energy"] for s in analysis["sections"]]
    assert energies[0] == min(energies)

    pool = scan_images(images)
    assert len(pool) == 6
    # bright yellow demo image must rank above the dark blue one
    by_path = {os.path.basename(r["path"]): r["vibrance"] for r in pool}
    assert by_path["img_6.png"] > by_path["img_1.png"]

    presets = load_presets()
    sb = make_storyboard(analysis, pool, presets, width=640, height=360,
                         fps=24, seed=7)
    validate_storyboard(sb, known_presets=set(presets))
    # determinism: same seed -> identical storyboard
    sb2 = make_storyboard(analysis, pool, presets, width=640, height=360,
                          fps=24, seed=7)
    assert sb["cuts"] == sb2["cuts"]
    # adjacent cuts never reuse an image
    for prev, cur in zip(sb["cuts"][:-1], sb["cuts"][1:]):
        assert prev["image"] != cur["image"]


def test_storyboard_rejects_gap():
    sb = {
        "version": 1,
        "audio": {"path": __file__, "duration": 10.0},
        "output": {"width": 640, "height": 360, "fps": 24},
        "cuts": [
            {"start": 0.0, "end": 4.0, "image": __file__, "preset": "static"},
            {"start": 5.0, "end": 10.0, "image": __file__, "preset": "static"},
        ],
    }
    with pytest.raises(StoryboardError):
        validate_storyboard(sb)


def test_mp3_input(assets, tmp_path):
    """librosa must decode mp3 (libsndfile >= 1.1); the whole pipeline is
    format-agnostic after load."""
    song, _ = assets
    mp3 = str(tmp_path / "demo.mp3")
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-i", song, mp3],
                   check=True)
    analysis = analyze_audio(mp3)
    assert abs(analysis["duration"] - 24.0) < 0.2


def test_portrait_image_render(assets, tmp_path):
    """Portrait/odd-aspect images must be cover-cropped, not distorted."""
    song, _ = assets
    from PIL import Image
    imgdir = tmp_path / "portrait"
    imgdir.mkdir()
    Image.new("RGB", (600, 1200), (200, 60, 60)).save(imgdir / "p1.png")
    Image.new("RGB", (500, 500), (60, 200, 60)).save(imgdir / "p2.png")

    analysis = analyze_audio(song)
    pool = scan_images(str(imgdir))
    presets = load_presets()
    sb = make_storyboard(analysis, pool, presets, width=640, height=360,
                         fps=24, seed=3)
    out = str(tmp_path / "portrait.mp4")
    render(sb, presets, out)
    probe = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", out],
                           capture_output=True, text=True).stderr
    assert "640x360" in probe


def test_end_to_end_render(assets, tmp_path):
    song, images = assets
    analysis = analyze_audio(song)
    pool = scan_images(images)
    presets = load_presets()
    sb = make_storyboard(analysis, pool, presets, width=640, height=360,
                         fps=24, seed=7)
    out = str(tmp_path / "out.mp4")
    render(sb, presets, out)
    assert os.path.getsize(out) > 50_000

    # container must hold a video and an audio stream of ~song duration
    probe = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", out],
                           capture_output=True, text=True).stderr
    assert "Video:" in probe and "Audio:" in probe
    import re
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
    assert m, probe
    got = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    assert abs(got - analysis["duration"]) < 0.5

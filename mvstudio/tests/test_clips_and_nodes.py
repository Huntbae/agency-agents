"""Video-clip cuts (lip-sync composite path) + ComfyUI node pack tests.

The lip-sync GENERATOR is external (ComfyUI nodes / other tools); what the
engine owns — and what these tests verify end-to-end — is that an external
clip is placed as one continuous cut over a section, survives validation,
and renders into the final video.  ComfyUI nodes are imported standalone
(no ComfyUI runtime) and driven directly.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mvstudio.analyze import analyze_audio
from mvstudio.clips import export_section_audio, place_clip
from mvstudio.director import make_storyboard
from mvstudio.images import scan_images
from mvstudio.presets import load_presets
from mvstudio.render import find_ffmpeg, media_duration, render


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    from mvstudio.demo import make_images, make_showcase_song
    root = tmp_path_factory.mktemp("clip_assets")
    song = make_showcase_song(str(root / "song.wav"))  # 48s, has a chorus
    images = make_images(str(root / "images"))
    # stand-in for a lip-synced clip: 6s synthetic moving test pattern
    clip = str(root / "talking.mp4")
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=duration=6:size=320x240:rate=24",
                    "-pix_fmt", "yuv420p", clip], check=True)
    return song, images, clip


@pytest.fixture(scope="module")
def storyboard(assets):
    song, images, _ = assets
    analysis = analyze_audio(song)
    return make_storyboard(analysis, scan_images(images), load_presets(),
                           width=640, height=360, fps=24, seed=7)


def test_place_clip_continuous_over_high_section(storyboard, assets):
    _, _, clip = assets
    presets = set(load_presets())
    sb = place_clip(storyboard, clip, label="high", known_presets=presets)

    video_cuts = [c for c in sb["cuts"] if c.get("video")]
    assert len(video_cuts) == 1
    vc = video_cuts[0]
    high = next(s for s in sb["sections"] if s["label"] == "high")
    assert abs(vc["start"] - high["start"]) < 0.1
    # 6s clip covers 6s of the section, not restarted per beat
    assert 5.5 <= vc["end"] - vc["start"] <= min(6.5, high["end"] - high["start"] + 0.1)
    # timeline still contiguous end to end
    for prev, cur in zip(sb["cuts"][:-1], sb["cuts"][1:]):
        assert abs(cur["start"] - prev["end"]) < 0.05


def test_place_clip_render_end_to_end(storyboard, assets, tmp_path):
    song, _, clip = assets
    sb = place_clip(storyboard, clip, label="high",
                    known_presets=set(load_presets()))
    out = str(tmp_path / "with_clip.mp4")
    render(sb, load_presets(), out)
    got = media_duration(out)
    assert got and abs(got - sb["audio"]["duration"]) < 0.5


def test_section_audio_export(storyboard, assets, tmp_path):
    song, _, _ = assets
    out = str(tmp_path / "sec.wav")
    high_idx = next(i for i, s in enumerate(storyboard["sections"])
                    if s["label"] == "high")
    export_section_audio(song, storyboard, high_idx, out)
    s = storyboard["sections"][high_idx]
    got = media_duration(out)
    assert got and abs(got - (s["end"] - s["start"])) < 0.3


def test_place_clip_bad_inputs(storyboard, tmp_path, assets):
    from mvstudio.render import RenderError
    _, _, clip = assets
    with pytest.raises(ValueError):
        place_clip(storyboard, clip, section=99)
    empty = str(tmp_path / "empty.mp4")
    open(empty, "wb").close()
    with pytest.raises(RenderError):
        place_clip(storyboard, empty, label="high")


# ---------------------------------------------------------- ComfyUI nodes

def _load_nodes():
    path = os.path.join(ROOT, "comfyui-mvstudio", "nodes.py")
    spec = importlib.util.spec_from_file_location("comfyui_mvstudio_nodes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_comfyui_nodes_registry():
    mod = _load_nodes()
    assert set(mod.NODE_CLASS_MAPPINGS) == set(mod.NODE_DISPLAY_NAME_MAPPINGS)
    for cls in mod.NODE_CLASS_MAPPINGS.values():
        assert hasattr(cls, "INPUT_TYPES") and hasattr(cls, "RETURN_TYPES")
        assert hasattr(cls, cls.FUNCTION)


def test_comfyui_full_flow(assets, tmp_path):
    song, images, clip = assets
    mod = _load_nodes()

    _, summary = mod.MVStudioAnalyzeSong().run(song)
    assert "energy" in summary

    sb_path, summary = mod.MVStudioStoryboard().run(
        song, str(tmp_path / "sb.json"), 640, 360, 24, 7, images_dir=images)
    assert os.path.isfile(sb_path) and "high" in summary
    high_idx = next(int(line.split("]")[0].strip("[ "))
                    for line in summary.splitlines() if "high" in line)

    (audio_path,) = mod.MVStudioSectionAudio().run(
        song, sb_path, high_idx, str(tmp_path / "sec.wav"))
    assert os.path.getsize(audio_path) > 1000

    (sb_path2,) = mod.MVStudioPlaceClip().run(sb_path, clip, section=high_idx)
    (video,) = mod.MVStudioRender().run(sb_path2, str(tmp_path / "final.mp4"))
    assert os.path.getsize(video) > 50_000

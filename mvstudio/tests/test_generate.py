"""Lyrics-to-visuals generation tests. The mflux call is injectable — a
fake generator paints solid PNGs — so what we verify is the contract:
prompts reflect lyrics and section energy, pools map images to their
sections exactly, and the storyboard honors them."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mvstudio.analyze import analyze_audio
from mvstudio.director import make_storyboard
from mvstudio.generate import (GenerationUnavailable, _template_prompts,
                               build_scene_prompts, generate_visuals)
from mvstudio.images import scan_images
from mvstudio.lyrics import parse_lrc
from mvstudio.presets import load_presets


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    from mvstudio.demo import make_showcase_lrc, make_showcase_song
    root = tmp_path_factory.mktemp("gen_assets")
    song = make_showcase_song(str(root / "song.wav"))
    lrc = make_showcase_lrc(str(root / "song.lrc"))
    return song, lrc


def test_template_prompts_reflect_lyrics_and_energy(assets):
    song, lrc = assets
    analysis = analyze_audio(song)
    lyrics = parse_lrc(lrc, duration=analysis["duration"])
    prompts = _template_prompts(analysis, lyrics, "test style", per_section=3)
    assert len(prompts) == len(analysis["sections"])
    assert all(len(p) == 3 for p in prompts)
    joined = " ".join(p for sec in prompts for p in sec)
    assert "test style" in joined
    # lyric text must appear in the prompts of its own section
    high = [i for i, s in enumerate(analysis["sections"]) if s["label"] == "high"]
    assert high, "showcase song must have a high-energy section"
    assert any("chorus" in p or "summer sun" in p for p in prompts[high[0]])


def test_build_scene_prompts_falls_back_without_ollama(assets, monkeypatch):
    song, _ = assets
    from mvstudio import semantic
    monkeypatch.setattr(semantic, "OLLAMA_URL", "http://localhost:9")
    analysis = analyze_audio(song)
    prompts = build_scene_prompts(analysis, None, per_section=2)
    assert len(prompts) == len(analysis["sections"])


def test_generate_visuals_pools_and_render(assets, tmp_path):
    song, lrc = assets
    analysis = analyze_audio(song)
    lyrics = parse_lrc(lrc, duration=analysis["duration"])

    calls = []

    def fake_generator(prompt, seed, out_path):
        from PIL import Image
        calls.append((prompt, seed))
        shade = 40 + (seed % 200)
        Image.new("RGB", (640, 360), (shade, shade // 2, 90)).save(out_path)

    outdir, pools = generate_visuals(
        analysis, lyrics, str(tmp_path / "gen"), per_section=2,
        text_model=None, generator=fake_generator, seed=1)

    n_sections = len(analysis["sections"])
    assert len(pools) == n_sections and len(calls) == n_sections * 2
    manifest = json.load(open(os.path.join(outdir, "prompts.json")))
    assert len(manifest["sections"]) == n_sections
    # pools are exact: section i only contains its own generated files
    for i, pool in enumerate(pools):
        assert all(os.path.basename(p).startswith(f"s{i:02d}_") for p in pool)
        assert all(os.path.isfile(p) for p in pool)

    sb = make_storyboard(analysis, scan_images(outdir), load_presets(),
                         width=640, height=360, fps=24, seed=1,
                         lyrics=lyrics, pools=pools)
    # every cut uses an image generated for the section it sits in
    for cut in sb["cuts"]:
        mid = (cut["start"] + cut["end"]) / 2
        sec = next(i for i, s in enumerate(sb["sections"])
                   if s["start"] <= mid < s["end"] or s is sb["sections"][-1])
        assert cut["image"] in pools[sec]


def test_generation_unavailable_message():
    with pytest.raises(GenerationUnavailable) as exc:
        from mvstudio.generate import _mflux_generator
        _mflux_generator("flux2-klein-4b", 640, 360)
    assert "mvstudio[gen]" in str(exc.value)

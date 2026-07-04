"""Semantic matching tests. The Ollama calls are mocked (the real vision
model runs on a user machine); what we verify here is the contract:
excluded images never reach the video, section pools are honored, and
unavailability degrades cleanly."""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mvstudio import semantic
from mvstudio.analyze import analyze_audio
from mvstudio.director import make_storyboard
from mvstudio.images import scan_images
from mvstudio.presets import load_presets
from mvstudio.semantic import SemanticUnavailable, match_images, semantic_match


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    from mvstudio.demo import make_images, make_song
    root = tmp_path_factory.mktemp("sem_assets")
    song = make_song(str(root / "demo.wav"), bars=6)
    images = make_images(str(root / "images"))
    return song, images


def test_unavailable_when_no_ollama(monkeypatch, assets):
    song, images = assets
    # point at a dead port so check_available fails fast
    monkeypatch.setattr(semantic, "OLLAMA_URL", "http://localhost:9")
    analysis = analyze_audio(song)
    with pytest.raises(SemanticUnavailable) as exc:
        semantic_match(analysis, scan_images(images), None)
    assert "brew install ollama" in str(exc.value)


def test_match_excludes_and_pools(monkeypatch, assets):
    song, images = assets
    analysis = analyze_audio(song)
    pool = scan_images(images)
    n_sections = len(analysis["sections"])
    assert n_sections >= 2

    # model says: photo 0 is an unrelated screenshot; photo 5 fits everything
    def fake_chat(model, messages, timeout=600.0):
        return json.dumps({
            "exclude": [0],
            "sections": [{"index": i, "images": [5, 3, 2]}
                         for i in range(n_sections)],
        })

    monkeypatch.setattr(semantic, "_chat", fake_chat)
    pools, excluded = match_images(analysis, pool, None)
    assert excluded == [pool[0]["path"]]
    assert len(pools) == n_sections
    assert all(pool[0]["path"] not in p for p in pools)
    assert pools[0][0] == pool[5]["path"]

    # the storyboard must never use the excluded image
    sb = make_storyboard(analysis, pool, load_presets(), width=640, height=360,
                         fps=24, seed=5, pools=pools)
    used = {c["image"] for c in sb["cuts"]}
    assert pool[0]["path"] not in used
    assert used <= {r["path"] for r in pool[1:]}


def test_match_survives_garbage_model_output(monkeypatch, assets):
    song, images = assets
    analysis = analyze_audio(song)
    pool = scan_images(images)

    # model tries to exclude everything and returns broken section entries
    def fake_chat(model, messages, timeout=600.0):
        return json.dumps({
            "exclude": list(range(len(pool))),
            "sections": [{"index": "x"}, {"images": [99]}],
        })

    monkeypatch.setattr(semantic, "_chat", fake_chat)
    pools, excluded = match_images(analysis, pool, None)
    assert excluded == []                       # exclude-all is refused
    assert all(p for p in pools)                # every section keeps images

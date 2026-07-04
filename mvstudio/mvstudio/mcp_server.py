"""mvstudio MCP server (Phase 0.5): the engine as agent tools.

Exposes the headless engine over the Model Context Protocol so any MCP
client (Claude Desktop/Code, etc.) can direct music videos conversationally
— the local counterpart of Higgsfield MCP, with no cloud and no credits.

Run:            mvstudio-mcp            (stdio transport)
Claude config:  {"mcpServers": {"mvstudio": {"command": "mvstudio-mcp"}}}

Requires the optional dependency:  pip install "mvstudio[mcp]"
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .analyze import analyze_audio
from .director import make_storyboard
from .images import scan_images
from .presets import load_presets
from .render import render as render_storyboard
from .schema import load_storyboard, save_storyboard

server = FastMCP(
    "mvstudio",
    instructions=(
        "Local music video engine. Typical flow: analyze_song -> "
        "generate_storyboard -> (optionally edit the storyboard JSON file) "
        "-> render_video. Or call make_music_video for the whole pipeline. "
        "Everything runs on this machine; no files leave it."),
)


def _abs(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


@server.tool()
def analyze_song(song_path: str) -> dict[str, Any]:
    """Analyze an audio file: BPM, beat grid, per-beat energy and
    low/mid/high energy sections. Returns the analysis as JSON."""
    return analyze_audio(_abs(song_path))


@server.tool()
def list_camera_presets() -> list[dict[str, Any]]:
    """List available camera motion presets (id, tier, zoom/pan ranges and
    the energy affinity used to match presets to song sections)."""
    return list(load_presets().values())


@server.tool()
def generate_storyboard(song_path: str, images_dir: str,
                        storyboard_path: str = "storyboard.json",
                        width: int = 1920, height: int = 1080, fps: int = 30,
                        seed: int = 42, director: str = "rule",
                        model: str = "qwen3:8b") -> dict[str, Any]:
    """Analyze a song and an image folder, then write a beat-synced
    storyboard JSON. director='rule' is deterministic; director='ollama'
    uses a local LLM and falls back to the rule director on failure.
    Returns a summary plus the storyboard path (edit it, then render)."""
    analysis = analyze_audio(_abs(song_path))
    images = scan_images(_abs(images_dir))
    presets = load_presets()
    sb = make_storyboard(analysis, images, presets, width=width, height=height,
                         fps=fps, seed=seed, director=director, model=model)
    out = _abs(storyboard_path)
    save_storyboard(sb, out)
    return {
        "storyboard_path": out,
        "duration": sb["audio"]["duration"],
        "bpm": sb["audio"]["bpm"],
        "sections": sb["sections"],
        "cut_count": len(sb["cuts"]),
        "director": sb["meta"]["director"],
    }


@server.tool()
def render_video(storyboard_path: str, output_path: str = "out.mp4") -> dict[str, Any]:
    """Render a storyboard JSON to an mp4 (deterministic FFmpeg engine).
    Cut timing, images and camera presets come only from the storyboard."""
    presets = load_presets()
    sb = load_storyboard(_abs(storyboard_path), known_presets=set(presets))
    out = render_storyboard(sb, presets, _abs(output_path))
    return {"output_path": out, "size_bytes": os.path.getsize(out),
            "duration": sb["audio"]["duration"], "cut_count": len(sb["cuts"])}


@server.tool()
def make_music_video(song_path: str, images_dir: str,
                     output_path: str = "out.mp4",
                     width: int = 1920, height: int = 1080, fps: int = 30,
                     seed: int = 42, director: str = "rule",
                     model: str = "qwen3:8b") -> dict[str, Any]:
    """Full pipeline in one call: analyze the song, direct a beat-synced
    storyboard from the image folder, and render the mp4. Also writes
    <output>.storyboard.json next to the video for later editing."""
    sb_path = os.path.splitext(_abs(output_path))[0] + ".storyboard.json"
    summary = generate_storyboard(song_path, images_dir, sb_path,
                                  width=width, height=height, fps=fps,
                                  seed=seed, director=director, model=model)
    result = render_video(sb_path, output_path)
    return {**summary, **result}


@server.tool()
def inspect_storyboard(storyboard_path: str) -> dict[str, Any]:
    """Validate a storyboard JSON and summarize it (sections, cuts, presets
    used). Use before render_video after hand-editing the file."""
    presets = load_presets()
    sb = load_storyboard(_abs(storyboard_path), known_presets=set(presets))
    used = sorted({c["preset"] for c in sb["cuts"]})
    return {"valid": True, "duration": sb["audio"]["duration"],
            "bpm": sb["audio"]["bpm"], "cut_count": len(sb["cuts"]),
            "presets_used": used, "sections": sb["sections"]}


def main() -> None:
    server.run()  # stdio transport


if __name__ == "__main__":
    main()

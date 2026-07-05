"""mvstudio engine exposed as ComfyUI nodes.

Nodes exchange plain file paths (STRING), so they compose with any other
node pack: generate a lip-synced portrait with your lip-sync nodes
(LatentSync/Sonic/SadTalker...), save it with VHS Save Video, then feed
the saved path into "MVStudio Place Clip" and render.

The nodes import mvstudio from this repo directly (no pip install into
ComfyUI's venv needed) — see _ensure_mvstudio().
"""

from __future__ import annotations

import json
import os
import sys


def _ensure_mvstudio() -> None:
    # this folder lives inside the mvstudio project; resolve through the
    # custom_nodes symlink to the real location and import from there
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_mvstudio()


def _load(path: str):
    from mvstudio.presets import load_presets
    from mvstudio.schema import load_storyboard
    presets = load_presets()
    return load_storyboard(os.path.expanduser(path),
                           known_presets=set(presets)), presets


class MVStudioAnalyzeSong:
    """Song -> BPM / beats / energy sections (JSON string + section list)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"song_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("analysis_json", "sections_summary")
    FUNCTION = "run"
    CATEGORY = "mvstudio"

    def run(self, song_path):
        from mvstudio.analyze import analyze_audio
        analysis = analyze_audio(os.path.expanduser(song_path))
        summary = "\n".join(
            f"[{i}] {s['start']:7.1f}-{s['end']:7.1f}s  "
            f"energy={s['energy']:.2f}  {s.get('label', '')}"
            for i, s in enumerate(analysis["sections"]))
        return (json.dumps(analysis, ensure_ascii=False), summary)


class MVStudioStoryboard:
    """Song + photo folder (or lyrics-generated visuals) -> storyboard JSON
    file. Edit it or place clips before rendering."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "song_path": ("STRING", {"default": ""}),
                "storyboard_path": ("STRING", {"default": "storyboard.json"}),
                "width": ("INT", {"default": 1280, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 720, "min": 64, "max": 4096}),
                "fps": ("INT", {"default": 30, "min": 1, "max": 120}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2**31}),
            },
            "optional": {
                "images_dir": ("STRING", {"default": ""}),
                "lyrics_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("storyboard_path", "sections_summary")
    FUNCTION = "run"
    CATEGORY = "mvstudio"

    def run(self, song_path, storyboard_path, width, height, fps, seed,
            images_dir="", lyrics_path=""):
        from mvstudio.analyze import analyze_audio
        from mvstudio.director import make_storyboard
        from mvstudio.images import scan_images
        from mvstudio.presets import load_presets
        from mvstudio.schema import save_storyboard

        song = os.path.expanduser(song_path)
        analysis = analyze_audio(song)
        lyrics = None
        if lyrics_path.strip():
            from mvstudio.lyrics import parse_lrc
            lyrics = parse_lrc(os.path.expanduser(lyrics_path),
                               duration=analysis["duration"])
        if images_dir.strip():
            images = scan_images(os.path.expanduser(images_dir))
            pools = None
        else:
            from mvstudio.generate import generate_visuals
            gen_dir = os.path.splitext(
                os.path.expanduser(storyboard_path))[0] + ".gen"
            _, pools = generate_visuals(analysis, lyrics, gen_dir)
            images = scan_images(gen_dir)

        sb = make_storyboard(analysis, images, load_presets(), width=width,
                             height=height, fps=fps, seed=seed,
                             lyrics=lyrics, pools=pools)
        out = os.path.abspath(os.path.expanduser(storyboard_path))
        save_storyboard(sb, out)
        summary = "\n".join(
            f"[{i}] {s['start']:7.1f}-{s['end']:7.1f}s  "
            f"energy={s['energy']:.2f}  {s.get('label', '')}"
            for i, s in enumerate(sb["sections"]))
        return (out, summary)


class MVStudioSectionAudio:
    """Export one section's audio — feed THIS to your lip-sync node so the
    mouth matches exactly that part of the song."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "song_path": ("STRING", {"default": ""}),
            "storyboard_path": ("STRING", {"default": ""}),
            "section": ("INT", {"default": 0, "min": 0, "max": 64}),
            "output_path": ("STRING", {"default": "section.wav"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("audio_path",)
    FUNCTION = "run"
    CATEGORY = "mvstudio"

    def run(self, song_path, storyboard_path, section, output_path):
        from mvstudio.clips import export_section_audio
        sb, _ = _load(storyboard_path)
        out = export_section_audio(os.path.expanduser(song_path), sb, section,
                                   os.path.abspath(os.path.expanduser(output_path)))
        return (out,)


class MVStudioPlaceClip:
    """Composite a video clip (e.g. your lip-synced portrait) as one
    continuous cut over a section of the storyboard."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard_path": ("STRING", {"default": ""}),
                "video_path": ("STRING", {"default": ""}),
            },
            "optional": {
                "section": ("INT", {"default": -1, "min": -1, "max": 64,
                                    "tooltip": "-1 = first 'high' section"}),
                "video_offset": ("FLOAT", {"default": 0.0, "min": 0.0}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("storyboard_path",)
    FUNCTION = "run"
    CATEGORY = "mvstudio"

    def run(self, storyboard_path, video_path, section=-1, video_offset=0.0):
        from mvstudio.clips import place_clip
        from mvstudio.schema import save_storyboard
        sb, presets = _load(storyboard_path)
        sb = place_clip(sb, os.path.abspath(os.path.expanduser(video_path)),
                        section=None if section < 0 else section,
                        label="high" if section < 0 else None,
                        video_offset=video_offset,
                        known_presets=set(presets))
        out = os.path.abspath(os.path.expanduser(storyboard_path))
        save_storyboard(sb, out)
        return (out,)


class MVStudioRender:
    """Deterministic render: storyboard JSON -> beat-synced mp4."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "storyboard_path": ("STRING", {"default": ""}),
            "output_path": ("STRING", {"default": "music_video.mp4"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "run"
    CATEGORY = "mvstudio"
    OUTPUT_NODE = True

    def run(self, storyboard_path, output_path):
        from mvstudio.render import render
        sb, presets = _load(storyboard_path)
        out = render(sb, presets,
                     os.path.abspath(os.path.expanduser(output_path)))
        return (out,)


NODE_CLASS_MAPPINGS = {
    "MVStudioAnalyzeSong": MVStudioAnalyzeSong,
    "MVStudioStoryboard": MVStudioStoryboard,
    "MVStudioSectionAudio": MVStudioSectionAudio,
    "MVStudioPlaceClip": MVStudioPlaceClip,
    "MVStudioRender": MVStudioRender,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MVStudioAnalyzeSong": "MVStudio: Analyze Song",
    "MVStudioStoryboard": "MVStudio: Storyboard",
    "MVStudioSectionAudio": "MVStudio: Section Audio (for lip-sync)",
    "MVStudioPlaceClip": "MVStudio: Place Clip (lip-sync composite)",
    "MVStudioRender": "MVStudio: Render Music Video",
}

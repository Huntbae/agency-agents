"""Video-clip placement: composite externally generated clips (lip-synced
talking portraits from ComfyUI, Wan2.2 motion clips, anything) into the
beat-synced timeline.

A lip-synced clip must play CONTINUOUSLY — restarting it on every 1-beat
cut would reset the mouth motion — so `place_clip` replaces the covered
span of a section with ONE video cut and re-stitches the neighbours.
"""

from __future__ import annotations

import subprocess
from typing import Any

from .render import RenderError, find_ffmpeg, media_duration
from .schema import MIN_CUT_SECONDS, validate_storyboard


def _pick_section(sb: dict[str, Any], section: int | None,
                  label: str | None) -> dict[str, Any]:
    sections = sb["sections"]
    if section is not None:
        if not 0 <= section < len(sections):
            raise ValueError(f"section index out of range: {section} "
                             f"(0..{len(sections) - 1})")
        return sections[section]
    want = label or "high"
    for s in sections:
        if s.get("label") == want:
            return s
    raise ValueError(f"no section labelled {want!r}; use --section <index> "
                     f"(sections: {[s.get('label') for s in sections]})")


def place_clip(sb: dict[str, Any], video_path: str,
               section: int | None = None, label: str | None = None,
               video_offset: float = 0.0,
               known_presets: set[str] | None = None) -> dict[str, Any]:
    """Place `video_path` as one continuous cut over the chosen section
    (the whole section, or as much as the clip covers). Returns the
    modified storyboard, re-validated."""
    clip_dur = media_duration(video_path)
    if not clip_dur or clip_dur <= 0:
        raise RenderError(f"could not read video duration: {video_path}")
    usable = max(clip_dur - video_offset, 0.0)
    if usable < MIN_CUT_SECONDS:
        raise RenderError(f"clip too short after offset ({usable:.2f}s)")

    target = _pick_section(sb, section, label)
    span0 = target["start"]
    span1 = min(target["end"], span0 + usable)
    if span1 - span0 < MIN_CUT_SECONDS:
        raise RenderError("target section too short for the clip")

    kept: list[dict[str, Any]] = []
    for cut in sb["cuts"]:
        if cut["end"] <= span0 + 1e-6 or cut["start"] >= span1 - 1e-6:
            kept.append(cut)
        elif cut["start"] < span0 < cut["end"]:
            head = {**cut, "end": round(span0, 3)}
            head.pop("fade_out", None)
            if head["end"] - head["start"] >= MIN_CUT_SECONDS:
                kept.append(head)
            else:
                span0 = cut["start"]  # absorb the sliver into the clip
        elif cut["start"] < span1 < cut["end"]:
            tail = {**cut, "start": round(span1, 3)}
            tail.pop("fade_in", None)
            if tail["end"] - tail["start"] >= MIN_CUT_SECONDS:
                kept.append(tail)
            else:
                span1 = cut["end"]
        # cuts fully inside the span are dropped

    video_cut: dict[str, Any] = {
        "start": round(span0, 3), "end": round(span1, 3),
        "video": video_path, "preset": "static",
    }
    if video_offset > 0:
        video_cut["video_offset"] = round(video_offset, 3)
    kept.append(video_cut)
    kept.sort(key=lambda c: c["start"])

    # re-stitch tiny float gaps introduced by rounding
    for prev, cur in zip(kept[:-1], kept[1:]):
        if abs(cur["start"] - prev["end"]) <= 0.05:
            cur["start"] = prev["end"]

    sb = {**sb, "cuts": kept}
    return validate_storyboard(sb, known_presets=known_presets)


def export_section_audio(song_path: str, sb: dict[str, Any],
                         section: int, out_path: str) -> str:
    """Cut the song's audio for one section (feed this to the lip-sync
    tool so the mouth matches exactly that part of the song)."""
    sections = sb["sections"]
    if not 0 <= section < len(sections):
        raise ValueError(f"section index out of range: {section} "
                         f"(0..{len(sections) - 1})")
    s = sections[section]
    ffmpeg = find_ffmpeg()
    proc = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-i", song_path, "-ss", f"{s['start']:.3f}",
         "-t", f"{s['end'] - s['start']:.3f}", out_path],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(f"audio export failed:\n{proc.stderr[-800:]}")
    return out_path

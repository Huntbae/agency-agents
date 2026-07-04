"""Deterministic FFmpeg renderer: storyboard JSON in, mp4 out.

Licensing note (matters for distribution, see README):
- Works with a plain LGPL FFmpeg build. Never requires --enable-gpl.
- Encoder preference: h264_videotoolbox (macOS hardware, LGPL-safe) >
  libopenh264 (LGPL-compatible) > libx264 (GPL — dev only, warned) > mpeg4.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any


def _log(msg: str) -> None:
    # stderr, never stdout: the MCP server speaks JSON-RPC on stdout.
    print(msg, file=sys.stderr, flush=True)

# Upscale factor applied before zoompan; sub-pixel motion on the enlarged
# frame is what prevents the classic zoompan jitter.
SUPERSAMPLE = 3


class RenderError(RuntimeError):
    pass


def find_ffmpeg() -> str:
    exe = os.environ.get("MVSTUDIO_FFMPEG") or shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RenderError(
            "ffmpeg not found. Install FFmpeg (LGPL build recommended), set "
            "MVSTUDIO_FFMPEG, or `pip install imageio-ffmpeg` for development.")


def pick_encoder(ffmpeg: str) -> tuple[str, list[str]]:
    """Return (encoder, extra output args) by LGPL-friendly preference."""
    out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    if "h264_videotoolbox" in out:
        return "h264_videotoolbox", ["-b:v", "10M"]
    if "libopenh264" in out:
        return "libopenh264", ["-b:v", "8M"]
    if "libx264" in out:
        _log("[mvstudio] WARNING: encoding with libx264 (GPL). Fine for local "
             "development; do NOT ship this FFmpeg build in a commercial app.")
        return "libx264", ["-preset", "veryfast", "-crf", "20"]
    return "mpeg4", ["-q:v", "4"]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(f"ffmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-2000:]}")


def _zoompan_filter(preset: dict[str, Any], frames: int, width: int,
                    height: int, fps: int) -> str:
    sw, sh = width * SUPERSAMPLE, height * SUPERSAMPLE
    z0, z1 = preset["z"]
    px0, px1 = preset["px"]
    py0, py1 = preset["py"]
    n = max(frames - 1, 1)
    t = f"on/{n}"
    return (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
        f"crop={sw}:{sh},"
        f"zoompan=z='{z0}+({z1 - z0})*{t}'"
        f":x='(iw-iw/zoom)*({px0}+({px1 - px0})*{t})'"
        f":y='(ih-ih/zoom)*({py0}+({py1 - py0})*{t})'"
        f":d={frames}:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )


def _eq_filter(grade_params: dict[str, Any]) -> str:
    args = ":".join(f"{k}={v}" for k, v in grade_params.items())
    return f"eq={args}"


def render(sb: dict[str, Any], presets: dict[str, dict[str, Any]],
           output: str, workdir: str | None = None,
           keep_temp: bool = False,
           grades: dict[str, Any] | None = None) -> str:
    ffmpeg = find_ffmpeg()
    encoder, enc_args = pick_encoder(ffmpeg)
    out_cfg = sb["output"]
    width, height, fps = out_cfg["width"], out_cfg["height"], out_cfg["fps"]
    duration = sb["audio"]["duration"]
    cuts = sb["cuts"]
    lyrics = sb.get("lyrics") or []

    if grades is None:
        from .presets import load_grades
        grades = load_grades()
    grade_table = grades.get("grades", {})

    tmp = workdir or tempfile.mkdtemp(prefix="mvstudio-")
    os.makedirs(tmp, exist_ok=True)
    clip_paths = []
    try:
        for i, cut in enumerate(cuts):
            dur = cut["end"] - cut["start"]
            frames = max(int(round(dur * fps)), 1)
            vf = _zoompan_filter(presets[cut["preset"]], frames, width, height, fps)
            grade = grade_table.get(cut.get("grade", ""), {})
            if grade:
                vf += f",{_eq_filter(grade)}"
            fade_in = float(cut.get("fade_in", 0) or 0)
            fade_out = float(cut.get("fade_out", 0) or 0)
            if fade_in > 0:
                vf += f",fade=t=in:st=0:d={fade_in:.3f}"
            if 0 < fade_out < dur:
                vf += f",fade=t=out:st={dur - fade_out:.3f}:d={fade_out:.3f}"
            clip = os.path.join(tmp, f"cut_{i:04d}.mp4")
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                  "-i", cut["image"], "-vf", vf, "-frames:v", str(frames),
                  "-c:v", encoder, *enc_args, "-an", clip])
            clip_paths.append(clip)
            _log(f"[mvstudio] cut {i + 1}/{len(cuts)} "
                 f"({cut['preset']}, {dur:.2f}s)")

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")

        base = os.path.join(tmp, "base.mp4") if lyrics else output
        _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", concat_list,
              "-i", sb["audio"]["path"],
              "-map", "0:v:0", "-map", "1:a:0",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-af", f"afade=t=out:st={max(duration - 1.0, 0):.3f}:d=1.0",
              "-t", f"{duration:.3f}", "-movflags", "+faststart", base])

        if lyrics:
            _log(f"[mvstudio] burning {len(lyrics)} lyric lines")
            _overlay_lyrics(ffmpeg, encoder, enc_args, base, lyrics,
                            width, height, tmp, output)
    finally:
        if not keep_temp and workdir is None:
            shutil.rmtree(tmp, ignore_errors=True)
    return output


# One extra encode pass; kept separate so the lyric-free path stays a fast
# stream-copy concat. Still images stay available to `overlay` past their
# single frame via the filter's default eof_action=repeat.
def _overlay_lyrics(ffmpeg: str, encoder: str, enc_args: list[str],
                    base: str, lyrics: list[dict[str, Any]],
                    width: int, height: int, tmp: str, output: str) -> None:
    from .lyrics import render_line_png

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", base]
    png_index: dict[str, int] = {}
    for line in lyrics:
        if line["text"] not in png_index:
            path = os.path.join(tmp, f"lyric_{len(png_index):04d}.png")
            render_line_png(line["text"], width, height, path)
            png_index[line["text"]] = len(png_index) + 1  # input #0 is video
            cmd += ["-i", path]

    chain, src = [], "[0:v]"
    for i, line in enumerate(lyrics):
        idx = png_index[line["text"]]
        out_label = f"[v{i}]"
        chain.append(f"{src}[{idx}:v]overlay=0:0:"
                     f"enable='between(t,{line['start']},{line['end']})'"
                     f"{out_label}")
        src = out_label
    cmd += ["-filter_complex", ";".join(chain), "-map", src, "-map", "0:a",
            "-c:v", encoder, *enc_args, "-c:a", "copy",
            "-movflags", "+faststart", output]
    _run(cmd)

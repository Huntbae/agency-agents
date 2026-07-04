"""mvstudio CLI.

  mvstudio analyze SONG [-o analysis.json]
  mvstudio storyboard SONG IMAGE_DIR [-o storyboard.json] [--director rule|ollama]
  mvstudio render STORYBOARD -o out.mp4
  mvstudio make SONG IMAGE_DIR -o out.mp4      # analyze + storyboard + render
  mvstudio presets                             # list camera presets
  mvstudio doctor                              # env check + self-test render
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .analyze import analyze_audio
from .director import make_storyboard
from .images import scan_images
from .presets import load_presets
from .render import render
from .schema import load_storyboard, save_storyboard


def _add_output_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)


def _add_director_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--director", choices=["rule", "ollama"], default="rule",
                   help="storyboard director (ollama requires a local Ollama server)")
    p.add_argument("--model", default="qwen3:8b",
                   help="Ollama model for --director ollama")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--presets-file", default=None,
                   help="alternative camera_presets.json")
    p.add_argument("--lyrics", default=None, metavar="LRC",
                   help=".lrc file to burn as subtitles (see also: transcribe)")


def _check_inputs(args: argparse.Namespace) -> None:
    """Fail fast with a readable message instead of a backend traceback."""
    if not os.path.isfile(args.song):
        raise SystemExit(f"[mvstudio] song file not found: {args.song}\n"
                         "  (tip: drag the file into the terminal to paste its path)")
    if hasattr(args, "images") and not os.path.isdir(args.images):
        raise SystemExit(f"[mvstudio] image folder not found: {args.images}")
    if getattr(args, "lyrics", None) and not os.path.isfile(args.lyrics):
        raise SystemExit(f"[mvstudio] lyrics file not found: {args.lyrics}")


def _build_storyboard(args: argparse.Namespace) -> dict:
    _check_inputs(args)
    analysis = analyze_audio(args.song)
    images = scan_images(args.images)
    presets = load_presets(args.presets_file)
    print(f"[mvstudio] {os.path.basename(args.song)}: "
          f"{analysis['duration']:.1f}s, {analysis['bpm']:.0f} BPM, "
          f"{len(analysis['beats'])} beats, {len(analysis['sections'])} sections, "
          f"{len(images)} images")
    lyrics = None
    if getattr(args, "lyrics", None):
        from .lyrics import parse_lrc
        lyrics = parse_lrc(args.lyrics, duration=analysis["duration"])
        print(f"[mvstudio] {len(lyrics)} lyric lines from {args.lyrics}")
    return make_storyboard(analysis, images, presets,
                           width=args.width, height=args.height, fps=args.fps,
                           seed=args.seed, director=args.director,
                           model=args.model, lyrics=lyrics)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mvstudio",
                                     description="Local beat-synced music video engine (MVP)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="audio analysis -> JSON")
    p.add_argument("song")
    p.add_argument("-o", "--output", default=None)

    p = sub.add_parser("storyboard", help="song + images -> storyboard JSON")
    p.add_argument("song")
    p.add_argument("images")
    p.add_argument("-o", "--output", default="storyboard.json")
    _add_output_opts(p)
    _add_director_opts(p)

    p = sub.add_parser("render", help="storyboard JSON -> mp4")
    p.add_argument("storyboard")
    p.add_argument("-o", "--output", default="out.mp4")
    p.add_argument("--presets-file", default=None)
    p.add_argument("--keep-temp", action="store_true")

    p = sub.add_parser("make", help="analyze + storyboard + render in one go")
    p.add_argument("song")
    p.add_argument("images")
    p.add_argument("-o", "--output", default="out.mp4")
    p.add_argument("--keep-temp", action="store_true")
    _add_output_opts(p)
    _add_director_opts(p)

    sub.add_parser("presets", help="list camera presets")

    sub.add_parser("doctor", help="environment check + end-to-end self-test")

    p = sub.add_parser("transcribe",
                       help="extract lyrics to .lrc via whisper (pip install 'mvstudio[lyrics]')")
    p.add_argument("song")
    p.add_argument("-o", "--output", default=None, help="default: <song>.lrc")
    p.add_argument("--whisper-model", default="small",
                   help="tiny/base/small/medium/large-v3-turbo")
    p.add_argument("--language", default=None, help="e.g. ko, en (default: auto)")

    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        from .doctor import run_doctor
        return run_doctor()

    if args.cmd == "transcribe":
        from .transcribe import transcribe_to_lrc
        out = args.output or os.path.splitext(args.song)[0] + ".lrc"
        transcribe_to_lrc(args.song, out, model_size=args.whisper_model,
                          language=args.language)
        return 0

    if args.cmd == "analyze":
        result = analyze_audio(args.song)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"[mvstudio] wrote {args.output}")
        else:
            print(text)

    elif args.cmd == "storyboard":
        sb = _build_storyboard(args)
        save_storyboard(sb, args.output)
        print(f"[mvstudio] wrote {args.output} ({len(sb['cuts'])} cuts)")

    elif args.cmd == "render":
        presets = load_presets(args.presets_file)
        sb = load_storyboard(args.storyboard, known_presets=set(presets))
        out = render(sb, presets, args.output, keep_temp=args.keep_temp)
        print(f"[mvstudio] wrote {out}")

    elif args.cmd == "make":
        sb = _build_storyboard(args)
        sb_path = os.path.splitext(args.output)[0] + ".storyboard.json"
        save_storyboard(sb, sb_path)
        presets = load_presets(args.presets_file)
        out = render(sb, presets, args.output, keep_temp=args.keep_temp)
        print(f"[mvstudio] wrote {out} (+ {sb_path}, {len(sb['cuts'])} cuts)")

    elif args.cmd == "presets":
        for pid, spec in sorted(load_presets().items()):
            print(f"{pid:15s} tier={spec['tier']} z={spec['z']} "
                  f"energy={spec['energy']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

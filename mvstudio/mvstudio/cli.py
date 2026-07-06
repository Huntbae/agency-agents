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
from .generate import GenerationUnavailable
from .images import scan_images
from .presets import load_presets
from .render import RenderError, render
from .schema import StoryboardError, load_storyboard, save_storyboard


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
    p.add_argument("--match", choices=["auto", "semantic", "energy"],
                   default="auto",
                   help="image selection: semantic = local VLM matches photos "
                        "to lyrics/mood and drops unrelated ones (needs Ollama); "
                        "energy = brightness only; auto = semantic if available")
    p.add_argument("--vision-model", default="qwen3-vl:8b",
                   help="Ollama vision model for --match semantic/auto")
    p.add_argument("--visuals", choices=["photos", "generate"], default="photos",
                   help="generate = create images FROM the lyrics with a local "
                        "FLUX.2 model instead of using a photo folder "
                        "(pip install 'mvstudio[gen]')")
    p.add_argument("--style", default=None, metavar="TEXT",
                   help="visual style for --visuals generate, e.g. "
                        "'네온 야경, 시네마틱'")
    p.add_argument("--gen-model", default="flux2-klein-4b",
                   help="mflux model for --visuals generate")
    p.add_argument("--images-per-section", type=int, default=3)


def _check_inputs(args: argparse.Namespace) -> None:
    """Fail fast with a readable message instead of a backend traceback."""
    if not os.path.isfile(args.song):
        raise SystemExit(f"[mvstudio] song file not found: {args.song}\n"
                         "  (tip: drag the file into the terminal to paste its path)")
    generating = getattr(args, "visuals", "photos") == "generate"
    if hasattr(args, "images") and not generating and (
            args.images is None or not os.path.isdir(args.images)):
        raise SystemExit(
            f"[mvstudio] image folder not found: {args.images}\n"
            "  (or use --visuals generate to create images from the lyrics)")
    if getattr(args, "lyrics", None) and not os.path.isfile(args.lyrics):
        raise SystemExit(f"[mvstudio] lyrics file not found: {args.lyrics}")


def _build_storyboard(args: argparse.Namespace) -> dict:
    _check_inputs(args)
    analysis = analyze_audio(args.song)
    presets = load_presets(args.presets_file)
    print(f"[mvstudio] {os.path.basename(args.song)}: "
          f"{analysis['duration']:.1f}s, {analysis['bpm']:.0f} BPM, "
          f"{len(analysis['beats'])} beats, {len(analysis['sections'])} sections")
    lyrics = None
    if getattr(args, "lyrics", None):
        from .lyrics import parse_lrc
        lyrics = parse_lrc(args.lyrics, duration=analysis["duration"])
        print(f"[mvstudio] {len(lyrics)} lyric lines from {args.lyrics}")

    if getattr(args, "visuals", "photos") == "generate":
        from .generate import DEFAULT_STYLE, generate_visuals
        gen_dir = os.path.splitext(args.output)[0] + ".gen"
        _, pools = generate_visuals(
            analysis, lyrics, gen_dir,
            style=args.style or DEFAULT_STYLE,
            per_section=args.images_per_section,
            gen_model=args.gen_model, seed=args.seed,
            width=args.width, height=args.height)
        images = scan_images(gen_dir)
        print(f"[mvstudio] generated {len(images)} images from the lyrics "
              f"-> {gen_dir}/")
        return make_storyboard(analysis, images, presets,
                               width=args.width, height=args.height,
                               fps=args.fps, seed=args.seed,
                               director=args.director, model=args.model,
                               lyrics=lyrics, pools=pools)

    images = scan_images(args.images)
    print(f"[mvstudio] {len(images)} images from {args.images}")

    pools = None
    match = getattr(args, "match", "auto")
    if match != "energy":
        from .semantic import SemanticUnavailable, semantic_match
        try:
            pools, excluded = semantic_match(
                analysis, images, lyrics,
                vision_model=args.vision_model, text_model=args.model)
            print(f"[mvstudio] semantic match: {len(excluded)}/{len(images)} "
                  "photos excluded as unrelated to the song")
            for path in excluded:
                print(f"[mvstudio]   excluded: {os.path.basename(path)}")
        except SemanticUnavailable as exc:
            if match == "semantic":
                raise SystemExit(f"[mvstudio] semantic matching unavailable:\n{exc}")
            print(f"[mvstudio] semantic matching unavailable, using energy "
                  f"matching. To enable:\n{exc}")

    return make_storyboard(analysis, images, presets,
                           width=args.width, height=args.height, fps=args.fps,
                           seed=args.seed, director=args.director,
                           model=args.model, lyrics=lyrics, pools=pools)


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch, turning expected failures into one-line
    messages instead of tracebacks."""
    try:
        return _dispatch(argv)
    except (FileNotFoundError, StoryboardError, RenderError,
            GenerationUnavailable) as exc:
        print(f"[mvstudio] error: {exc}", file=sys.stderr)
        return 1


def _dispatch(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mvstudio",
                                     description="Local beat-synced music video engine (MVP)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="audio analysis -> JSON")
    p.add_argument("song")
    p.add_argument("-o", "--output", default=None)

    p = sub.add_parser("storyboard", help="song + images -> storyboard JSON")
    p.add_argument("song")
    p.add_argument("images", nargs="?", default=None,
                   help="photo folder (optional with --visuals generate)")
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
    p.add_argument("images", nargs="?", default=None,
                   help="photo folder (optional with --visuals generate)")
    p.add_argument("-o", "--output", default="out.mp4")
    p.add_argument("--keep-temp", action="store_true")
    _add_output_opts(p)
    _add_director_opts(p)

    sub.add_parser("presets", help="list camera presets")

    sub.add_parser("doctor", help="environment check + end-to-end self-test")

    p = sub.add_parser("demo", help="generate showcase assets and render a "
                                    "full demo video in one go")
    p.add_argument("-o", "--outdir", default="mvstudio-demo")

    p = sub.add_parser("place-clip",
                       help="composite a video clip (e.g. lip-synced portrait) "
                            "over one section of a storyboard")
    p.add_argument("storyboard")
    p.add_argument("video")
    p.add_argument("--section", type=int, default=None,
                   help="section index (see the storyboard's sections)")
    p.add_argument("--label", default=None,
                   help="or first section with this label (default: high)")
    p.add_argument("--video-offset", type=float, default=0.0,
                   help="seconds to skip from the clip start")
    p.add_argument("-o", "--output", default=None,
                   help="default: overwrite the storyboard in place")

    p = sub.add_parser("section-audio",
                       help="export one section's audio (feed it to a "
                            "lip-sync tool so the mouth matches the song)")
    p.add_argument("song")
    p.add_argument("storyboard")
    p.add_argument("--section", type=int, required=True)
    p.add_argument("-o", "--output", default="section.wav")

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

    if args.cmd == "demo":
        from .demo import make_scene_images, make_showcase_lrc, make_showcase_song
        from .lyrics import parse_lrc
        os.makedirs(args.outdir, exist_ok=True)
        song = make_showcase_song(os.path.join(args.outdir, "song.wav"))
        images_dir = make_scene_images(os.path.join(args.outdir, "photos"))
        lrc = make_showcase_lrc(os.path.join(args.outdir, "song.lrc"))
        print(f"[mvstudio] showcase assets -> {args.outdir}/")
        analysis = analyze_audio(song)
        lyrics = parse_lrc(lrc, duration=analysis["duration"])
        presets = load_presets()
        sb = make_storyboard(analysis, scan_images(images_dir), presets,
                             width=1280, height=720, fps=30, seed=42,
                             lyrics=lyrics)
        out = os.path.join(args.outdir, "demo.mp4")
        save_storyboard(sb, os.path.join(args.outdir, "demo.storyboard.json"))
        render(sb, presets, out)
        print(f"[mvstudio] wrote {out} ({len(sb['cuts'])} cuts, "
              f"{analysis['duration']:.0f}s)")
        return 0

    if args.cmd == "place-clip":
        from .clips import place_clip
        presets = load_presets()
        sb = load_storyboard(args.storyboard, known_presets=set(presets))
        if not os.path.isfile(args.video):
            raise FileNotFoundError(f"video not found: {args.video}")
        sb = place_clip(sb, os.path.abspath(args.video), section=args.section,
                        label=args.label, video_offset=args.video_offset,
                        known_presets=set(presets))
        out = args.output or args.storyboard
        save_storyboard(sb, out)
        clip_cut = next(c for c in sb["cuts"] if c.get("video"))
        print(f"[mvstudio] clip placed at {clip_cut['start']:.1f}-"
              f"{clip_cut['end']:.1f}s -> {out}")
        return 0

    if args.cmd == "section-audio":
        from .clips import export_section_audio
        presets = load_presets()
        sb = load_storyboard(args.storyboard, known_presets=set(presets))
        if not os.path.isfile(args.song):
            raise FileNotFoundError(f"song file not found: {args.song}")
        out = export_section_audio(args.song, sb, args.section, args.output)
        s = sb["sections"][args.section]
        print(f"[mvstudio] section {args.section} ({s['start']:.1f}-"
              f"{s['end']:.1f}s, {s.get('label')}) audio -> {out}")
        return 0

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

"""`mvstudio doctor`: environment checks + end-to-end self-test.

Meant to be the single command a user runs right after installing on a new
machine (especially a Mac) to confirm the whole pipeline works before
trying their own songs. Environment problems are reported as WARN and the
run continues; the self-test render is the pass/fail core.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

_RESULTS: list[tuple[str, str]] = []


def _report(level: str, msg: str) -> None:
    _RESULTS.append((level, msg))
    print(f"[{level}] {msg}", flush=True)


def _media_duration(ffmpeg: str, path: str) -> float | None:
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                           capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _check_environment() -> None:
    _report("INFO", f"python {platform.python_version()} on "
                    f"{platform.system()} {platform.machine()}")
    if sys.version_info < (3, 10):
        _report("FAIL", "Python >= 3.10 required")

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        _report("PASS", "Apple Silicon detected")

    try:
        page = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        ram_gb = page / 1e9
        _report("INFO", f"RAM: {ram_gb:.0f} GB")
        if ram_gb < 15:
            _report("WARN", "under 16GB RAM: core editing features only; "
                            "AI video clip generation (Phase 3) will be gated off")
        elif ram_gb < 31:
            _report("INFO", "16GB tier: core features OK; Wan2.2 clip "
                            "generation will need the 32GB tier")
        else:
            _report("PASS", "32GB+ tier: full feature set planned for this machine")
    except (ValueError, OSError):
        _report("INFO", "RAM size: could not determine")

    free_gb = shutil.disk_usage(os.path.expanduser("~")).free / 1e9
    level = "PASS" if free_gb >= 60 else "WARN"
    _report(level, f"disk free: {free_gb:.0f} GB "
                   f"(60+ GB recommended once AI models are added)")

    for mod in ("librosa", "soundfile", "numpy", "PIL"):
        try:
            __import__(mod)
            _report("PASS", f"dependency: {mod}")
        except ImportError as exc:
            _report("FAIL", f"dependency missing: {mod} ({exc})")

    try:
        __import__("mcp")
        _report("PASS", "mcp SDK installed (mvstudio-mcp available)")
    except ImportError:
        _report("INFO", "mcp SDK not installed — `pip install 'mvstudio[mcp]'` "
                        "to use the MCP server (optional)")

    from .render import RenderError, find_ffmpeg, pick_encoder
    try:
        ffmpeg = find_ffmpeg()
        version = subprocess.run([ffmpeg, "-version"], capture_output=True,
                                 text=True).stdout.splitlines()[0]
        _report("PASS", f"ffmpeg: {ffmpeg}")
        _report("INFO", version)
        encoder, _ = pick_encoder(ffmpeg)
        if encoder == "h264_videotoolbox":
            _report("PASS", "encoder: h264_videotoolbox (Apple hardware, LGPL-safe)")
        elif encoder == "libx264":
            _report("WARN", "encoder: libx264 (GPL build — OK for personal use, "
                            "not for commercial distribution)")
        else:
            _report("INFO", f"encoder: {encoder}")
    except RenderError as exc:
        _report("FAIL", str(exc))

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags",
                                    timeout=2) as resp:
            models = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        _report("PASS", f"ollama server running ({len(models)} models) — "
                        "`--director ollama` available")
    except Exception:
        _report("INFO", "ollama not reachable — rule director only "
                        "(optional; install Ollama + `ollama pull qwen3:8b` for the LLM director)")


def _self_test() -> None:
    from .analyze import analyze_audio
    from .demo import make_images, make_song
    from .director import make_storyboard
    from .images import scan_images
    from .presets import load_presets
    from .render import find_ffmpeg, render

    tmp = tempfile.mkdtemp(prefix="mvstudio-doctor-")
    try:
        song = make_song(os.path.join(tmp, "demo.wav"), bars=4)  # 8 seconds
        images = make_images(os.path.join(tmp, "images"), count=4)
        _report("PASS", "self-test: demo assets synthesized")

        analysis = analyze_audio(song)
        _report("PASS", f"self-test: analysis ({analysis['bpm']:.0f} BPM, "
                        f"{len(analysis['beats'])} beats, "
                        f"{len(analysis['sections'])} sections)")

        presets = load_presets()
        _report("PASS", f"self-test: {len(presets)} camera presets loaded "
                        "(package data)")

        sb = make_storyboard(analysis, scan_images(images), presets,
                             width=480, height=270, fps=24, seed=1)
        _report("PASS", f"self-test: storyboard ({len(sb['cuts'])} cuts)")

        out = os.path.join(tmp, "doctor.mp4")
        render(sb, presets, out)
        size = os.path.getsize(out)
        got = _media_duration(find_ffmpeg(), out)
        if size > 10_000 and got and abs(got - analysis["duration"]) < 0.5:
            _report("PASS", f"self-test: rendered {size // 1024} KB, "
                            f"{got:.1f}s (expected {analysis['duration']:.1f}s)")
        else:
            _report("FAIL", f"self-test: render suspicious "
                            f"(size={size}, duration={got})")
    except Exception as exc:
        _report("FAIL", f"self-test: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_doctor() -> int:
    print("mvstudio doctor — environment check + end-to-end self-test\n")
    _RESULTS.clear()
    _check_environment()
    print()
    _self_test()

    fails = [m for lv, m in _RESULTS if lv == "FAIL"]
    warns = [m for lv, m in _RESULTS if lv == "WARN"]
    print()
    if fails:
        print(f"RESULT: FAIL ({len(fails)} problem(s))")
        for m in fails:
            print(f"  - {m}")
        return 1
    print(f"RESULT: OK{f' ({len(warns)} warning(s))' if warns else ''}")
    print("Next: mvstudio make your_song.mp3 your_photos/ -o out.mp4")
    return 0

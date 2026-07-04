"""Optional lyric transcription via faster-whisper (MIT; Whisper weights MIT).

Install with:  pip install "mvstudio[lyrics]"

NOTE: the model call itself cannot run in the CI/dev container (model
downloads are blocked there), so `segments_to_lrc` — the logic — is kept
pure and unit-tested, while `transcribe_to_lrc` is a thin documented
wrapper to verify on a real machine (`mvstudio transcribe song.mp3`).
"""

from __future__ import annotations

import sys
from typing import Any, Iterable


def segments_to_lrc(segments: Iterable[Any]) -> str:
    """Convert whisper-style segments (objects or dicts with .start/.text)
    into LRC text. Pure function; testable without a model."""
    lines = []
    for seg in segments:
        start = seg["start"] if isinstance(seg, dict) else seg.start
        text = (seg["text"] if isinstance(seg, dict) else seg.text).strip()
        if not text:
            continue
        minutes, seconds = divmod(max(float(start), 0.0), 60.0)
        lines.append(f"[{int(minutes):02d}:{seconds:05.2f}] {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def transcribe_to_lrc(audio_path: str, out_path: str,
                      model_size: str = "small",
                      language: str | None = None) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(
            "faster-whisper not installed. Run: pip install 'mvstudio[lyrics]'")

    print(f"[mvstudio] loading whisper '{model_size}' (first run downloads "
          "the model)", file=sys.stderr, flush=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, language=language,
                                      vad_filter=True)
    lrc = segments_to_lrc(segments)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(lrc)
    n = lrc.count("\n")
    print(f"[mvstudio] {n} lines -> {out_path} "
          f"(language: {info.language})", file=sys.stderr, flush=True)
    if n == 0:
        print("[mvstudio] no vocals detected — is this an instrumental?",
              file=sys.stderr, flush=True)
    return out_path

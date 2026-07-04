"""Audio analysis: BPM, beat grid, per-beat energy, section segmentation.

librosa only (ISC license). Deliberately avoids madmom/Essentia/aubio,
whose models or code are non-commercial/GPL licensed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

SR = 22050
FALLBACK_BPM = 120.0


def analyze_audio(path: str, max_sections: int = 12) -> dict[str, Any]:
    import os
    if not os.path.isfile(path):
        raise FileNotFoundError(f"audio file not found: {path}")

    import librosa  # deferred: heavy import

    y, sr = librosa.load(path, sr=SR, mono=True)
    duration = float(len(y) / sr)

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, trim=False)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 0.0

    # Degenerate audio (silence, drones): fall back to a uniform grid so the
    # rest of the pipeline always has beats to snap to.
    if len(beat_times) < 4 or bpm <= 0:
        bpm = FALLBACK_BPM
        beat_times = np.arange(0.0, duration, 60.0 / bpm)

    # Per-beat energy from RMS, normalized to 0..1.
    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    beat_energy = np.interp(beat_times, rms_times, rms)
    lo, hi = float(beat_energy.min()), float(beat_energy.max())
    beat_energy = (beat_energy - lo) / (hi - lo) if hi > lo else np.full_like(beat_energy, 0.5)

    sections = _segment(y, sr, beat_times, beat_energy, duration, max_sections)

    return {
        "path": path,
        "duration": round(duration, 3),
        "bpm": round(bpm, 2),
        "beats": [round(float(t), 3) for t in beat_times],
        "beat_energy": [round(float(e), 3) for e in beat_energy],
        "sections": sections,
    }


def _segment(y: np.ndarray, sr: int, beat_times: np.ndarray,
             beat_energy: np.ndarray, duration: float,
             max_sections: int) -> list[dict[str, Any]]:
    """Split the song into sections whose boundaries land on beats."""
    import librosa

    k = int(np.clip(round(duration / 20.0), 2, max_sections))

    boundaries: list[float]
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        feats = np.vstack([mfcc, chroma])
        # Beat-synchronous features keep segmentation aligned with the grid.
        beat_frames = librosa.time_to_frames(beat_times, sr=sr)
        sync = librosa.util.sync(feats, beat_frames, aggregate=np.mean)
        if sync.shape[1] <= k:
            raise ValueError("too few beats to segment")
        # agglomerative returns the k left-boundary indices (first is 0)
        # into the beat-synchronous frames, not per-frame segment ids.
        bounds = librosa.segment.agglomerative(sync, k)
        boundaries = [float(beat_times[min(int(i), len(beat_times) - 1)])
                      for i in bounds[1:]]
    except Exception:
        boundaries = [duration * i / k for i in range(1, k)]

    edges = [0.0] + sorted(boundaries) + [duration]
    sections = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end - start < 1.0:
            continue
        mask = (beat_times >= start) & (beat_times < end)
        energy = float(beat_energy[mask].mean()) if mask.any() else 0.5
        sections.append({"start": round(start, 3), "end": round(end, 3),
                         "energy": round(energy, 3)})
    if not sections:
        sections = [{"start": 0.0, "end": round(duration, 3), "energy": 0.5}]
    # Re-stitch so sections are contiguous after the <1s filter.
    sections[0]["start"] = 0.0
    for prev, cur in zip(sections[:-1], sections[1:]):
        cur["start"] = prev["end"]
    sections[-1]["end"] = round(duration, 3)

    tertiles = np.quantile([s["energy"] for s in sections], [1 / 3, 2 / 3])
    for s in sections:
        s["label"] = ("low" if s["energy"] <= tertiles[0]
                      else "high" if s["energy"] >= tertiles[1] else "mid")
    return sections

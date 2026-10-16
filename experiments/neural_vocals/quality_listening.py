"""Make a fair seven-way Phase 4B-2 listening set without changing raw outputs."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.app.audio.vocal_pitch import read_vocal_wav, vocal_levels
from backend.app.audio.vocal_quality import match_loudness

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = (ROOT / "runs").resolve()
    baseline, candidate, output = (p.resolve() for p in (args.baseline, args.candidate, args.output))
    if any(not p.is_relative_to(runs) for p in (baseline, candidate, output)) or output.exists():
        parser.error("Use a new output directory inside the experiment runs")
    sources = {
        "A_original": baseline / "original_vocals.wav",
        "B_rubberband_plus_3": baseline / "rubberband_plus_3.wav",
        "C_neural_baseline_plus_3": baseline / "neural_plus_3.wav",
        "D_neural_candidate_plus_3": candidate / "neural_plus_3.wav",
        "E_rubberband_minus_3": baseline / "rubberband_minus_3.wav",
        "F_neural_baseline_minus_3": baseline / "neural_minus_3.wav",
        "G_neural_candidate_minus_3": candidate / "neural_minus_3.wav",
    }
    original, rate = read_vocal_wav(sources["A_original"])
    tracks = {}
    native = {}
    for label, path in sources.items():
        audio, track_rate = read_vocal_wav(path)
        if track_rate != rate or audio.shape[1] != original.shape[1] or abs(len(audio) - len(original)) > 2205:
            raise ValueError(f"Incompatible raw candidate: {label}")
        native[label] = {"source": str(path), **asdict(vocal_levels(audio, rate)),
                         "frame_difference": len(audio) - len(original)}
        aligned = np.zeros_like(original)
        aligned[:min(len(audio), len(original))] = audio[:len(original)]
        fade = min(round(0.005 * rate), len(original) // 2)
        aligned[:fade] *= np.linspace(0, 1, fade)[:, None]
        aligned[-fade:] *= np.linspace(1, 0, fade)[:, None]
        tracks[label] = aligned
    matched, loudness = match_loudness(tracks, rate)
    output.mkdir(parents=True, exist_ok=False)
    for label, audio in matched.items():
        if not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) >= 1:
            raise ValueError(f"Invalid or clipped matched candidate: {label}")
        sf.write(output / f"{label}.wav", audio, rate, subtype="PCM_24")
    report = {
        "baseline": str(baseline), "candidate": str(candidate),
        "selection": "Provisional 40-step candidate for blinded human review; no perceptual superiority claimed",
        "native": native, "loudness": loudness,
        "processing": "Mono PCM24, original duration, end-pad at most 408 native neural frames, common 5-ms endpoint fades; no time warp or onset shift",
        "listening_review": "PENDING",
    }
    with (output / "manifest.json").open("x", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, allow_nan=False)
    print(output)


if __name__ == "__main__":
    main()

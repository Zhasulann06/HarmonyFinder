"""Create matched-loudness Phase 4C-2 comparisons, preserving every raw file."""

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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = (ROOT / "runs").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(runs) or output.exists():
        parser.error("Use a new listening-set directory inside experiments/neural_vocals/runs")
    prior = runs / "dynamic-listening-20261017T0000"
    sources = {
        "A_original": prior / "A_original.wav",
        "B_previous_dynamic_plus": prior / "C_dynamic_plus_3_4.wav",
        "C_previous_dynamic_minus": prior / "E_dynamic_minus_3_4.wav",
    }
    for direction in ("above", "below"):
        for treatment in ("baseline80", "short30"):
            run = runs / f"harmony-{direction}-{treatment}-20261017"
            label = f"harmony_{direction}_{treatment}"
            sources[f"{direction}_{treatment}"] = run / f"{label}.wav"
    sources["above_motion30"] = (runs / "harmony-above-motion30-20261017"
                                  / "harmony_above_motion30.wav")
    original, rate = read_vocal_wav(sources["A_original"])
    aligned, native = {}, {}
    for label, path in sources.items():
        audio, candidate_rate = read_vocal_wav(path)
        if candidate_rate != rate or audio.shape[1] != original.shape[1] or abs(len(audio) - len(original)) > 2205:
            raise ValueError(f"Incompatible comparison WAV: {path}")
        native[label] = {"source": str(path), **asdict(vocal_levels(audio, rate)),
                         "frame_difference": len(audio) - len(original)}
        aligned_audio = np.zeros_like(original)
        aligned_audio[:min(len(audio), len(original))] = audio[:len(original)]
        fade = min(round(0.005 * rate), len(original) // 2)
        aligned_audio[:fade] *= np.linspace(0, 1, fade)[:, None]
        aligned_audio[-fade:] *= np.linspace(1, 0, fade)[:, None]
        aligned[label] = aligned_audio
    matched, loudness = match_loudness(aligned, rate)
    if any(not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) >= 1
           for audio in matched.values()):
        raise ValueError("Matched output contains non-finite or clipped samples")
    output.mkdir(parents=True, exist_ok=False)
    for label, audio in matched.items():
        sf.write(output / f"{label}.wav", audio, rate, subtype="PCM_24")
    with (output / "manifest.json").open("x", encoding="utf-8") as destination:
        json.dump({"sources": native, "loudness": loudness,
                   "processing": "Common 5-ms endpoint fades, neural end padding to 6 s only; no onset shift or time warp",
                   "listening_review": "PENDING: user must compare transitions and harmony plausibility"},
                  destination, indent=2, allow_nan=False)
    print(output)


if __name__ == "__main__":
    main()

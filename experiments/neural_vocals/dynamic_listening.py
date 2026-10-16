"""Create a matched-loudness constant-versus-dynamic neural listening set."""

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
    parser.add_argument("--constant-run", type=Path, required=True)
    parser.add_argument("--dynamic-plus", type=Path, required=True)
    parser.add_argument("--dynamic-minus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = (ROOT / "runs").resolve()
    constant, plus, minus, output = (p.resolve() for p in
                                     (args.constant_run, args.dynamic_plus, args.dynamic_minus, args.output))
    if any(not p.is_relative_to(runs) for p in (constant, plus, minus, output)) or output.exists():
        parser.error("Use existing experiment runs and a new output directory within runs")
    sources = {
        "A_original": constant / "original_vocals.wav",
        "B_constant_plus_3": constant / "neural_plus_3.wav",
        "C_dynamic_plus_3_4": plus / "dynamic_plus_3_4.wav",
        "D_constant_minus_3": constant / "neural_minus_3.wav",
        "E_dynamic_minus_3_4": minus / "dynamic_minus_3_4.wav",
    }
    original, rate = read_vocal_wav(sources["A_original"])
    aligned = {}
    raw_levels = {}
    for name, path in sources.items():
        audio, candidate_rate = read_vocal_wav(path)
        if candidate_rate != rate or audio.shape[1] != original.shape[1] or abs(len(audio) - len(original)) > 2205:
            raise ValueError(f"Incompatible comparison WAV: {path}")
        raw_levels[name] = {"source": str(path), **asdict(vocal_levels(audio, rate)),
                            "frame_difference": len(audio) - len(original)}
        copy = np.zeros_like(original)
        copy[:min(len(audio), len(original))] = audio[:len(original)]
        fade = min(round(0.005 * rate), len(original) // 2)
        copy[:fade] *= np.linspace(0, 1, fade)[:, None]
        copy[-fade:] *= np.linspace(1, 0, fade)[:, None]
        aligned[name] = copy
    matched, loudness = match_loudness(aligned, rate)
    if any(not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) >= 1 for audio in matched.values()):
        raise ValueError("Comparison output invalid or clipped")
    output.mkdir(parents=True, exist_ok=False)
    for name, audio in matched.items():
        sf.write(output / f"{name}.wav", audio, rate, subtype="PCM_24")
    with (output / "manifest.json").open("x", encoding="utf-8") as destination:
        json.dump({"sources": raw_levels, "loudness": loudness,
                   "processing": "Common 5-ms endpoint fades and end padding to source duration only; no time warp or onset shift",
                   "listening_review": "PENDING"}, destination, indent=2, allow_nan=False)
    print(output)


if __name__ == "__main__":
    main()

"""Frame-aligned pYIN diagnostics for the isolated six-second vocal experiment."""

import argparse
import json
from pathlib import Path

import numpy as np

from backend.app.audio.pitch import PyinPitchDetector


def summarize(source, output, shift: int, start: float, end: float) -> dict:
    pairs = [(a, b) for a, b in zip(source.frames, output.frames)
             if start <= a.time_seconds < end]
    common = [(a, b) for a, b in pairs if a.voiced and b.voiced
              and a.midi_pitch is not None and b.midi_pitch is not None]
    errors = np.array([100 * (b.midi_pitch - a.midi_pitch - shift) for a, b in common])
    return {
        "start_seconds": start, "end_seconds": end,
        "source_voiced_frames": sum(a.voiced for a, _ in pairs),
        "output_voiced_frames": sum(b.voiced for _, b in pairs),
        "common_voiced_frames": len(common),
        "source_voiced_output_unvoiced": sum(a.voiced and not b.voiced for a, b in pairs),
        "source_unvoiced_output_voiced": sum(not a.voiced and b.voiced for a, b in pairs),
        "median_signed_error_cents": float(np.median(errors)) if len(errors) else None,
        "median_absolute_error_cents": float(np.median(abs(errors))) if len(errors) else None,
        "p90_absolute_error_cents": float(np.percentile(abs(errors), 90)) if len(errors) else None,
        "frames_over_100_cents": int(np.sum(abs(errors) > 100)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--variant", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(
            (Path(__file__).resolve().parent / "runs").resolve()):
        parser.error("Write a new JSON file inside experiments/neural_vocals/runs")
    detector = PyinPitchDetector()
    source_path = args.baseline / "original_vocals.wav"
    source = detector.detect(source_path)
    reference = detector.detect(args.baseline / "reference_same_singer.wav")
    candidates = {}
    for run in [args.baseline, *args.variant]:
        for shift, suffix in ((3, "plus_3"), (-3, "minus_3")):
            path = run / f"neural_{suffix}.wav"
            contour = detector.detect(path)
            candidates[f"{run.name}/{suffix}"] = {
                "path": str(path),
                "whole": summarize(source, contour, shift, 0.0, 6.0),
                "one_second_bins": [summarize(source, contour, shift, t, t + 1.0)
                                    for t in range(6)],
            }
    reference_voiced = [f.f0_hz for f in reference.frames if f.voiced and f.f0_hz is not None]
    source_voiced = [f.f0_hz for f in source.frames if f.voiced and f.f0_hz is not None]
    result = {
        "source": str(source_path),
        "source_voiced_f0_median_hz": float(np.median(source_voiced)),
        "reference_voiced_f0_median_hz": float(np.median(reference_voiced)),
        "candidates": candidates,
        "scope": "pYIN 10-ms frame estimates, no transcript or ground-truth pitch; voiced mismatches do not measure lyric intelligibility",
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
    print(args.output)


if __name__ == "__main__":
    main()

"""Generate and measure +/-3-semitone vocals from an existing WAV, offline."""

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np

from backend.app.audio.pitch import PyinPitchDetector
from backend.app.audio.vocal_pitch import RubberBandVocalPitchShifter, read_vocal_wav, vocal_levels
from backend.app.core.config import resolve_project_path


def envelope_lag(source: np.ndarray, shifted: np.ndarray, rate: int) -> float:
    """Coarse energy-envelope offset, not a guarantee of individual syllable timing."""
    hop = round(rate * 0.01)
    length = len(source) // hop * hop
    def energy(audio: np.ndarray) -> np.ndarray:
        blocks = audio[:length].astype(np.float64).reshape(-1, hop, audio.shape[1])
        rms = np.sqrt(np.mean(blocks ** 2, axis=(1, 2)))
        return rms - rms.mean()
    a, b = energy(source), energy(shifted)
    if np.linalg.norm(a) < 1e-9 or np.linalg.norm(b) < 1e-9:
        return 0.0
    lags = range(-25, 26)
    scores = [float(np.dot(a[max(0, -lag):len(a) - max(0, lag)],
                           b[max(0, lag):len(b) - max(0, -lag)])) for lag in lags]
    return list(lags)[int(np.argmax(scores))] * hop / rate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Separated vocal WAV, relative to project root or absolute")
    parser.add_argument("--output", default="backend/data/vocal_pitch_comparison")
    args = parser.parse_args()
    source, output = resolve_project_path(args.input), resolve_project_path(args.output)
    if source.parent == output or source.parent in output.parents:
        parser.error("Use a comparison directory outside the source job")
    original, rate = read_vocal_wav(source)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output / "original_vocals.wav")
    shifter = RubberBandVocalPitchShifter()
    reports = {}
    for semitones, name in ((3, "vocals_plus_3.wav"), (-3, "vocals_minus_3.wav")):
        report = shifter.shift(source, output / name, semitones)
        reports[name] = asdict(report)
        shifted, _ = read_vocal_wav(output / name)
        reports[name]["energy_envelope_lag_seconds"] = envelope_lag(original, shifted, rate)
        print(f"Generated {name}: {report.processing_seconds:.3f}s processing", flush=True)
    # Reuse pYIN only for evaluation; the shifter has no pitch-detection dependency.
    detector = PyinPitchDetector()
    baseline = detector.detect(source)
    for semitones, name in ((3, "vocals_plus_3.wav"), (-3, "vocals_minus_3.wav")):
        analysis = detector.detect(output / name)
        differences = [b.midi_pitch - a.midi_pitch for a, b in zip(baseline.frames, analysis.frames)
                       if a.voiced and b.voiced and a.midi_pitch is not None and b.midi_pitch is not None]
        if not differences:
            raise RuntimeError("No shared voiced frames available to verify pitch direction")
        offset = float(np.median(differences))
        reports[name]["median_detected_shift_semitones"] = offset
        reports[name]["matched_voiced_frames"] = len(differences)
        if abs(offset - semitones) > 0.5:
            raise RuntimeError(f"Pitch direction/magnitude check failed for {name}: {offset}")
        if abs(reports[name]["energy_envelope_lag_seconds"]) > 0.03:
            raise RuntimeError(f"Energy-envelope timing check failed for {name}")
    results = {"source_job": source.parent.name, "original_vocals.wav": asdict(vocal_levels(original, rate)),
               "shifts": reports,
               "limitations": "Technical checks are not listening verification of lyrics, speaker identity, naturalness, formants, or syllable-level timing."}
    (output / "measurements.json").write_text(json.dumps(results, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

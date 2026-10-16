"""Controlled perturbations; label changes are sensitivity, not accuracy."""

import argparse
import json
from pathlib import Path

import numpy as np

from experiments.chord_recognition.detector import ANALYSIS_RATE, detect, load_audio

ROOT = Path(__file__).resolve().parent


def synth_triad(pitches: tuple[int, int, int], seconds: float,
                overtone: float = 0.15) -> np.ndarray:
    t = np.arange(round(seconds * ANALYSIS_RATE)) / ANALYSIS_RATE
    signal = np.zeros_like(t)
    for pitch in pitches:
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        for partial, strength in ((1, 1), (2, overtone), (3, overtone / 2)):
            signal += strength * np.sin(2 * np.pi * frequency * partial * t)
    return np.asarray(signal / 5 * np.exp(-0.5 * t), dtype=np.float32)


def compare_frames(reference: list, candidate: list) -> dict:
    if len(reference) != len(candidate):
        raise ValueError("Comparison must share a frame grid")
    changed = sum(a.label != b.label for a, b in zip(reference, candidate))
    fixed = [(a.label, b.label) for a, b in zip(reference, candidate)
             if a.label not in {"ambiguous", "no_chord"}]
    return {"changed_frames": changed, "total_frames": len(reference),
            "change_fraction": changed / len(reference) if reference else None,
            "confident_reference_changed": sum(a != b for a, b in fixed),
            "reference_chord_frames": len(fixed)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrumental", type=Path, required=True)
    parser.add_argument("--vocals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new JSON under experiments/chord_recognition/runs")
    instrumental, rate = load_audio(args.instrumental.resolve())
    vocals, vocal_rate = load_audio(args.vocals.resolve())
    if rate != vocal_rate or len(instrumental) != len(vocals):
        raise ValueError("Synchronized Demucs stems required")
    baseline, _, _ = detect(instrumental, rate)
    rng = np.random.default_rng(321)
    percussive = instrumental.copy()
    for start in np.arange(0.5, len(instrumental) / rate, 0.5):
        index = round(start * rate)
        n = min(1200, len(percussive) - index)
        percussive[index:index + n] += (0.11 * rng.standard_normal(n) *
                                         np.exp(-np.arange(n) / 180)).astype(np.float32)
    t = np.arange(len(instrumental)) / rate
    bass = instrumental + (0.07 * np.sin(2 * np.pi * 73.416 * t)).astype(np.float32)
    perturbed = {
        "added_25_percent_vocal_stem": instrumental + 0.25 * vocals,
        "added_D2_bass_sine_0.07_peak": bass,
        "added_0.5s_percussion_bursts": percussive,
    }
    real = {}
    for name, signal in perturbed.items():
        candidate, _, _ = detect(signal, rate)
        real[name] = compare_frames(baseline, candidate)
    # Controlled synthetic probes: clean progression, overtone-rich plucks,
    # and four 250-ms chords to expose the 500-ms analysis resolution limit.
    sequence = [("C:major", (60, 64, 67)), ("A:minor", (57, 60, 64)),
                ("G:major", (55, 59, 62)), ("D:major", (62, 66, 69))]
    synthetic = {}
    for overtone in (0.15, 0.7):
        audio = np.concatenate([synth_triad(notes, 1.0, overtone) for _, notes in sequence])
        frames, _, _ = detect(audio, rate)
        centers = [frames[round((index + 0.5) / 0.5)].label for index in range(4)]
        synthetic[f"overtone_{overtone}"] = {
            "expected": [name for name, _ in sequence], "observed": centers,
            "correct": sum(a == b for a, b in zip(centers, [name for name, _ in sequence]))}
    short_audio = np.concatenate([synth_triad(notes, 0.25) for _, notes in sequence])
    short_frames, _, _ = detect(short_audio, rate)
    synthetic["four_250ms_chords"] = {"expected": [name for name, _ in sequence],
                                      "observed_500ms_bins": [frame.label for frame in short_frames],
                                      "limitation": "Four 250-ms changes cannot be resolved in two 500-ms bins"}
    report = {"real_stem_sensitivity": real, "synthetic_probes": synthetic,
              "caution": "Real-stem labels have no ground truth. Perturbation label changes measure instability, not chord accuracy. Added vocal/bass/percussion signals are controlled hypothetical contaminants, not measured Demucs leakage."}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

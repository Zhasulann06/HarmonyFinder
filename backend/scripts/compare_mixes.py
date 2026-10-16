"""Reproducible, offline comparison using existing real job artifacts."""

import argparse
import json
from pathlib import Path

import numpy as np

from backend.app.audio.mixing import load_stereo, mix_preview
from backend.app.audio.stem_mixer import mix_stems, signal_levels
from backend.app.core.config import resolve_project_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, help="Existing job directory relative to project root or absolute")
    parser.add_argument("--output", help="Comparison directory; original artifacts are never modified")
    args = parser.parse_args()
    job = resolve_project_path(args.job)
    original = next((job / name for name in ("original.wav", "original.mp3") if (job / name).is_file()), None)
    if original is None:
        parser.error("No original audio found")
    for name in ("vocals.wav", "instrumental.wav", "harmony_piano.wav"):
        if not (job / name).is_file():
            parser.error(f"Missing {name}")
    output = resolve_project_path(args.output or f"backend/data/mix_comparison/{job.name}")
    if output == job or job in output.parents:
        parser.error("Use an output directory outside the source job")
    output.mkdir(parents=True, exist_ok=True)
    piano, vocals, instrumental = (job / name for name in ("harmony_piano.wav", "vocals.wav", "instrumental.wav"))
    mix_preview(original, piano, output / "previous_mix.wav", 0.8, 0.6)
    forward = mix_stems(instrumental, vocals, piano, output / "harmony_forward.wav")
    balanced = mix_stems(instrumental, vocals, piano, output / "balanced.wav", 0.85, 0.70, 4)
    before = signal_levels(load_stereo(output / "previous_mix.wav"))
    # Old lead/instrument levels are reference estimates from Demucs stems,
    # since the legacy mixer actually uses the original recording, not stems.
    frames = round(forward.output.duration_seconds * 44100)
    reference = {}
    for name, path, gain in (("lead_vocal", vocals, 0.8), ("instrumental", instrumental, 0.8), ("harmony", piano, 0.6)):
        samples = load_stereo(path)
        padded = np.zeros((frames, 2)); padded[:len(samples)] = samples * gain
        reference[name] = signal_levels(padded).model_dump()
    report = {"job_id": job.name, "previous_mix": before.model_dump(),
              "previous_reference_contributions": reference,
              "harmony_forward": forward.model_dump(), "balanced": balanced.model_dump(),
              "notes": ["RMS and sample peaks are measured levels, not perceived loudness or true peaks.",
                        "Legacy lead/instrument levels are estimates using Demucs stem contributions at original_gain=0.8.",
                        "No listening-based perceptual verification performed by this script."]}
    (output / "measurements.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

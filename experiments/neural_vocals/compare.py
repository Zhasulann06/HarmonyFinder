"""Prepare immutable local baselines, then assess actual neural output (no inference imports)."""

import argparse
import hashlib
import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.app.audio.pitch import PyinPitchDetector
from backend.app.audio.vocal_pitch import RubberBandVocalPitchShifter, read_vocal_wav, vocal_levels
from backend.app.audio.vocal_quality import match_loudness
from backend.scripts.compare_vocal_pitch import envelope_lag

ROOT = Path(__file__).resolve().parent


def save_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, allow_nan=False)


def prepare(source: Path, start: float, duration: float, reference_start: float) -> Path:
    samples, rate = read_vocal_wav(source)
    if (not all(math.isfinite(x) for x in (start, duration, reference_start)) or start < 0 or reference_start < 0
            or not 5 <= duration <= 10 or max(start, reference_start) + duration > len(samples) / rate
            or not (start + duration <= reference_start or reference_start + duration <= start)):
        raise ValueError("Choose valid source/reference excerpts of 5–10 seconds")
    run = ROOT / "runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    start_frame, count = round(start * rate), round(duration * rate)
    source_cut = samples[start_frame:start_frame + count]
    sf.write(run / "original_stereo_excerpt.wav", source_cut, rate, subtype="FLOAT")
    # Neural CLI downmixes to mono; use the identical mono source for every trial.
    original = source_cut.mean(axis=1, keepdims=True)
    reference = samples[round(reference_start * rate):round(reference_start * rate) + count].mean(axis=1, keepdims=True)
    sf.write(run / "original_vocals.wav", original, rate, subtype="FLOAT")
    sf.write(run / "reference_same_singer.wav", reference, rate, subtype="FLOAT")
    metadata = {"source": str(source.resolve()), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_excerpt_seconds": [start, start + duration], "reference_excerpt_seconds": [reference_start, reference_start + duration],
                "reference_scope": "Same recording/singer; not independent ground-truth identity or a clean studio reference",
                "original": asdict(vocal_levels(original, rate)), "rubberband": {}}
    for shift, label in ((3, "rubberband_plus_3"), (-3, "rubberband_minus_3")):
        report = RubberBandVocalPitchShifter().shift(run / "original_vocals.wav", run / f"{label}.wav", shift)
        metadata["rubberband"][label] = asdict(report)
    save_json(run / "preparation.json", metadata)
    write_comparison(run)
    print(run, flush=True)
    return run


def pitch_metrics(source, output, expected: float) -> dict:
    pairs = [(a, b) for a, b in zip(source.frames, output.frames)
             if a.voiced and b.voiced and a.midi_pitch is not None and b.midi_pitch is not None]
    offset = np.array([b.midi_pitch - a.midi_pitch for a, b in pairs])
    return {"expected_semitones": expected, "matched_voiced_frames": len(pairs),
            "median_shift_semitones": float(np.median(offset)) if len(offset) else None,
            "median_absolute_error_cents": float(np.median(abs(offset - expected)) * 100) if len(offset) else None,
            "p90_absolute_error_cents": float(np.percentile(abs(offset - expected), 90) * 100) if len(offset) else None,
            "voiced_source_frames": sum(frame.voiced for frame in source.frames),
            "voiced_output_frames": sum(frame.voiced for frame in output.frames),
            "scope": "All common voiced pYIN 10-ms frames, no manual octave correction or boundary exclusion; not ground truth"}


def silence_metrics(source: np.ndarray, output: np.ndarray, rate: int) -> dict:
    """Compare quiet 10-ms blocks, not pYIN-unvoiced consonants or a learned VAD."""
    hop = max(1, round(rate * 0.01))
    blocks = min(len(source), len(output)) // hop
    source_rms = np.sqrt(np.mean(source[:blocks * hop].reshape(blocks, -1) ** 2, axis=1))
    output_rms = np.sqrt(np.mean(output[:blocks * hop].reshape(blocks, -1) ** 2, axis=1))
    quiet = source_rms < 0.001  # -60 dBFS RMS, explicit and fixed across candidates.
    active = source_rms >= 0.01
    return {"block_seconds": hop / rate, "source_quiet_threshold_dbfs": -60,
            "quiet_source_blocks": int(quiet.sum()),
            "quiet_output_rms_max": float(output_rms[quiet].max()) if quiet.any() else None,
            "quiet_blocks_exceeding_minus_40_dbfs": int(np.sum(output_rms[quiet] > 0.01)),
            "active_source_blocks": int(active.sum()),
            "active_blocks_becoming_quiet": int(np.sum(output_rms[active] < 0.001)),
            "scope": "Energy-only screen; an excerpt without quiet blocks cannot establish silence preservation."}


def write_comparison(run: Path) -> dict:
    """Never relabel a DSP baseline as neural; missing C/D remain explicitly absent."""
    original, rate = read_vocal_wav(run / "original_vocals.wav")
    detector = PyinPitchDetector()
    baseline = detector.detect(run / "original_vocals.wav")
    tracks = {"A_original": original}
    metrics = {"A_original": asdict(vocal_levels(original, rate))}
    candidates = [("B_rubberband_plus_3", run / "rubberband_plus_3.wav", 3),
                  ("E_rubberband_minus_3", run / "rubberband_minus_3.wav", -3)]
    neural_report_path = run / "seed_report.json"
    neural = json.loads(neural_report_path.read_text()) if neural_report_path.is_file() else {}
    for label, key, shift in (("C_neural_plus_3", "neural_plus_3", 3), ("D_neural_minus_3", "neural_minus_3", -3)):
        if key in neural.get("renders", {}):
            candidates.append((label, run / neural["renders"][key]["path"], shift))
    for label, path, shift in candidates:
        audio, out_rate = read_vocal_wav(path)
        if out_rate != rate or audio.shape[1] != original.shape[1]:
            raise ValueError("Comparison requires identical rate/channels; do not hide conversion")
        mismatch = len(audio) - len(original)
        metrics[label] = {**asdict(vocal_levels(audio, rate)), "native_frame_difference": mismatch,
                          "native_duration_difference_seconds": mismatch / rate,
                          "pitch": pitch_metrics(baseline, detector.detect(path), shift)}
        if abs(mismatch) > round(0.05 * rate):
            raise ValueError("Native duration mismatch exceeds 50 ms; inspect before preparing aligned copies")
        # Only end-pad/crop hop rounding for listening. No audio shift, warp or timing correction.
        aligned = np.zeros_like(original)
        aligned[:min(len(audio), len(original))] = audio[:len(original)]
        metrics[label]["energy_envelope_lag_seconds"] = envelope_lag(original, aligned, rate)
        metrics[label]["silence"] = silence_metrics(original, aligned, rate)
        tracks[label] = aligned
    fade = min(round(0.005 * rate), len(original) // 2)
    for track in tracks.values():
        track[:fade] *= np.linspace(0, 1, fade)[:, None]
        track[-fade:] *= np.linspace(1, 0, fade)[:, None]
    matched, loudness = match_loudness(tracks, rate)
    listening = run / f"listening-{uuid.uuid4().hex[:8]}"
    listening.mkdir(exist_ok=False)
    for name, audio in matched.items():
        sf.write(listening / f"{name}.wav", audio, rate, subtype="PCM_24")
    report = {"metrics": metrics, "loudness": loudness, "listening_directory": str(listening.relative_to(run)),
              "missing_neural_trials": [key for key in ("neural_plus_3", "neural_minus_3") if key not in neural.get("renders", {})],
              "neural_error": neural.get("error"), "user_listening_review": "PENDING; no naturalness/intelligibility/identity verdict inferred",
              "scope": "Consonants/lyrics/timbre require listening. Envelope lag is coarse, not phoneme alignment. Duration rounding disclosed, not time-stretched."}
    save_json(listening / "measurements.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--start", type=float, default=7.0)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--reference-start", type=float, default=13.2)
    parser.add_argument("--assess", type=Path)
    args = parser.parse_args()
    if args.assess:
        write_comparison(args.assess.resolve())
    elif args.source:
        prepare(args.source.resolve(), args.start, args.duration, args.reference_start)
    else:
        parser.error("Choose --source or --assess")

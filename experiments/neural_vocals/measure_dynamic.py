"""Measure a full-phrase dynamic Seed-VC render against injected and constant F0."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

import librosa
import numpy as np
import soundfile as sf
import torch
import torchaudio

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor" / "seed-vc"))
from modules.rmvpe import RMVPE  # noqa: E402


def extract(extractor: RMVPE, path: Path) -> np.ndarray:
    audio, _ = librosa.load(path, sr=44100)
    wave = torch.from_numpy(audio).float().to("cuda")
    wave_16k = torchaudio.functional.resample(wave, 44100, 16000)
    return np.asarray(extractor.infer_from_audio(wave_16k, thred=0.03), dtype=np.float64)


def cents(actual: np.ndarray, target: np.ndarray, valid: np.ndarray) -> dict:
    delta = 1200 * np.log2(actual[valid] / target[valid])
    return {
        "matched_voiced_frames": int(valid.sum()),
        "median_signed_error_cents": float(np.median(delta)) if len(delta) else None,
        "median_absolute_error_cents": float(np.median(np.abs(delta))) if len(delta) else None,
        "p90_absolute_error_cents": float(np.percentile(np.abs(delta), 90)) if len(delta) else None,
        "frames_over_100_cents": int(np.sum(np.abs(delta) > 100)),
    }


def crossing(times: np.ndarray, relative_cents: np.ndarray, voiced: np.ndarray,
             center: float, before: float, after: float) -> dict:
    near_center = (times >= center - 0.03) & (times <= center + 0.03)
    if int((near_center & voiced).sum()) < 5:
        return {"center_seconds": center, "measured_seconds": None,
                "reason": "Transition overlaps unvoiced or unmatched frames; acoustic crossing cannot be timed"}
    window = (times >= center - 0.18) & (times <= center + 0.18)
    if int((window & voiced).sum()) < 8:
        return {"center_seconds": center, "measured_seconds": None,
                "reason": "Insufficient voiced comparison frames"}
    threshold = (before + after) * 50  # semitone midpoint expressed in cents
    choices = []
    for index in np.flatnonzero(window[:-1] & window[1:] & voiced[:-1] & voiced[1:]):
        left, right = relative_cents[index], relative_cents[index + 1]
        if (left - threshold) * (right - threshold) <= 0 and left != right:
            fraction = (threshold - left) / (right - left)
            choices.append(float(times[index] + fraction * (times[index + 1] - times[index])))
    if not choices:
        return {"center_seconds": center, "measured_seconds": None,
                "reason": "No observed midpoint crossing in adjacent voiced frames"}
    found = min(choices, key=lambda value: abs(value - center))
    return {"center_seconds": center, "measured_seconds": found,
            "error_seconds": found - center, "candidate_crossings": len(choices)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--constant-run", type=Path, required=True)
    args = parser.parse_args()
    run, constant = args.run.resolve(), args.constant_run.resolve()
    root_runs = (ROOT / "runs").resolve()
    if not run.is_relative_to(root_runs) or not constant.is_relative_to(root_runs):
        parser.error("Use isolated experiment runs")
    report_path, contours_path = run / "dynamic_metrics_final.json", run / "measured_f0_final.npz"
    if report_path.exists() or contours_path.exists():
        parser.error("Preserve prior analysis; use a new run")
    schedule = json.loads((run / "shift_map.json").read_text(encoding="utf-8"))
    label = schedule["label"]
    suffix = "plus_3" if label == "dynamic_plus_3_4" else "minus_3"
    if label not in {"dynamic_plus_3_4", "dynamic_minus_3_4"}:
        parser.error("Unknown dynamic experiment")
    raw = run / f"{label}.wav"
    constant_path = constant / f"neural_{suffix}.wav"
    with np.load(run / "injected_f0.npz") as injected:
        source = injected["source_hz"].astype(np.float64)
        target = injected["target_hz"].astype(np.float64)
        times = injected["times_seconds"].astype(np.float64)
    if raw.stat().st_size == 0 or constant_path.stat().st_size == 0:
        raise ValueError("Empty neural WAV")
    dynamic_info, constant_info = sf.info(raw), sf.info(constant_path)
    if (dynamic_info.samplerate, dynamic_info.channels) != (44100, 1) or (
            constant_info.samplerate, constant_info.channels) != (44100, 1):
        raise ValueError("Expected original 44.1 kHz mono neural output")
    started = time.perf_counter()
    extractor = RMVPE(ROOT / "assets" / "rmvpe" / "rmvpe.pt", is_half=False, device=torch.device("cuda"))
    measured = extract(extractor, raw)
    measured_constant = extract(extractor, constant_path)
    torch.cuda.synchronize()
    extraction_seconds = time.perf_counter() - started
    original_lengths = {"injected": len(times), "generated": len(measured),
                        "constant": len(measured_constant)}
    n = min(len(source), len(target), len(times), len(measured), len(measured_constant))
    source, target, times = source[:n], target[:n], times[:n]
    measured, measured_constant = measured[:n], measured_constant[:n]
    source_voiced, output_voiced = source > 1, measured > 1
    common = source_voiced & output_voiced & (target > 1)
    both_outputs = common & (measured_constant > 1)
    relative = np.full(n, np.nan)
    relative[both_outputs] = 1200 * np.log2(measured[both_outputs] / measured_constant[both_outputs])
    plateaus = ((0.2, 1.25), (1.45, 2.55), (2.75, 4.35), (4.65, 5.85))
    base_shift = 3 if suffix == "plus_3" else -3
    expected_shifts = (base_shift, base_shift + (1 if base_shift > 0 else -1),
                       base_shift, base_shift + (1 if base_shift > 0 else -1))
    segments = []
    for (start, end), desired in zip(plateaus, expected_shifts):
        selected = both_outputs & (times >= start) & (times < end)
        observed = relative[selected]
        segments.append({"start_seconds": start, "end_seconds": end,
                         "intended_shift_semitones": desired,
                         "expected_relative_to_constant_cents": 100 * (desired - base_shift),
                         "matched_voiced_frames": int(selected.sum()),
                         "median_relative_to_constant_cents": float(np.median(observed)) if len(observed) else None,
                         "p90_abs_relative_error_cents": float(np.percentile(
                             np.abs(observed - 100 * (desired - base_shift)), 90)) if len(observed) else None,
                         "target_error": cents(measured, target, selected)})
    transitions = [crossing(times, relative, both_outputs, center, before, after)
                   for center, before, after in zip(
                       schedule["source_note_onsets_seconds"],
                       (value - base_shift for value in expected_shifts[:-1]),
                       (value - base_shift for value in expected_shifts[1:]))]
    # Compare small frame-to-frame movements away from the scheduled ramps and
    # large note jumps. This is a contour proxy, not a vocal-naturalness score.
    stable = np.zeros(n, dtype=bool)
    for start, end in plateaus:
        stable |= (times >= start) & (times < end)
    adjacent = stable[1:] & stable[:-1] & common[1:] & common[:-1]
    source_delta = 12 * np.log2(source[1:][adjacent] / source[:-1][adjacent])
    output_delta = 12 * np.log2(measured[1:][adjacent] / measured[:-1][adjacent])
    small = np.abs(source_delta) < 0.3
    vibrato_corr = float(np.corrcoef(source_delta[small], output_delta[small])[0, 1]) if small.sum() > 10 else None
    result = {
        "label": label, "run": str(run), "constant_run": str(constant),
        "frames": {**original_lengths, "compared": n},
        "raw_audio": {"duration_seconds": dynamic_info.duration, "sample_rate": dynamic_info.samplerate,
                      "channels": dynamic_info.channels},
        "f0": {"source_voiced_frames": int(source_voiced.sum()),
               "output_voiced_frames": int(output_voiced.sum()),
               "source_voiced_output_unvoiced": int(np.sum(source_voiced & ~output_voiced)),
               "source_unvoiced_output_voiced": int(np.sum(~source_voiced & output_voiced)),
               "overall_target_error": cents(measured, target, common)},
        "segments": segments, "transitions": transitions,
        "small_motion_correlation": vibrato_corr,
        "small_motion_frame_pairs": int(small.sum()),
        "rmvpe_extraction_seconds": extraction_seconds,
        "scope": "Same RMVPE for source target and output; adjacent 10-ms frames. Voicing and transition timing are estimator-dependent. Correlation is a contour proxy, not a naturalness score.",
    }
    if not math.isfinite(dynamic_info.duration):
        raise ValueError("Invalid output duration")
    with contours_path.open("xb") as artifact:
        np.savez_compressed(artifact, times_seconds=times, source_hz=source, target_hz=target,
                            generated_hz=measured, constant_hz=measured_constant)
    with report_path.open("x", encoding="utf-8") as artifact:
        json.dump(result, artifact, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

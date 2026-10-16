"""Measure generated melodic-harmony F0 and boundary behavior (not naturalness)."""

import argparse
import json
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


def pitch_error(actual: np.ndarray, target: np.ndarray, mask: np.ndarray) -> dict:
    delta = 1200 * np.log2(actual[mask] / target[mask])
    return {"frames": int(mask.sum()),
            "median_signed_cents": float(np.median(delta)) if len(delta) else None,
            "median_abs_cents": float(np.median(np.abs(delta))) if len(delta) else None,
            "p90_abs_cents": float(np.percentile(np.abs(delta), 90)) if len(delta) else None,
            "peak_abs_cents": float(np.max(np.abs(delta))) if len(delta) else None}


def boundary_metrics(times: np.ndarray, source: np.ndarray, target: np.ndarray,
                     generated: np.ndarray, boundary: dict) -> dict:
    center = boundary["center_seconds"]
    near = (times >= center - 0.1) & (times <= center + 0.1)
    voiced = (source > 1) & (target > 1) & (generated > 1)
    mask = near & voiced
    result = {"note_index": boundary["note_index"], "center_seconds": center,
              "gap_seconds": boundary["gap_seconds"],
              "matched_voiced_frames": int(mask.sum()),
              "local_target_error": pitch_error(generated, target, mask)}
    if mask.sum() < 5 or (voiced & (abs(times - center) <= 0.03)).sum() < 3:
        result["timing"] = "unmeasurable: insufficient continuously voiced frames at boundary"
        return result
    relative = np.full(len(times), np.nan)
    relative[voiced] = 12 * np.log2(generated[voiced] / source[voiced])
    midpoint = (boundary["from_semitones"] + boundary["to_semitones"]) / 2
    crossings = []
    for index in np.flatnonzero(near[:-1] & near[1:] & voiced[:-1] & voiced[1:]):
        left, right = relative[index], relative[index + 1]
        if (left - midpoint) * (right - midpoint) <= 0 and left != right:
            crossings.append(float(times[index] + (midpoint - left) *
                                   (times[index + 1] - times[index]) / (right - left)))
    if crossings:
        measured = min(crossings, key=lambda value: abs(value - center))
        result["midpoint_crossing_seconds"] = measured
        result["crossing_error_ms"] = (measured - center) * 1000
    else:
        result["timing"] = "unmeasurable: no adjacent voiced midpoint crossing"
    pairs = near[1:] & near[:-1] & voiced[1:] & voiced[:-1]
    if pairs.any():
        jump = 1200 * np.log2(generated[1:][pairs] / generated[:-1][pairs])
        target_jump = 1200 * np.log2(target[1:][pairs] / target[:-1][pairs])
        result["max_adjacent_generated_cents"] = float(np.max(np.abs(jump)))
        result["max_adjacent_target_cents"] = float(np.max(np.abs(target_jump)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((ROOT / "runs").resolve()):
        parser.error("Use an isolated experiment run")
    output = run / "melodic_metrics.json"
    contours = run / "melodic_measured_f0.npz"
    if output.exists() or contours.exists():
        parser.error("Preserve existing measurements")
    schedule = json.loads((run / "shift_map.json").read_text(encoding="utf-8"))
    wav = run / f'{schedule["label"]}.wav'
    info = sf.info(wav)
    if (info.samplerate, info.channels) != (44100, 1):
        raise ValueError("Expected 44.1-kHz mono neural WAV")
    with np.load(run / "injected_f0.npz") as injection:
        source = injection["source_hz"].astype(float)
        target = injection["target_hz"].astype(float)
        times = injection["times_seconds"].astype(float)
    start = time.perf_counter()
    extractor = RMVPE(ROOT / "assets" / "rmvpe" / "rmvpe.pt",
                      is_half=False, device=torch.device("cuda"))
    generated = extract(extractor, wav)
    torch.cuda.synchronize()
    n = min(len(source), len(target), len(times), len(generated))
    source, target, times, generated = (item[:n] for item in
                                        (source, target, times, generated))
    voiced = (source > 1) & (target > 1) & (generated > 1)
    stable = voiced.copy()
    for boundary in schedule["boundaries"]:
        stable &= abs(times - boundary["center_seconds"]) > 0.1
    note_metrics = []
    for note in schedule["notes"]:
        in_note = stable & (times >= note["start_time"] + 0.03) & (
            times < note["end_time"] - 0.03)
        expected_hz = 440 * 2 ** ((note["harmony_midi"] - 69) / 12)
        expected = np.full(n, expected_hz)
        note_metrics.append({"harmony_note": note["harmony_note"],
                             "start_time": note["start_time"],
                             "end_time": note["end_time"],
                             "absolute_note_error": pitch_error(generated, expected, in_note),
                             "expressive_contour_error": pitch_error(generated, target, in_note)})
    result = {"label": schedule["label"], "key": schedule["key"],
              "key_status": schedule["key_status"],
              "audio": {"duration_seconds": info.duration, "sample_rate": info.samplerate,
                        "channels": info.channels, "frames": info.frames},
              "f0": {"frames_compared": n, "source_voiced": int((source > 1).sum()),
                     "generated_voiced": int((generated > 1).sum()),
                     "source_voiced_output_unvoiced": int(((source > 1) & (generated <= 1)).sum()),
                     "source_unvoiced_output_voiced": int(((source <= 1) & (generated > 1)).sum()),
                     "overall_target_error": pitch_error(generated, target, voiced),
                     "stable_target_error": pitch_error(generated, target, stable)},
              "notes": note_metrics,
              "boundaries": [boundary_metrics(times, source, target, generated, item)
                             for item in schedule["boundaries"]],
              "extraction_seconds": time.perf_counter() - start,
              "scope": "RMVPE 10-ms acoustic estimates, not hand-labelled truth; local jumps and timing cannot establish naturalness"}
    with contours.open("xb") as artifact:
        np.savez_compressed(artifact, times_seconds=times, source_hz=source,
                            target_hz=target, generated_hz=generated)
    with output.open("x", encoding="utf-8") as artifact:
        json.dump(result, artifact, indent=2, allow_nan=False)
    print(json.dumps({"label": result["label"], "f0": result["f0"],
                      "audio": result["audio"]}, indent=2))


if __name__ == "__main__":
    main()

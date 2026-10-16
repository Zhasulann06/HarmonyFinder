"""Plan an isolated, provisional diatonic harmony from the cached lead analysis.

Run with the *existing* application Python for its pydantic models. Inference
still runs only in the separate neural environment. No production file is edited.
"""

import argparse
import json
import math
import os
from pathlib import Path

import numpy as np

from backend.app.audio.harmony import HarmonyConfig, generate_harmony
from backend.app.audio.music import KEYS, PITCH_CLASSES, SCALES
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizationConfig, quantize_melody


ROOT = Path(__file__).resolve().parent
SOURCE_RUN = ROOT / "runs" / "gpu-20261016T214526"
ANALYSIS = (ROOT.parents[1] / "backend" / "data" / "audio"
            / "fa570cb6-1482-4dd2-8907-3ec2c0cbdf83" / "pitch_analysis.json")
EXCERPT_START = 7.0
EXCERPT_DURATION = 6.0


def scale_coverage(analysis: PitchAnalysis) -> list[dict]:
    """Duration-weighted pitch-class fit, not a key/mode detector."""
    scores = []
    for key in PITCH_CLASSES:
        for scale in SCALES:
            allowed = {(KEYS[key] + step) % 12 for step in SCALES[scale]}
            inside = sum(note.duration for note in analysis.notes if note.midi_note % 12 in allowed)
            total = sum(note.duration for note in analysis.notes)
            scores.append({"key": key, "scale": scale, "fitted_seconds": round(inside, 3),
                           "total_note_seconds": round(total, 3),
                           "fraction": round(inside / total, 4) if total else None})
    return sorted(scores, key=lambda row: row["fitted_seconds"], reverse=True)


def excerpt(analysis: PitchAnalysis) -> PitchAnalysis:
    notes = []
    for note in analysis.notes:
        start = max(0.0, note.start_time - EXCERPT_START)
        end = min(EXCERPT_DURATION, note.end_time - EXCERPT_START)
        if end > start:
            notes.append(note.model_copy(update={"start_time": start, "end_time": end,
                                          "duration": end - start}))
    if not notes:
        raise ValueError("No notes in source excerpt")
    return analysis.model_copy(update={"duration_seconds": EXCERPT_DURATION,
                                       "notes": notes, "frames": []})


def transition_map(notes: list[dict], treatment: str,
                   source_f0: np.ndarray | None = None) -> tuple[list[float], list[float], list[dict]]:
    """Offset ramps around note onsets, not audio cuts or absolute-F0 smoothing."""
    width = {"baseline80": 0.08, "short30": 0.03, "motion30": 0.03}[treatment]
    if not notes:
        raise ValueError("Expected planned notes")
    offsets = [note["offset_semitones"] for note in notes]
    boundaries = []
    for index in range(1, len(notes)):
        if abs(offsets[index] - offsets[index - 1]) < 1e-6:
            continue
        current, previous = notes[index], notes[index - 1]
        gap = current["start_time"] - previous["end_time"]
        # If the source has a gap, move the control change into the gap. The
        # F0 adapter leaves true unvoiced frames at zero regardless.
        center = ((current["start_time"] + previous["end_time"]) / 2
                  if gap >= 0.03 else current["start_time"])
        placement = "gap_midpoint" if gap >= 0.03 else "note_onset"
        if treatment == "motion30" and gap < 0.03 and source_f0 is not None:
            expected_delta = current["source_midi_fractional"] - previous["source_midi_fractional"]
            if abs(expected_delta) >= 0.8:
                candidates = []
                for frame in range(max(0, round(center * 100) - 6),
                                   min(len(source_f0) - 1, round(center * 100) + 6)):
                    before_f0, after_f0 = source_f0[frame:frame + 2]
                    if before_f0 > 1 and after_f0 > 1:
                        motion = 12 * math.log2(after_f0 / before_f0)
                        if 0.3 <= abs(motion) <= 6 and motion * expected_delta > 0:
                            candidates.append((abs(motion), (frame + 0.5) * 0.01))
                if candidates:
                    center = max(candidates)[1]
                    placement = "source_f0_motion"
        boundaries.append({"center": center, "index": index, "gap_seconds": gap,
                           "placement": placement})
    times = [0.0]
    shifts = [offsets[0]]
    details = []
    for position, boundary in enumerate(boundaries):
        center, index = boundary["center"], boundary["index"]
        left_limit = center - (boundaries[position - 1]["center"] if position else 0.0)
        right_limit = (boundaries[position + 1]["center"] if position + 1 < len(boundaries)
                       else EXCERPT_DURATION) - center
        half = min(width / 2, 0.4 * left_limit, 0.4 * right_limit)
        if half <= 0:
            raise ValueError("Coincident or invalid note boundaries")
        start, end = center - half, center + half
        before, after = offsets[index - 1], offsets[index]
        if start > times[-1]:
            times.append(start)
            shifts.append(before)
        times.append(end)
        shifts.append(after)
        details.append({"note_index": index, "note_start_seconds": notes[index]["start_time"],
                        "center_seconds": center, "ramp_start_seconds": start,
                        "ramp_end_seconds": end, "gap_seconds": boundary["gap_seconds"],
                        "placement": boundary["placement"],
                        "from_semitones": before, "to_semitones": after})
    times.append(EXCERPT_DURATION)
    shifts.append(offsets[-1])
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("Shift map points must be strictly increasing")
    return times, shifts, details


def plan(analysis: PitchAnalysis, direction: str, key: str, scale: str,
         treatment: str, source_f0: np.ndarray | None = None) -> dict:
    clipped = excerpt(analysis)
    quantized = quantize_melody(clipped, QuantizationConfig(mode="scale-aware", key=key, scale=scale))
    harmony = generate_harmony(quantized, HarmonyConfig(interval="diatonic_third",
                                                        direction=direction, key=key, scale=scale))
    note_rows = []
    for source, corrected, target in zip(clipped.notes, quantized.notes, harmony.notes):
        offset = target.harmony_midi_note - source.midi_pitch
        if not math.isfinite(offset) or abs(offset) > 12:
            raise ValueError("A planned source-to-harmony offset exceeds the evaluated F0 range")
        note_rows.append({"start_time": source.start_time, "end_time": source.end_time,
                          "source_note": source.note_name, "source_midi_fractional": source.midi_pitch,
                          "scale_note": corrected.corrected_note_name,
                          "scale_correction_cents": corrected.correction_cents,
                          "harmony_note": target.harmony_note_name,
                          "harmony_midi": target.harmony_midi_note,
                          "offset_semitones": offset,
                          "out_of_scale": source.midi_note % 12 not in
                          {(KEYS[key] + step) % 12 for step in SCALES[scale]}})
    times, shifts, boundaries = transition_map(note_rows, treatment, source_f0)
    return {"label": f"harmony_{direction}_{treatment}", "times": times, "shifts": shifts,
            "transition_treatment": treatment,
            "interpolation": "cubic smoothstep between adjacent map points; voiced source F0 only",
            "key_status": "provisional; melody-only pitch classes cannot establish tonic or mode",
            "key": key, "scale": scale, "direction": direction,
            "notes": note_rows, "boundaries": boundaries,
            "unsegmented_voiced_policy": "nearest event offset between note spans; source unvoiced F0 remains zero",
            "source": "cached full-song pYIN analysis cropped to source seconds 7-13; production quantizer and diatonic harmony engine imported read-only"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--direction", choices=("above", "below"), required=True)
    parser.add_argument("--key", default="D")
    parser.add_argument("--scale", choices=("major", "natural_minor"), default="major")
    parser.add_argument("--treatment", choices=("baseline80", "short30", "motion30"), required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((ROOT / "runs").resolve()) or run.exists():
        parser.error("Choose a new run path inside experiments/neural_vocals/runs")
    analysis = PitchAnalysis.model_validate_json(ANALYSIS.read_text(encoding="utf-8"))
    source_f0 = None
    if args.treatment == "motion30":
        prior = ROOT / "runs" / "dynamic-plus34-retry-20261016T234734" / "injected_f0.npz"
        with np.load(prior) as injection:
            source_f0 = injection["source_hz"].astype(float)
    result = plan(analysis, args.direction, args.key, args.scale, args.treatment, source_f0)
    result["full_song_scale_coverage"] = scale_coverage(analysis)[:8]
    run.mkdir(parents=True, exist_ok=False)
    for name in ("original_vocals.wav", "reference_same_singer.wav"):
        os.link(SOURCE_RUN / name, run / name)
    (run / "shift_map.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"run": str(run), "label": result["label"],
                      "notes": len(result["notes"]), "transitions": len(result["boundaries"]),
                      "coverage": result["full_song_scale_coverage"][:4]}, indent=2))


if __name__ == "__main__":
    main()

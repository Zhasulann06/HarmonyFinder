"""CPU-only checks for the isolated melodic target planner."""

import json
import math
from pathlib import Path

import numpy as np

from backend.app.audio.pitch_models import NoteEvent, PitchAnalysis
from experiments.neural_vocals.control import target_f0
from experiments.neural_vocals.melodic_harmony import plan, transition_map


def analysis(notes: list[tuple[int, float, float, float]]) -> PitchAnalysis:
    events = [NoteEvent(midi_note=pitch, note_name="source", midi_pitch=fraction,
                        start_time=start, end_time=end, duration=end - start,
                        median_pitch_hz=440 * 2 ** ((fraction - 69) / 12),
                        pitch_deviation_cents=0)
              for pitch, fraction, start, end in notes]
    return PitchAnalysis(duration_seconds=13, sample_rate=44100, hop_length=441,
                         frame_length=2048, fmin_hz=50, fmax_hz=1100,
                         frames=[], notes=events)


def test_true_diatonic_thirds_and_preserved_timing() -> None:
    source = analysis([(50, 50.2, 7, 7.5), (52, 51.9, 7.5, 8),
                       (54, 54.1, 8, 8.5)])
    above = plan(source, "above", "D", "major", "short30")
    below = plan(source, "below", "D", "major", "baseline80")
    assert [n["harmony_note"] for n in above["notes"]] == ["F#3", "G3", "A3"]
    assert [n["harmony_note"] for n in below["notes"]] == ["B2", "C#3", "D3"]
    assert [(n["start_time"], n["end_time"]) for n in above["notes"]] == [
        (0, 0.5), (0.5, 1), (1, 1.5)]
    assert math.isclose(above["notes"][0]["offset_semitones"], 3.8)


def test_out_of_scale_event_is_reported_and_adjusted() -> None:
    source = analysis([(53, 53.0, 7, 7.5)])  # F is outside D major; ties choose F#.
    result = plan(source, "above", "D", "major", "short30")
    assert result["notes"][0]["out_of_scale"] is True
    assert result["notes"][0]["scale_note"] == "F#3"
    assert result["notes"][0]["harmony_note"] == "A3"


def test_short_ramps_are_narrower_and_unvoiced_stays_zero() -> None:
    notes = [{"start_time": 0, "end_time": 1, "offset_semitones": 3.0},
             {"start_time": 1, "end_time": 2, "offset_semitones": 4.0}]
    baseline = transition_map(notes, "baseline80")
    short = transition_map(notes, "short30")
    assert round(baseline[2][0]["ramp_end_seconds"] - baseline[2][0]["ramp_start_seconds"], 2) == 0.08
    assert round(short[2][0]["ramp_end_seconds"] - short[2][0]["ramp_start_seconds"], 2) == 0.03
    f0 = np.full(601, 220.0)
    f0[75:85] = 0
    mapped = target_f0(f0, times=np.asarray(short[0]), shifts=np.asarray(short[1]))
    assert np.all(mapped[75:85] == 0)
    assert np.isclose(mapped[30], 220 * 2 ** (3 / 12), atol=0.01)
    assert np.isclose(mapped[150], 220 * 2 ** (4 / 12), atol=0.01)


def test_motion_aligned_transition_uses_source_jump() -> None:
    notes = [{"start_time": 0, "end_time": 1, "offset_semitones": 3.0,
              "source_midi_fractional": 50.0},
             {"start_time": 1, "end_time": 2, "offset_semitones": 4.0,
              "source_midi_fractional": 52.0}]
    contour = np.full(601, 220.0)
    contour[103:] = 220 * 2 ** (2 / 12)
    _, _, boundaries = transition_map(notes, "motion30", contour)
    assert boundaries[0]["placement"] == "source_f0_motion"
    assert math.isclose(boundaries[0]["center_seconds"], 1.025)


def test_planned_run_keeps_previous_inputs() -> None:
    run = Path(__file__).resolve().parent / "runs" / "harmony-above-baseline80-20261017"
    if run.exists():
        mapped = json.loads((run / "shift_map.json").read_text(encoding="utf-8"))
        assert mapped["label"] == "harmony_above_baseline80"
        assert mapped["key_status"].startswith("provisional")

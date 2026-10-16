"""Pure, expression-preserving harmony automation, independent of waveform DSP."""

import math
from dataclasses import dataclass

import numpy as np

from backend.app.audio.harmony import HarmonyConfig, HarmonyMelody, generate_harmony
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizedMelody


@dataclass(frozen=True)
class CurvePoint:
    time_seconds: float
    shift_semitones: float
    gain: float
    note_index: int | None = None
    reliable_f0: bool = False
    detected_midi: float | None = None
    expressive_target_midi: float | None = None


@dataclass(frozen=True)
class HarmonyPitchCurve:
    duration_seconds: float
    points: tuple[CurvePoint, ...]
    transition_seconds: float = 0.020

    def validate(self) -> None:
        if not math.isfinite(self.duration_seconds) or not 0 < self.duration_seconds <= 30:
            raise ValueError("Curve duration must be in (0, 30] seconds")
        if len(self.points) < 2 or len(self.points) > 40000:
            raise ValueError("Curve requires 2–40000 points")
        if self.points[0].time_seconds != 0 or not math.isclose(self.points[-1].time_seconds, self.duration_seconds, abs_tol=1e-9):
            raise ValueError("Curve must span the complete waveform")
        previous = -1.0
        for point in self.points:
            if (not all(math.isfinite(x) for x in (point.time_seconds, point.shift_semitones, point.gain))
                    or not previous < point.time_seconds <= self.duration_seconds
                    or not -12 <= point.shift_semitones <= 12 or not 0 <= point.gain <= 1):
                raise ValueError("Invalid curve point or non-increasing time")
            previous = point.time_seconds


def build_harmony_curve(analysis: PitchAnalysis, quantized: QuantizedMelody,
                        harmony: HarmonyMelody, *, transition_seconds: float = 0.020) -> HarmonyPitchCurve:
    """Transpose the performance by planned scale intervals, retaining its expression.

    expressive_target = harmony_note + (detected_midi - quantized_lead_anchor)
    shift = expressive_target - detected_midi = harmony_note - lead_anchor.
    F0 is diagnostic, not a noisy frame-by-frame autotune controller.
    """
    if not math.isfinite(transition_seconds) or not 0.005 <= transition_seconds <= 0.050:
        raise ValueError("Transition must be 5–50 ms")
    duration = analysis.duration_seconds
    if (not 0 < analysis.sample_rate <= 192000 or analysis.hop_length <= 0
            or len(analysis.frames) > 10000 or len(quantized.notes) > 1000):
        raise ValueError("Invalid or excessive analysis grid")
    if any(not math.isclose(d, duration, abs_tol=1e-6) for d in (quantized.duration_seconds, harmony.duration_seconds)):
        raise ValueError("Analysis, quantization, and harmony durations must match")
    expected = generate_harmony(quantized, HarmonyConfig(interval=harmony.interval, direction=harmony.direction,
                                                       key=harmony.key, scale=harmony.scale))
    if len(analysis.notes) != len(quantized.notes) or expected.notes != harmony.notes:
        raise ValueError("Harmony must match the quantized source notes and interval configuration")
    for original, note in zip(analysis.notes, quantized.notes):
        if any(not math.isclose(a, b, abs_tol=1e-6) for a, b in
               ((original.start_time, note.start_time), (original.end_time, note.end_time), (original.duration, note.duration))):
            raise ValueError("Original and quantized note timing must match")
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("Invalid analysis duration")
    frame_times = np.array([f.time_seconds for f in analysis.frames])
    if len(frame_times) and (not np.all(np.isfinite(frame_times)) or np.any(np.diff(frame_times) <= 0)
                             or frame_times[0] < 0 or frame_times[-1] >= duration):
        raise ValueError("Pitch frame times must be ordered and inside the recording")
    # Include exact event edges and short-note midpoints in addition to a 5 ms grid.
    times = sorted(set([0.0, duration, *np.arange(0, duration, 0.005).tolist(),
                        *[t for n in harmony.notes for t in (n.start_time, (n.start_time + n.end_time) / 2, n.end_time)]]))
    raw = np.zeros(len(times)); gains = np.zeros(len(times)); indices: list[int | None] = [None] * len(times)
    time_array = np.array(times)
    for index, note in enumerate(harmony.notes):
        shift = note.harmony_midi_note - note.original_midi_note
        if not -12 <= shift <= 12:
            raise ValueError("Planned shift exceeds the evaluated +/-12-semitone DSP range")
        for i in np.flatnonzero((time_array >= note.start_time) & (time_array < note.end_time)):
            raw[i] = shift; indices[i] = index
    # Touching notes belong to one amplitude phrase: no gain dips per note.
    spans: list[list[float]] = []
    for note in harmony.notes:
        if spans and note.start_time <= spans[-1][1] + 1e-9:
            spans[-1][1] = note.end_time
        else:
            spans.append([note.start_time, note.end_time])
    for start, end in spans:
        fade = min(0.005, (end - start) / 4)
        for i in np.flatnonzero((time_array >= start) & (time_array <= end)):
            gains[i] = max(0, min(1.0, (times[i] - start) / fade, (end - times[i]) / fade))
    # Smooth the interval automation in time, not the singer's pitch contour.
    # Midpoint integration on a 1 ms grid avoids weighting extra event knots.
    grid = np.arange(0, duration + 0.001, 0.001)
    control = np.interp(grid, times, raw)
    width = max(1, round(transition_seconds / 0.001))
    padded = np.pad(control, (width // 2, width - 1 - width // 2), mode="edge")
    smooth = np.interp(times, grid, np.convolve(padded, np.ones(width) / width, mode="valid"))
    points = []
    for i, t in enumerate(times):
        detected = None; reliable = False; target = None
        note_index = indices[i]
        if note_index is not None and len(frame_times):
            nearest = int(np.clip(np.searchsorted(frame_times, t), 0, len(frame_times) - 1))
            if nearest and abs(frame_times[nearest - 1] - t) < abs(frame_times[nearest] - t): nearest -= 1
            frame = analysis.frames[nearest]
            anchor = quantized.notes[note_index].corrected_midi_pitch
            if (abs(frame.time_seconds - t) <= analysis.hop_length / analysis.sample_rate + 1e-9
                    and frame.voiced and frame.midi_pitch is not None and frame.f0_hz is not None
                    and math.isfinite(frame.midi_pitch) and math.isfinite(frame.f0_hz) and frame.f0_hz > 0
                    and (frame.voiced_probability is None or frame.voiced_probability >= 0.5)
                    and abs(frame.midi_pitch - anchor) <= 2
                    and abs(frame.midi_pitch - (69 + 12 * math.log2(frame.f0_hz / 440))) < 0.2):
                detected = frame.midi_pitch; reliable = True
                target = detected + float(smooth[i])
        points.append(CurvePoint(t, float(smooth[i]), float(gains[i]), note_index, reliable, detected, target))
    curve = HarmonyPitchCurve(duration, tuple(points), transition_seconds)
    curve.validate()
    return curve

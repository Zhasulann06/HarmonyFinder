"""Frame-level F0 conditioning experiment; no note planning or waveform stitching."""

import numpy as np


def target_f0(source: np.ndarray, semitones: float = 0, *,
              times: np.ndarray | None = None, shifts: np.ndarray | None = None,
              hop_seconds: float = 0.01) -> np.ndarray:
    source = np.asarray(source, dtype=np.float64)
    if (source.ndim != 1 or not len(source) or not np.all(np.isfinite(source))
            or np.any(source < 0) or not np.isfinite(semitones) or not -12 <= semitones <= 12
            or not np.isfinite(hop_seconds) or hop_seconds <= 0):
        raise ValueError("Expected a finite F0 vector, positive hop and shift within +/-12")
    offsets = np.full(len(source), semitones)
    if times is not None or shifts is not None:
        times, shifts = np.asarray(times, dtype=float), np.asarray(shifts, dtype=float)
        if (times.ndim != 1 or shifts.shape != times.shape or len(times) < 2
                or not np.all(np.isfinite(times)) or not np.all(np.isfinite(shifts))
                or times[0] != 0 or np.any(np.diff(times) <= 0)
                or times[-1] < (len(source) - 1) * hop_seconds
                or np.any(np.abs(shifts) > 12)):
            raise ValueError("Shift map must cover the F0 grid with ordered, bounded points")
        frame_times = np.arange(len(source)) * hop_seconds
        segment = np.clip(np.searchsorted(times, frame_times, side="right") - 1, 0, len(times) - 2)
        phase = np.clip((frame_times - times[segment]) / (times[segment + 1] - times[segment]), 0, 1)
        smooth = phase * phase * (3 - 2 * phase)
        offsets = shifts[segment] + (shifts[segment + 1] - shifts[segment]) * smooth
    result = np.zeros_like(source)
    voiced = source > 1
    result[voiced] = source[voiced] * 2 ** (offsets[voiced] / 12)
    # The selected model bins F0 approximately over 50–1100 Hz. Reject rather than silently clamp.
    if np.any((result[voiced] < 50) | (result[voiced] > 1100)):
        raise ValueError("Target F0 exceeds the evaluated Seed-VC conditioning range 50–1100 Hz")
    return result.astype(np.float32)

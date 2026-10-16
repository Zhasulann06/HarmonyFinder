"""Turn voiced pitch frames into stable note events without retuning them."""

import math

import numpy as np
from scipy.ndimage import median_filter

from backend.app.audio.pitch_models import NoteEvent, PitchFrame
from backend.app.audio.music import midi_to_note_name


def segment_notes(
    frames: list[PitchFrame], duration: float, frame_step: float,
    *, min_note_seconds: float = 0.08, max_gap_seconds: float = 0.04,
    change_semitones: float = 0.75,
) -> list[NoteEvent]:
    """Bridge brief dropouts and require sustained changes to split notes.

    Smoothing affects boundaries only. Note statistics use the original voiced
    samples, and unvoiced frames never contribute a pitch to a note.
    """
    voiced = [i for i, frame in enumerate(frames)
              if frame.voiced and frame.f0_hz is not None and frame.midi_pitch is not None]
    if not voiced:
        return []
    groups: list[list[int]] = [[voiced[0]]]
    for index in voiced[1:]:
        previous = groups[-1][-1]
        gap = (index - previous - 1) * frame_step
        close_pitch = abs(frames[index].midi_pitch - frames[previous].midi_pitch) < change_semitones
        if index == previous + 1 or (gap <= max_gap_seconds + 1e-9 and close_pitch):
            groups[-1].append(index)
        else:
            groups.append([index])

    hold = max(2, math.ceil(min_note_seconds / frame_step))
    events: list[NoteEvent] = []
    for group in groups:
        first, last = group[0], group[-1]
        indices = np.arange(first, last + 1)
        # Interpolation is for boundary detection across short gaps only.
        pitches = np.interp(indices, group, [frames[i].midi_pitch for i in group])
        smooth = median_filter(pitches, size=5, mode="nearest")
        start = 0
        index = hold
        boundaries: list[tuple[int, int]] = []
        while index + hold <= len(smooth):
            anchor = float(np.median(smooth[start:index]))
            delta = smooth[index:index + hold] - anchor
            if (np.mean(delta >= change_semitones) >= 0.8
                    or np.mean(delta <= -change_semitones) >= 0.8):
                boundaries.append((first + start, first + index))
                start = index
                index += hold
            else:
                index += 1
        boundaries.append((first + start, last + 1))
        for begin, end in boundaries:
            selected = [frames[i] for i in group if begin <= i < end]
            start_time = frames[begin].time_seconds
            end_time = min(duration, frames[end - 1].time_seconds + frame_step)
            if end_time - start_time < min_note_seconds - 1e-9 or len(selected) < hold:
                continue
            median_hz = float(np.median([frame.f0_hz for frame in selected]))
            midi = 69 + 12 * math.log2(median_hz / 440)
            nearest = math.floor(midi + 0.5)
            probabilities = [f.voiced_probability for f in selected
                             if f.voiced_probability is not None]
            events.append(NoteEvent(
                midi_note=nearest, note_name=midi_to_note_name(nearest),
                midi_pitch=midi, start_time=start_time, end_time=end_time,
                duration=end_time - start_time, median_pitch_hz=median_hz,
                pitch_deviation_cents=100 * (midi - nearest),
                voiced_probability=float(np.median(probabilities)) if probabilities else None,
            ))
    return events

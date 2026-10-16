"""Deterministic piano MIDI export from the existing harmony JSON schema."""

import math
from pathlib import Path

import pretty_midi
from pydantic import ValidationError

from backend.app.audio.harmony import HarmonyMelody
from backend.app.audio.render_errors import RenderInputError


class MidiRenderer:
    def render(self, harmony_json: Path, output: Path, velocity: int = 90) -> HarmonyMelody:
        if isinstance(velocity, bool) or not isinstance(velocity, int) or not 1 <= velocity <= 127:
            raise RenderInputError("Velocity must be an integer in 1-127")
        try:
            if harmony_json.stat().st_size > 2 * 1024 * 1024:
                raise RenderInputError("Harmony JSON is too large")
            melody = HarmonyMelody.model_validate_json(harmony_json.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise RenderInputError("Invalid or missing harmony_melody.json; regenerate harmony") from exc
        if not math.isfinite(melody.duration_seconds) or not 0 <= melody.duration_seconds <= 30:
            raise RenderInputError("Harmony duration must be finite and within 0-30 seconds")
        # At 120 BPM this resolution gives one tick per 1/44100 second.
        midi = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=22050)
        piano = pretty_midi.Instrument(program=0, is_drum=False, name="Harmony piano")
        previous_end = 0.0
        for index, note in enumerate(melody.notes):
            pitch = note.harmony_midi_note
            if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
                raise RenderInputError(f"Harmony note {index} must be an integer MIDI pitch in 0-127")
            if (not all(math.isfinite(t) for t in (note.start_time, note.end_time, note.duration))
                    or note.start_time < previous_end - 1e-9
                    or note.end_time <= note.start_time or note.duration <= 0
                    or not math.isclose(note.duration, note.end_time - note.start_time, abs_tol=1e-9)
                    or note.end_time > melody.duration_seconds + 1e-9):
                raise RenderInputError(f"Harmony note {index} has invalid or overlapping timing")
            if midi.time_to_tick(note.start_time) == midi.time_to_tick(note.end_time):
                raise RenderInputError(f"Harmony note {index} is shorter than one MIDI tick")
            previous_end = note.end_time
            piano.notes.append(pretty_midi.Note(
                velocity=velocity, pitch=pitch, start=note.start_time, end=note.end_time,
            ))
        midi.instruments.append(piano)
        # Keep trailing rests and empty-melody duration without introducing notes.
        midi.text_events.append(pretty_midi.Text("HarmonyFinder end", melody.duration_seconds))
        midi.write(str(output))
        return melody

"""Generate a timed second voice from quantized melody notes."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.app.audio.music import KEYS, SCALES, midi_to_note_name, normalize_key
from backend.app.audio.quantization import QuantizedMelody


Interval = Literal[
    "major_third", "minor_third", "perfect_fourth", "perfect_fifth", "octave",
    "diatonic_third", "diatonic_sixth",
]
FIXED_INTERVALS = {"major_third": 4, "minor_third": 3, "perfect_fourth": 5,
                   "perfect_fifth": 7, "octave": 12}
DIATONIC_INTERVALS = {"diatonic_third": 2, "diatonic_sixth": 5}


class HarmonyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval: Interval
    direction: Literal["above", "below"] = "above"
    key: str | None = None
    scale: Literal["major", "natural_minor"] | None = None

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str | None) -> str | None:
        return normalize_key(value)

    @field_validator("scale", mode="before")
    @classmethod
    def normalize_scale(cls, value: object) -> object:
        return "natural_minor" if value == "minor" else value

    @model_validator(mode="after")
    def require_scale(self) -> "HarmonyConfig":
        if self.interval in DIATONIC_INTERVALS and (self.key is None or self.scale is None):
            raise ValueError("Diatonic intervals require both key and scale")
        return self


class HarmonyNote(BaseModel):
    original_midi_note: int
    harmony_midi_note: int
    original_note_name: str
    harmony_note_name: str
    start_time: float
    end_time: float
    duration: float


class HarmonyMelody(BaseModel):
    interval: Interval
    direction: Literal["above", "below"]
    key: str | None
    scale: Literal["major", "natural_minor"] | None
    duration_seconds: float
    notes: list[HarmonyNote]


def generate_harmony(melody: QuantizedMelody, config: HarmonyConfig) -> HarmonyMelody:
    """Transpose existing events only; never quantize or alter their timing."""
    sign = 1 if config.direction == "above" else -1
    tonic = 0
    scale: tuple[int, ...] = ()
    if config.interval in DIATONIC_INTERVALS:
        assert config.key is not None and config.scale is not None
        tonic = KEYS[config.key]
        scale = SCALES[config.scale]
    if not math.isfinite(melody.duration_seconds) or melody.duration_seconds < 0:
        raise ValueError("Melody duration must be finite and nonnegative")
    notes: list[HarmonyNote] = []
    previous_end = 0.0
    for index, note in enumerate(melody.notes):
        source = note.corrected_midi_pitch
        if isinstance(source, bool) or not isinstance(source, int) or not 0 <= source <= 127:
            raise ValueError(f"Source note {index} must be an integer MIDI pitch in 0-127")
        if (not all(math.isfinite(t) for t in (note.start_time, note.end_time, note.duration))
                or note.start_time < 0 or note.end_time <= note.start_time
                or note.duration <= 0
                or not math.isclose(note.duration, note.end_time - note.start_time, abs_tol=1e-9)
                or note.end_time > melody.duration_seconds + 1e-9):
            raise ValueError(f"Source note {index} has invalid timing")
        if note.start_time < previous_end - 1e-9:
            raise ValueError(f"Source note {index} overlaps or is out of order")
        previous_end = note.end_time
        if config.interval in FIXED_INTERVALS:
            target = source + sign * FIXED_INTERVALS[config.interval]
        else:
            octave, pitch_class = divmod(source - tonic, 12)
            if pitch_class not in scale:
                raise ValueError(
                    f"Source note {index} ({midi_to_note_name(source)}) is outside "
                    f"the selected {config.key} {config.scale} scale"
                )
            degree = octave * len(scale) + scale.index(pitch_class)
            target_octave, target_degree = divmod(
                degree + sign * DIATONIC_INTERVALS[config.interval], len(scale)
            )
            target = tonic + 12 * target_octave + scale[target_degree]
        if not 0 <= target <= 127:
            raise ValueError(f"Harmony for source note {index} would be MIDI {target}, outside 0-127")
        notes.append(HarmonyNote(
            original_midi_note=source, harmony_midi_note=target,
            original_note_name=midi_to_note_name(source), harmony_note_name=midi_to_note_name(target),
            start_time=note.start_time, end_time=note.end_time, duration=note.duration,
        ))
    return HarmonyMelody(
        interval=config.interval, direction=config.direction, key=config.key,
        scale=config.scale, duration_seconds=melody.duration_seconds, notes=notes,
    )

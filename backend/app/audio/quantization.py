"""Simple note quantization that preserves the original analysis."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.music import KEYS, SCALES, midi_to_note_name, normalize_key


class QuantizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["chromatic", "scale-aware"] = "chromatic"
    key: str | None = None
    scale: Literal["major", "natural_minor"] | None = None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> object:
        return "scale-aware" if value == "scale_aware" else value

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str | None) -> str | None:
        return normalize_key(value)

    @field_validator("scale", mode="before")
    @classmethod
    def normalize_scale(cls, value: object) -> object:
        return "natural_minor" if value == "minor" else value

    @model_validator(mode="after")
    def require_scale_parameters(self) -> "QuantizationConfig":
        if self.mode == "scale-aware" and (self.key is None or self.scale is None):
            raise ValueError("Scale-aware mode requires both key and scale")
        return self


class QuantizedNote(BaseModel):
    original_midi_pitch: float
    corrected_midi_pitch: int
    original_note_name: str
    corrected_note_name: str
    correction_cents: float
    start_time: float
    end_time: float
    duration: float
    median_pitch_hz: float
    confidence: float | None
    voiced_probability: float | None


class QuantizedMelody(BaseModel):
    mode: Literal["chromatic", "scale-aware"]
    key: str | None
    scale: Literal["major", "natural_minor"] | None
    duration_seconds: float
    notes: list[QuantizedNote]


def quantize_melody(
    analysis: PitchAnalysis, config: QuantizationConfig | None = None,
) -> QuantizedMelody:
    """Snap existing note events; equal-distance ties choose the higher note.

    Frames are not quantized or converted into new notes. Input objects are
    read only, and note times and durations are copied without rounding.
    """
    config = config or QuantizationConfig()
    candidates = list(range(128))
    if config.mode == "scale-aware":
        tonic = KEYS[config.key]
        allowed = {(tonic + offset) % 12 for offset in SCALES[config.scale]}
        candidates = [note for note in candidates if note % 12 in allowed]
    notes: list[QuantizedNote] = []
    for original in analysis.notes:
        pitch = original.midi_pitch
        if not math.isfinite(pitch) or not 0 <= pitch <= 127:
            raise ValueError("Original MIDI pitch must be finite and between 0 and 127")
        corrected = min(candidates, key=lambda note: (abs(note - pitch), -note))
        notes.append(QuantizedNote(
            original_midi_pitch=pitch, corrected_midi_pitch=corrected,
            original_note_name=original.note_name,
            corrected_note_name=midi_to_note_name(corrected),
            correction_cents=100 * (corrected - pitch),
            start_time=original.start_time, end_time=original.end_time,
            duration=original.duration, median_pitch_hz=original.median_pitch_hz,
            confidence=original.confidence, voiced_probability=original.voiced_probability,
        ))
    return QuantizedMelody(
        mode=config.mode, key=config.key, scale=config.scale,
        duration_seconds=analysis.duration_seconds, notes=notes,
    )

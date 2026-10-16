"""JSON models for an uncorrected vocal pitch analysis."""

from pydantic import BaseModel


class PitchFrame(BaseModel):
    time_seconds: float
    f0_hz: float | None
    midi_pitch: float | None
    voiced: bool
    voiced_probability: float | None


class NoteEvent(BaseModel):
    midi_note: int
    note_name: str
    midi_pitch: float
    start_time: float
    end_time: float
    duration: float
    median_pitch_hz: float
    pitch_deviation_cents: float
    confidence: float | None = None
    voiced_probability: float | None = None


class PitchAnalysis(BaseModel):
    detector: str = "librosa.pyin"
    duration_seconds: float
    sample_rate: int
    hop_length: int
    frame_length: int
    fmin_hz: float
    fmax_hz: float
    frames: list[PitchFrame]
    notes: list[NoteEvent]

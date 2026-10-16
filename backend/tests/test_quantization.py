"""Quantization rules and API preservation tests without audio inference."""

import json
import math
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.audio.jobs import AudioJob
from backend.app.audio.pitch_models import NoteEvent, PitchAnalysis, PitchFrame
from backend.app.audio.quantization import QuantizationConfig, quantize_melody
from backend.app.main import create_app


def analysis(pitches: list[float]) -> PitchAnalysis:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    notes = []
    for index, pitch in enumerate(pitches):
        nearest = math.floor(pitch + 0.5)
        notes.append(NoteEvent(
            midi_note=nearest, note_name=f"{names[nearest % 12]}{nearest // 12 - 1}",
            midi_pitch=pitch, start_time=index + 0.123, end_time=index + 0.987,
            duration=0.864, median_pitch_hz=440 * 2 ** ((pitch - 69) / 12),
            pitch_deviation_cents=100 * (pitch - nearest), voiced_probability=0.95,
        ))
    return PitchAnalysis(
        duration_seconds=max(1, len(pitches)), sample_rate=16000, hop_length=160,
        frame_length=1024, fmin_hz=65, fmax_hz=1047, notes=notes,
        frames=[PitchFrame(time_seconds=0, f0_hz=None, midi_pitch=None,
                           voiced=False, voiced_probability=0)],
    )


@pytest.mark.parametrize("pitch,expected,name,cents", [
    (60.35, 60, "C4", -35), (61.58, 62, "D4", 42),
    (61.499999, 61, "C#4", -49.9999), (61.5, 62, "D4", 50),
    (61.500001, 62, "D4", 49.9999),
    (59.51, 60, "C4", 49), (71.51, 72, "C5", 49),
    (0, 0, "C-1", 0), (127, 127, "G9", 0),
])
def test_chromatic(pitch: float, expected: int, name: str, cents: float) -> None:
    original = analysis([pitch])
    before = original.model_dump()
    result = quantize_melody(original)
    note = result.notes[0]
    assert note.original_midi_pitch == pitch
    assert note.corrected_midi_pitch == expected
    assert note.original_note_name == original.notes[0].note_name
    assert note.corrected_note_name == name
    assert note.correction_cents == pytest.approx(cents)
    assert (note.start_time, note.end_time, note.duration) == (0.123, 0.987, 0.864)
    assert original.model_dump() == before


def test_all_chromatic_notes_stay_unchanged() -> None:
    result = quantize_melody(analysis(list(range(60, 72))))
    assert [note.corrected_midi_pitch for note in result.notes] == list(range(60, 72))
    assert all(note.correction_cents == 0 for note in result.notes)


@pytest.mark.parametrize("key,scale,pitch,expected", [
    ("C", "major", 61, 62), ("C", "major", 60.8, 60),
    ("C", "natural_minor", 64, 65), ("C", "natural_minor", 69, 70),
    ("A", "minor", 66, 67), ("B", "major", 60, 61),
    ("Db", "major", 60.9, 61), ("C", "major", 71.6, 72),
])
def test_scale_aware(key: str, scale: str, pitch: float, expected: int) -> None:
    config = QuantizationConfig(mode="scale-aware", key=key, scale=scale)
    assert quantize_melody(analysis([pitch]), config).notes[0].corrected_midi_pitch == expected


@pytest.mark.parametrize("tonic,key", list(enumerate(
    ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)))
@pytest.mark.parametrize("scale,intervals", [
    ("major", (0, 2, 4, 5, 7, 9, 11)),
    ("natural_minor", (0, 2, 3, 5, 7, 8, 10)),
])
def test_twelve_tonics_and_nearest_scale_pitch(
    tonic: int, key: str, scale: str, intervals: tuple[int, ...]
) -> None:
    pitches = [n + 0.3 for n in range(48, 72)]
    result = quantize_melody(analysis(pitches), QuantizationConfig(mode="scale-aware", key=key, scale=scale))
    allowed = {(tonic + interval) % 12 for interval in intervals}
    for pitch, note in zip(pitches, result.notes):
        assert note.corrected_midi_pitch % 12 in allowed
        assert all(abs(note.corrected_midi_pitch - pitch) <= abs(candidate - pitch)
                   for candidate in range(128) if candidate % 12 in allowed)


def test_silence_and_empty_sequence_create_no_notes() -> None:
    original = analysis([])
    before = original.model_dump()
    for config in (QuantizationConfig(), QuantizationConfig(mode="scale-aware", key="C", scale="major")):
        assert quantize_melody(original, config).notes == []
    assert original.model_dump() == before


@pytest.mark.parametrize("parameters", [
    {"mode": "wrong"}, {"key": "H"}, {"scale": "dorian"},
    {"mode": "scale-aware"}, {"mode": "scale-aware", "key": "C"},
    {"mode": "scale-aware", "scale": "major"}, {"key": "../C"},
])
def test_invalid_parameters(parameters: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        QuantizationConfig(**parameters)


@pytest.mark.parametrize("pitch", [float("nan"), float("inf"), -1, 128])
def test_invalid_original_pitch(pitch: float) -> None:
    original = analysis([60])
    original.notes[0].midi_pitch = pitch
    with pytest.raises(ValueError):
        quantize_melody(original)


@pytest.fixture
def ready_job(tmp_path: Path):
    app = create_app(audio_root=tmp_path)
    audio_id = str(uuid.uuid4())
    directory = tmp_path / audio_id
    directory.mkdir()
    source = directory / "original.wav"
    source.write_bytes(b"original audio sentinel")
    (directory / "vocals.wav").write_bytes(b"vocal audio sentinel")
    (directory / "instrumental.wav").write_bytes(b"instrumental audio sentinel")
    original = analysis([60.35, 61.58, 61.0])
    (directory / "pitch_analysis.json").write_text(original.model_dump_json(), encoding="utf-8")
    app.state.audio_jobs.jobs[audio_id] = AudioJob(
        audio_id, source, status="completed", pitch_analysis=original,
    )
    with TestClient(app) as client:
        yield client, audio_id, directory


def test_api_default_export_retrieval_and_preservation(ready_job) -> None:
    client, audio_id, directory = ready_job
    originals = {path.name: path.read_bytes() for path in directory.iterdir()}
    pitch_before = client.get(f"/api/audio/{audio_id}/pitch").json()
    assert client.get(f"/api/audio/{audio_id}/quantized").status_code == 409
    response = client.post(f"/api/audio/{audio_id}/quantize")
    assert response.status_code == 200
    assert response.json()["mode"] == "chromatic"
    assert [n["corrected_midi_pitch"] for n in response.json()["notes"]] == [60, 62, 61]
    assert client.get(f"/api/audio/{audio_id}/quantized").json() == response.json()
    assert json.loads((directory / "quantized_melody.json").read_text(encoding="utf-8")) == response.json()
    scaled = client.post(f"/api/audio/{audio_id}/quantize", json={
        "mode": "scale-aware", "key": "C", "scale": "major",
    })
    assert scaled.status_code == 200
    assert [n["corrected_midi_pitch"] for n in scaled.json()["notes"]] == [60, 62, 62]
    assert client.get(f"/api/audio/{audio_id}/quantized").json() == scaled.json()
    for name, content in originals.items():
        assert (directory / name).read_bytes() == content
    assert client.get(f"/api/audio/{audio_id}/pitch").json() == pitch_before
    for old, new in zip(pitch_before["notes"], scaled.json()["notes"]):
        for field in ("start_time", "end_time", "duration"):
            assert old[field] == new[field]


def test_api_invalid_parameters_and_missing_analysis(ready_job) -> None:
    client, audio_id, directory = ready_job
    for parameters in ({"mode": "wrong"}, {"key": "H"}, {"scale": "wrong"}, {"mode": "scale-aware"}):
        assert client.post(f"/api/audio/{audio_id}/quantize", json=parameters).status_code == 422
    assert not (directory / "quantized_melody.json").exists()
    assert client.post("/api/audio/not-a-uuid/quantize").status_code == 404
    client.app.state.audio_jobs.jobs[audio_id].pitch_analysis = None
    assert client.post(f"/api/audio/{audio_id}/quantize").status_code == 409


def test_export_failure_preserves_previous_result(ready_job, monkeypatch: pytest.MonkeyPatch) -> None:
    client, audio_id, directory = ready_job
    previous = client.post(f"/api/audio/{audio_id}/quantize").json()
    saved = (directory / "quantized_melody.json").read_bytes()

    def failed_replace(self: Path, target: Path) -> Path:
        raise OSError("mock disk failure")

    monkeypatch.setattr(Path, "replace", failed_replace)
    assert client.post(f"/api/audio/{audio_id}/quantize", json={
        "mode": "scale-aware", "key": "C", "scale": "major",
    }).status_code == 500
    assert (directory / "quantized_melody.json").read_bytes() == saved
    assert not (directory / "quantized_melody.json.tmp").exists()
    assert client.get(f"/api/audio/{audio_id}/quantized").json() == previous

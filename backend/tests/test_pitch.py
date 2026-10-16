"""Synthetic pYIN, segmentation, and pitch API tests; no model downloads."""

import io
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.audio.pitch import InvalidPitchAudioError, PyinPitchDetector
from backend.app.audio.pitch_models import PitchFrame
from backend.app.audio.segmentation import segment_notes
from backend.app.main import create_app


RATE = 16000


def tone(hz: float, seconds: float = 0.8) -> np.ndarray:
    times = np.arange(round(RATE * seconds)) / RATE
    return (0.3 * np.sin(2 * np.pi * hz * times)).astype(np.float32)


def write_audio(tmp_path: Path, samples: np.ndarray) -> Path:
    source = tmp_path / "vocals.wav"
    sf.write(source, samples, RATE, subtype="PCM_16")
    return source


@pytest.mark.parametrize("hz,midi,name", [(440, 69, "A4"), (261.63, 60, "C4")])
def test_single_notes(tmp_path: Path, hz: float, midi: int, name: str) -> None:
    result = PyinPitchDetector().detect(write_audio(tmp_path, tone(hz)))
    assert len(result.notes) == 1
    note = result.notes[0]
    assert (note.midi_note, note.note_name) == (midi, name)
    assert note.median_pitch_hz == pytest.approx(hz, rel=0.01)
    assert abs(note.pitch_deviation_cents) < 12
    assert note.start_time < 0.08
    assert note.end_time == pytest.approx(0.8, abs=0.05)
    assert note.duration == pytest.approx(note.end_time - note.start_time)
    assert note.confidence is None
    assert 0 <= note.voiced_probability <= 1
    assert all(0 <= frame.time_seconds < 0.8 for frame in result.frames)


def test_silence_has_no_pitch_or_notes(tmp_path: Path) -> None:
    result = PyinPitchDetector().detect(write_audio(tmp_path, np.zeros(RATE)))
    assert result.notes == []
    assert len(result.frames) == 100
    assert all(not f.voiced and f.f0_hz is None and f.midi_pitch is None for f in result.frames)
    # Must be strict JSON, without NaN or Infinity.
    json.dumps(result.model_dump(), allow_nan=False)


@pytest.mark.parametrize("gap_seconds", [0, 0.2])
def test_sequential_notes_preserve_timing(tmp_path: Path, gap_seconds: float) -> None:
    samples = np.concatenate([tone(261.63, 0.6), np.zeros(round(RATE * gap_seconds)), tone(440, 0.6)])
    result = PyinPitchDetector().detect(write_audio(tmp_path, samples))
    assert [n.midi_note for n in result.notes] == [60, 69]
    assert result.notes[0].end_time == pytest.approx(0.6, abs=0.08)
    assert result.notes[1].start_time == pytest.approx(0.6 + gap_seconds, abs=0.08)
    assert result.notes[1].end_time <= len(samples) / RATE
    if gap_seconds:
        middle = [f for f in result.frames if 0.65 < f.time_seconds < 0.75]
        assert middle and all(not f.voiced and f.f0_hz is None for f in middle)


@pytest.mark.parametrize("cents", [-25, 25])
def test_out_of_tune_pitch_is_preserved(tmp_path: Path, cents: float) -> None:
    hz = 440 * 2 ** (cents / 1200)
    result = PyinPitchDetector().detect(write_audio(tmp_path, tone(hz)))
    assert len(result.notes) == 1
    note = result.notes[0]
    assert note.midi_note == 69
    assert note.pitch_deviation_cents == pytest.approx(cents, abs=11)
    assert note.midi_pitch == pytest.approx(69 + cents / 100, abs=0.11)
    assert any(f.midi_pitch is not None and abs(f.midi_pitch - 69) > 0.1 for f in result.frames)


def test_short_vibrato_is_one_note(tmp_path: Path) -> None:
    times = np.arange(RATE) / RATE
    frequencies = 440 * 2 ** (0.35 * np.sin(2 * np.pi * 5 * times) / 12)
    samples = 0.3 * np.sin(2 * np.pi * np.cumsum(frequencies) / RATE)
    result = PyinPitchDetector().detect(write_audio(tmp_path, samples))
    assert len(result.notes) == 1
    assert result.notes[0].midi_note == 69
    pitches = [f.midi_pitch for f in result.frames if f.voiced]
    assert max(pitches) - min(pitches) > 0.3


def test_segmentation_bridges_dropouts_and_ignores_pitch_glitch() -> None:
    frames = []
    for index in range(100):
        voiced = index not in {45, 46, 47}
        midi = 72.0 if index == 25 else 69.25
        frames.append(PitchFrame(
            time_seconds=index * 0.01, voiced=voiced,
            f0_hz=440 * 2 ** ((midi - 69) / 12) if voiced else None,
            midi_pitch=midi if voiced else None, voiced_probability=0.9 if voiced else 0,
        ))
    notes = segment_notes(frames, 1.0, 0.01)
    assert len(notes) == 1
    assert notes[0].pitch_deviation_cents == pytest.approx(25)
    assert notes[0].duration == pytest.approx(1)
    assert frames[46].midi_pitch is None


@pytest.mark.parametrize("contents", [b"not audio", b"RIFF", b""])
def test_invalid_audio(tmp_path: Path, contents: bytes) -> None:
    source = tmp_path / "broken.wav"
    source.write_bytes(contents)
    with pytest.raises(InvalidPitchAudioError):
        PyinPitchDetector().detect(source)


def test_overlong_audio_is_rejected(tmp_path: Path) -> None:
    source = write_audio(tmp_path, np.zeros(31 * RATE))
    with pytest.raises(InvalidPitchAudioError):
        PyinPitchDetector().detect(source)


class CopySeparator:
    def separate(self, source: Path, output_dir: Path) -> None:
        for name in ("vocals.wav", "instrumental.wav"):
            (output_dir / name).write_bytes(source.read_bytes())


def separated_upload(client: TestClient) -> str:
    stream = io.BytesIO()
    sf.write(stream, tone(440), RATE, format="WAV", subtype="PCM_16")
    response = client.post("/api/audio/upload", files={"file": ("song.wav", stream.getvalue())})
    assert response.status_code == 201
    audio_id = response.json()["audio_id"]
    assert client.post(f"/api/audio/{audio_id}/separate").status_code == 202
    for _ in range(100):
        if client.get(f"/api/audio/{audio_id}/status").json()["status"] == "completed":
            return audio_id
        time.sleep(0.01)
    pytest.fail("Mock separation did not complete")


def test_pitch_api_and_debug_export(tmp_path: Path) -> None:
    with TestClient(create_app(separator=CopySeparator(), audio_root=tmp_path)) as client:
        audio_id = separated_upload(client)
        assert client.get(f"/api/audio/{audio_id}/pitch").status_code == 409
        before = (tmp_path / audio_id / "vocals.wav").read_bytes()
        response = client.post(f"/api/audio/{audio_id}/analyze-pitch")
        assert response.status_code == 200
        assert response.json()["notes"][0]["note_name"] == "A4"
        assert client.get(f"/api/audio/{audio_id}/pitch").json() == response.json()
        assert client.post(f"/api/audio/{audio_id}/analyze-pitch").json() == response.json()
        export = tmp_path / audio_id / "pitch_analysis.json"
        assert json.loads(export.read_text(encoding="utf-8")) == response.json()
        assert (tmp_path / audio_id / "vocals.wav").read_bytes() == before
        assert client.get(f"/api/audio/{audio_id}/status").json()["status"] == "completed"


def test_pitch_requires_completed_separation(tmp_path: Path) -> None:
    with TestClient(create_app(audio_root=tmp_path)) as client:
        assert client.post("/api/audio/not-a-uuid/analyze-pitch").status_code == 404
        assert client.get("/api/audio/not-a-uuid/pitch").status_code == 404
        stream = io.BytesIO()
        sf.write(stream, tone(440), RATE, format="WAV")
        audio_id = client.post("/api/audio/upload", files={"file": ("a.wav", stream.getvalue())}).json()["audio_id"]
        assert client.post(f"/api/audio/{audio_id}/analyze-pitch").status_code == 409


@pytest.mark.parametrize("error,status", [(InvalidPitchAudioError("bad WAV"), 422), (RuntimeError("failed"), 500)])
def test_pitch_errors_allow_retry_without_changing_separation(
    tmp_path: Path, error: Exception, status: int
) -> None:
    class FailedDetector:
        def detect(self, source: Path):
            raise error

    app = create_app(separator=CopySeparator(), audio_root=tmp_path, pitch_detector=FailedDetector())
    with TestClient(app) as client:
        audio_id = separated_upload(client)
        assert client.post(f"/api/audio/{audio_id}/analyze-pitch").status_code == status
        assert client.get(f"/api/audio/{audio_id}/pitch").status_code == 409
        assert not (tmp_path / audio_id / "pitch_analysis.json").exists()
        app.state.pitch_detector = PyinPitchDetector()
        assert client.post(f"/api/audio/{audio_id}/analyze-pitch").status_code == 200
        assert client.get(f"/api/audio/{audio_id}/status").json()["status"] == "completed"

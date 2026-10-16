"""Harmony interval, timing, validation, and API tests without inference."""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.audio.harmony import HarmonyConfig, generate_harmony
from backend.app.audio.jobs import AudioJob
from backend.app.audio.music import midi_to_note_name
from backend.app.audio.quantization import QuantizedMelody, QuantizedNote
from backend.app.main import create_app


def melody(pitches: list[int]) -> QuantizedMelody:
    return QuantizedMelody(
        mode="chromatic", key=None, scale=None, duration_seconds=len(pitches) + 0.3,
        notes=[QuantizedNote(
            original_midi_pitch=pitch + 0.25, corrected_midi_pitch=pitch,
            original_note_name=midi_to_note_name(pitch), corrected_note_name=midi_to_note_name(pitch),
            correction_cents=-25, start_time=index + 0.1, end_time=index + 0.7,
            duration=0.6, median_pitch_hz=440 * 2 ** ((pitch - 69) / 12),
            confidence=None, voiced_probability=0.9,
        ) for index, pitch in enumerate(pitches)],
    )


@pytest.mark.parametrize("interval,direction,target,name", [
    ("major_third", "above", 64, "E4"), ("minor_third", "above", 63, "D#4"),
    ("perfect_fourth", "above", 65, "F4"), ("perfect_fifth", "above", 67, "G4"),
    ("octave", "above", 72, "C5"), ("major_third", "below", 56, "G#3"),
    ("minor_third", "below", 57, "A3"), ("perfect_fourth", "below", 55, "G3"),
    ("perfect_fifth", "below", 53, "F3"), ("octave", "below", 48, "C3"),
])
def test_fixed_intervals(interval: str, direction: str, target: int, name: str) -> None:
    source = melody([60])
    before = source.model_dump()
    result = generate_harmony(source, HarmonyConfig(interval=interval, direction=direction))
    note = result.notes[0]
    assert (note.original_midi_note, note.original_note_name) == (60, "C4")
    assert (note.harmony_midi_note, note.harmony_note_name) == (target, name)
    assert source.model_dump() == before


@pytest.mark.parametrize("key,scale,interval,direction,pitches,expected", [
    ("C", "major", "diatonic_third", "above", [60, 62, 64], [64, 65, 67]),
    ("A", "natural_minor", "diatonic_third", "above", [57, 59, 60], [60, 62, 64]),
    ("C", "major", "diatonic_third", "below", [60, 62, 64], [57, 59, 60]),
    ("A", "minor", "diatonic_third", "below", [57, 59, 60], [53, 55, 57]),
    ("C", "major", "diatonic_sixth", "above", [60, 62, 64], [69, 71, 72]),
    ("C", "major", "diatonic_sixth", "below", [60, 62, 64], [52, 53, 55]),
    ("A", "natural_minor", "diatonic_sixth", "above", [57, 59, 60], [65, 67, 69]),
    ("A", "natural_minor", "diatonic_sixth", "below", [57, 59, 60], [48, 50, 52]),
    ("C", "major", "diatonic_third", "above", [59, 71], [62, 74]),
    ("Db", "major", "diatonic_third", "above", [61], [65]),
])
def test_diatonic_examples(
    key: str, scale: str, interval: str, direction: str,
    pitches: list[int], expected: list[int],
) -> None:
    source = melody(pitches)
    before = source.model_dump()
    result = generate_harmony(source, HarmonyConfig(
        interval=interval, direction=direction, key=key, scale=scale,
    ))
    assert [note.harmony_midi_note for note in result.notes] == expected
    assert source.model_dump() == before


@pytest.mark.parametrize("tonic,key", list(enumerate(
    ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)))
@pytest.mark.parametrize("scale,offsets", [
    ("major", (0, 2, 4, 5, 7, 9, 11)), ("natural_minor", (0, 2, 3, 5, 7, 8, 10)),
])
def test_all_keys_degrees_and_directions(
    tonic: int, key: str, scale: str, offsets: tuple[int, ...]
) -> None:
    allowed = [midi for midi in range(128) if (midi - tonic) % 12 in offsets]
    pitches = [midi for midi in allowed if 48 <= midi < 72]
    for interval, degrees in (("diatonic_third", 2), ("diatonic_sixth", 5)):
        for direction, sign in (("above", 1), ("below", -1)):
            result = generate_harmony(melody(pitches), HarmonyConfig(
                interval=interval, direction=direction, key=key, scale=scale,
            ))
            assert [note.harmony_midi_note for note in result.notes] == [
                allowed[allowed.index(pitch) + sign * degrees] for pitch in pitches
            ]


def test_timing_and_rests_are_preserved() -> None:
    source = melody([60, 62, 64])
    result = generate_harmony(source, HarmonyConfig(interval="perfect_fifth"))
    assert result.duration_seconds == source.duration_seconds
    assert len(result.notes) == len(source.notes)
    for original, harmony in zip(source.notes, result.notes):
        assert (harmony.start_time, harmony.end_time, harmony.duration) == (
            original.start_time, original.end_time, original.duration,
        )
    assert result.notes[1].start_time - result.notes[0].end_time == pytest.approx(0.4)


@pytest.mark.parametrize("config", [
    HarmonyConfig(interval="octave", direction="below"),
    HarmonyConfig(interval="diatonic_third", key="C", scale="major"),
])
def test_empty_sequence(config: HarmonyConfig) -> None:
    assert generate_harmony(melody([]), config).notes == []


def test_out_of_scale_is_rejected_without_changing_source() -> None:
    source = melody([60, 61])
    before = source.model_dump()
    with pytest.raises(ValueError, match="C#4.*outside.*C major"):
        generate_harmony(source, HarmonyConfig(interval="diatonic_third", key="C", scale="major"))
    assert source.model_dump() == before


@pytest.mark.parametrize("pitch,interval,direction,key,scale", [
    (0, "perfect_fifth", "below", None, None), (127, "octave", "above", None, None),
    (0, "diatonic_third", "below", "C", "major"),
    (127, "diatonic_sixth", "above", "G", "major"),
    (-1, "major_third", "above", None, None), (128, "major_third", "below", None, None),
])
def test_midi_boundaries_reject_overflow(
    pitch: int, interval: str, direction: str, key: str | None, scale: str | None,
) -> None:
    with pytest.raises(ValueError, match="0-127"):
        generate_harmony(melody([pitch]), HarmonyConfig(
            interval=interval, direction=direction, key=key, scale=scale,
        ))


def test_midi_boundaries_accept_exact_limits() -> None:
    assert generate_harmony(melody([12]), HarmonyConfig(interval="octave", direction="below")).notes[0].harmony_midi_note == 0
    assert generate_harmony(melody([115]), HarmonyConfig(interval="octave")).notes[0].harmony_midi_note == 127


def test_fractional_source_is_not_requantized() -> None:
    source = melody([60])
    source.notes[0].corrected_midi_pitch = 60.2
    with pytest.raises(ValueError, match="integer MIDI"):
        generate_harmony(source, HarmonyConfig(interval="major_third"))


@pytest.mark.parametrize("parameters", [
    {"interval": "tritone"}, {"interval": "octave", "direction": "sideways"},
    {"interval": "octave", "key": "H"}, {"interval": "octave", "scale": "dorian"},
    {"interval": "diatonic_third"}, {"interval": "diatonic_sixth", "key": "C"},
    {"interval": "diatonic_third", "scale": "major"}, {},
])
def test_invalid_parameters(parameters: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        HarmonyConfig(**parameters)


@pytest.mark.parametrize("field,value", [("start_time", -1), ("end_time", float("nan")), ("duration", 0.1)])
def test_invalid_timing_is_rejected(field: str, value: float) -> None:
    source = melody([60])
    setattr(source.notes[0], field, value)
    with pytest.raises(ValueError, match="invalid timing"):
        generate_harmony(source, HarmonyConfig(interval="octave"))


def test_overlapping_events_are_rejected() -> None:
    source = melody([60, 62])
    source.notes[1].start_time = 0.5
    source.notes[1].end_time = 1.1
    with pytest.raises(ValueError, match="overlaps"):
        generate_harmony(source, HarmonyConfig(interval="octave"))


@pytest.fixture
def ready_job(tmp_path: Path) -> Iterator[tuple[TestClient, str, Path]]:
    app = create_app(audio_root=tmp_path)
    audio_id = str(uuid.uuid4())
    directory = tmp_path / audio_id
    directory.mkdir()
    source = directory / "original.wav"
    for name in ("original.wav", "vocals.wav", "instrumental.wav", "pitch_analysis.json"):
        (directory / name).write_bytes(b"unchanged original artifact")
    quantized = melody([60, 62, 64])
    (directory / "quantized_melody.json").write_text(quantized.model_dump_json(), encoding="utf-8")
    app.state.audio_jobs.jobs[audio_id] = AudioJob(
        audio_id, source, status="completed", quantized_melody=quantized,
    )
    with TestClient(app) as client:
        yield client, audio_id, directory


def test_api_export_retrieval_and_preservation(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    quantized_before = client.get(f"/api/audio/{audio_id}/quantized").json()
    assert client.get(f"/api/audio/{audio_id}/harmony").status_code == 409
    result = client.post(f"/api/audio/{audio_id}/harmony", json={
        "interval": "diatonic_third", "direction": "above", "key": "C", "scale": "major",
    })
    assert result.status_code == 200
    assert [note["harmony_midi_note"] for note in result.json()["notes"]] == [64, 65, 67]
    assert client.get(f"/api/audio/{audio_id}/harmony").json() == result.json()
    assert json.loads((directory / "harmony_melody.json").read_text(encoding="utf-8")) == result.json()
    for name, content in before.items():
        assert (directory / name).read_bytes() == content
    assert client.get(f"/api/audio/{audio_id}/quantized").json() == quantized_before
    for source, harmony in zip(quantized_before["notes"], result.json()["notes"]):
        assert all(source[field] == harmony[field] for field in ("start_time", "end_time", "duration"))


def test_api_invalid_parameters_and_missing_quantization(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    for bad in ({"interval": "bad"}, {"interval": "octave", "key": "H"},
                {"interval": "octave", "direction": "bad"}, {"interval": "octave", "scale": "bad"}):
        assert client.post(f"/api/audio/{audio_id}/harmony", json=bad).status_code == 422
    config = {"interval": "octave"}
    assert client.post("/api/audio/not-a-uuid/harmony", json=config).status_code == 404
    assert client.get("/api/audio/not-a-uuid/harmony").status_code == 404
    client.app.state.audio_jobs.jobs[audio_id].quantized_melody = None
    assert client.post(f"/api/audio/{audio_id}/harmony", json=config).status_code == 409
    assert not (directory / "harmony_melody.json").exists()


def test_api_out_of_scale_does_not_replace_previous_harmony(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    previous = client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "octave"}).json()
    saved = (directory / "harmony_melody.json").read_bytes()
    client.app.state.audio_jobs.jobs[audio_id].quantized_melody.notes[0].corrected_midi_pitch = 61
    result = client.post(f"/api/audio/{audio_id}/harmony", json={
        "interval": "diatonic_third", "key": "C", "scale": "major",
    })
    assert result.status_code == 422
    assert "outside" in result.json()["detail"]
    assert client.get(f"/api/audio/{audio_id}/harmony").json() == previous
    assert (directory / "harmony_melody.json").read_bytes() == saved


def test_export_failure_preserves_previous_harmony(
    ready_job: tuple[TestClient, str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, audio_id, directory = ready_job
    previous = client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "octave"}).json()
    saved = (directory / "harmony_melody.json").read_bytes()

    def failed_replace(self: Path, target: Path) -> Path:
        raise OSError("mock disk failure")

    monkeypatch.setattr(Path, "replace", failed_replace)
    assert client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "perfect_fifth"}).status_code == 500
    assert client.get(f"/api/audio/{audio_id}/harmony").json() == previous
    assert (directory / "harmony_melody.json").read_bytes() == saved
    assert not (directory / "harmony_melody.json.tmp").exists()


def test_requantization_invalidates_cached_harmony(ready_job: tuple[TestClient, str, Path]) -> None:
    from backend.tests.test_quantization import analysis

    client, audio_id, directory = ready_job
    assert client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "octave"}).status_code == 200
    snapshot = (directory / "harmony_melody.json").read_bytes()
    client.app.state.audio_jobs.jobs[audio_id].pitch_analysis = analysis([60, 62, 64])
    assert client.post(f"/api/audio/{audio_id}/quantize").status_code == 200
    assert client.get(f"/api/audio/{audio_id}/harmony").status_code == 409
    assert (directory / "harmony_melody.json").read_bytes() == snapshot
    assert client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "perfect_fifth"}).status_code == 200

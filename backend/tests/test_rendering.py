"""MIDI and rendering tests with mocked external synthesis and no models."""

import json
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import mido
import numpy as np
import pretty_midi
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.audio.harmony import HarmonyMelody, HarmonyNote
from backend.app.audio.jobs import AudioJob
from backend.app.audio.midi_renderer import MidiRenderer
from backend.app.audio.mixing import SAMPLE_RATE, mix_preview, validate_wav
from backend.app.audio.music import midi_to_note_name
from backend.app.audio.piano_renderer import FluidSynthPianoRenderer, RELEASE_SECONDS
from backend.app.audio.render_errors import MissingRenderDependency, RenderError, RenderInputError
from backend.app.audio.rendering import RenderConfig
from backend.app.main import create_app


def harmony(pitches: list[int] | None = None) -> HarmonyMelody:
    pitches = [60, 64] if pitches is None else pitches
    return HarmonyMelody(
        interval="major_third", direction="above", key=None, scale=None,
        duration_seconds=max(1, len(pitches) * 0.25 + 0.2),
        notes=[HarmonyNote(
            original_midi_note=pitch, harmony_midi_note=pitch,
            original_note_name=midi_to_note_name(pitch), harmony_note_name=midi_to_note_name(pitch),
            start_time=index * 0.25 + 0.1, end_time=index * 0.25 + 0.2, duration=0.1,
        ) for index, pitch in enumerate(pitches)],
    )


def write_harmony(tmp_path: Path, melody: HarmonyMelody) -> Path:
    source = tmp_path / "harmony_melody.json"
    source.write_text(melody.model_dump_json(), encoding="utf-8")
    return source


def test_midi_pitches_timings_rests_program_and_determinism(tmp_path: Path) -> None:
    original = harmony()
    source = write_harmony(tmp_path, original)
    before = source.read_bytes()
    first, second = tmp_path / "one.mid", tmp_path / "two.mid"
    MidiRenderer().render(source, first)
    MidiRenderer().render(source, second)
    assert first.read_bytes() == second.read_bytes()
    assert source.read_bytes() == before
    data = pretty_midi.PrettyMIDI(str(first))
    assert len(data.instruments) == 1
    piano = data.instruments[0]
    assert piano.program == 0 and not piano.is_drum
    assert [n.pitch for n in piano.notes] == [60, 64]
    assert all(n.velocity == 90 for n in piano.notes)
    for expected, actual in zip(original.notes, piano.notes):
        assert actual.start == pytest.approx(expected.start_time, abs=1 / 44100)
        assert actual.end == pytest.approx(expected.end_time, abs=1 / 44100)
    assert piano.notes[1].start - piano.notes[0].end == pytest.approx(0.15, abs=1 / 44100)
    assert data.get_end_time() == pytest.approx(original.duration_seconds, abs=1 / 44100)


@pytest.mark.parametrize("velocity", [1, 53, 127])
def test_velocity_configuration(tmp_path: Path, velocity: int) -> None:
    source = write_harmony(tmp_path, harmony())
    output = tmp_path / "harmony.mid"
    MidiRenderer().render(source, output, velocity)
    assert all(note.velocity == velocity for note in pretty_midi.PrettyMIDI(str(output)).instruments[0].notes)


def test_all_midi_pitches(tmp_path: Path) -> None:
    # Shorten the fixture so all 128 sequential pitches stay within 30 seconds.
    melody = harmony(list(range(128)))
    melody.duration_seconds = 13
    for index, note in enumerate(melody.notes):
        note.start_time = index * 0.1
        note.end_time = index * 0.1 + 0.05
        note.duration = 0.05
    output = tmp_path / "all.mid"
    MidiRenderer().render(write_harmony(tmp_path, melody), output)
    assert [n.pitch for n in pretty_midi.PrettyMIDI(str(output)).instruments[0].notes] == list(range(128))


def test_empty_melody_valid_midi_and_silent_piano(tmp_path: Path) -> None:
    output = tmp_path / "empty.mid"
    MidiRenderer().render(write_harmony(tmp_path, harmony([])), output)
    assert all(not inst.notes for inst in pretty_midi.PrettyMIDI(str(output)).instruments)
    assert any(message.type == "program_change" and message.program == 0
               for track in mido.MidiFile(output).tracks for message in track)
    piano = tmp_path / "empty.wav"
    FluidSynthPianoRenderer().render(output, piano, 1.0, None)
    assert validate_wav(piano) == 1
    assert not np.any(sf.read(piano)[0])


@pytest.mark.parametrize("velocity", [0, -1, 128, 90.5, True])
def test_invalid_velocity(tmp_path: Path, velocity: int) -> None:
    with pytest.raises(RenderInputError):
        MidiRenderer().render(write_harmony(tmp_path, harmony()), tmp_path / "bad.mid", velocity)
    with pytest.raises(ValidationError):
        RenderConfig(velocity=velocity)


def test_invalid_harmony_json_and_overlap(tmp_path: Path) -> None:
    source = tmp_path / "harmony_melody.json"
    source.write_text("not json", encoding="utf-8")
    with pytest.raises(RenderInputError):
        MidiRenderer().render(source, tmp_path / "bad.mid")
    melody = harmony()
    melody.notes[1].start_time = 0.15
    melody.notes[1].end_time = 0.25
    with pytest.raises(RenderInputError, match="overlapping"):
        MidiRenderer().render(write_harmony(tmp_path, melody), tmp_path / "bad.mid")


def test_missing_soundfont(tmp_path: Path) -> None:
    with pytest.raises(MissingRenderDependency, match="HARMONYFINDER_SOUNDFONT"):
        FluidSynthPianoRenderer(soundfont=tmp_path / "missing.sf2").render(tmp_path / "a.mid", tmp_path / "a.wav", 1, 0.5)


def test_missing_fluidsynth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    font = tmp_path / "user.sf2"
    font.write_bytes(b"test fixture")
    monkeypatch.setattr("backend.app.audio.piano_renderer.shutil.which", lambda name: None)
    with pytest.raises(MissingRenderDependency, match="Install FluidSynth"):
        FluidSynthPianoRenderer(font).render(tmp_path / "a.mid", tmp_path / "a.wav", 1, 0.5)


def test_fluidsynth_command_tail_format_and_peak_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_harmony(tmp_path, harmony([60]))
    midi = tmp_path / "harmony.mid"
    MidiRenderer().render(source, midi)
    before = midi.read_bytes()
    font = tmp_path / "user piano.sf2"
    font.write_bytes(b"mock SoundFont")
    monkeypatch.setattr("backend.app.audio.piano_renderer.shutil.which", lambda name: "fluidsynth.exe")
    commands: list[list[str]] = []

    def synth(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        playback = pretty_midi.PrettyMIDI(args[-1])
        assert playback.get_end_time() >= 0.5 + RELEASE_SECONDS - 1 / SAMPLE_RATE
        # Synthetic pulses are test fixtures, not a production piano substitute.
        samples = np.zeros((2 * SAMPLE_RATE, 2), dtype=np.float32)
        samples[round(0.1 * SAMPLE_RATE):round(0.6 * SAMPLE_RATE)] = 2
        sf.write(args[args.index("-F") + 1], samples, SAMPLE_RATE, subtype="FLOAT")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("backend.app.audio.piano_renderer.subprocess.run", synth)
    piano = tmp_path / "piano.wav"
    FluidSynthPianoRenderer(font).render(midi, piano, 1, 0.5)
    assert validate_wav(piano) == pytest.approx(1.25)
    samples, rate = sf.read(piano, always_2d=True)
    assert rate == SAMPLE_RATE and samples.shape[1] == 2
    assert not np.any(samples[:round(0.1 * SAMPLE_RATE)])
    assert np.max(np.abs(samples)) <= 0.9801
    assert commands[0][commands[0].index("-O") + 1] == "float"
    assert commands[0][-2] == str(font.resolve())
    assert commands[0][-1].endswith("playback.mid")
    assert commands[0].index("-o") < len(commands[0]) - 2
    assert midi.read_bytes() == before


def test_corrupt_synth_output_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    midi = tmp_path / "harmony.mid"
    MidiRenderer().render(write_harmony(tmp_path, harmony()), midi)
    font = tmp_path / "user.sf2"
    font.write_bytes(b"mock")
    monkeypatch.setattr("backend.app.audio.piano_renderer.shutil.which", lambda name: "fluidsynth")

    def synth(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(args[args.index("-F") + 1]).write_bytes(b"corrupt audio")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("backend.app.audio.piano_renderer.subprocess.run", synth)
    with pytest.raises(RenderError):
        FluidSynthPianoRenderer(font).render(midi, tmp_path / "bad.wav", 1, 0.5)


def test_preview_alignment_resampling_mono_and_tail(tmp_path: Path) -> None:
    original = tmp_path / "original.wav"
    piano = tmp_path / "piano.wav"
    mix = tmp_path / "mix.wav"
    sf.write(original, np.zeros(22050), 22050)
    samples = np.zeros((round(1.25 * SAMPLE_RATE), 2), dtype=np.float32)
    samples[22050] = (0.5, 0.25)
    samples[-1000:-900] = 0.1
    sf.write(piano, samples, SAMPLE_RATE, subtype="FLOAT")
    before = original.read_bytes()
    duration = mix_preview(original, piano, mix, original_gain=0.8, piano_gain=0.6)
    rendered, rate = sf.read(mix, always_2d=True)
    assert rate == SAMPLE_RATE and duration == pytest.approx(1.25, abs=1 / SAMPLE_RATE)
    assert np.argmax(np.abs(rendered[:, 0])) == 22050
    assert rendered[22050] == pytest.approx((0.3, 0.15), abs=1 / 32768)
    assert np.any(rendered[SAMPLE_RATE:])
    assert original.read_bytes() == before


def test_preview_includes_original_once_and_prevents_clipping(tmp_path: Path) -> None:
    original, piano, output = tmp_path / "original.wav", tmp_path / "piano.wav", tmp_path / "mix.wav"
    sf.write(original, np.full(22050, 0.4), 22050, subtype="FLOAT")
    sf.write(piano, np.zeros((44100, 2)), 44100)
    mix_preview(original, piano, output, original_gain=0.8, piano_gain=0.6)
    samples, _ = sf.read(output)
    assert samples[22050] == pytest.approx((0.32, 0.32), abs=0.001)
    sf.write(original, np.ones((44100, 2)), 44100, subtype="FLOAT")
    sf.write(piano, np.ones((44100, 2)), 44100, subtype="FLOAT")
    mix_preview(original, piano, output, original_gain=2, piano_gain=2)
    assert np.max(np.abs(sf.read(output)[0])) <= 0.9801


class MockPianoRenderer:
    def render(self, midi: Path, output: Path, duration_seconds: float, last_note_end: float | None) -> None:
        assert pretty_midi.PrettyMIDI(str(midi)).instruments[0].program == 0
        samples = np.zeros((round((duration_seconds + RELEASE_SECONDS) * SAMPLE_RATE), 2))
        samples[4410:8820] = 0.2
        sf.write(output, samples, SAMPLE_RATE)


@pytest.fixture
def ready_job(tmp_path: Path) -> Iterator[tuple[TestClient, str, Path]]:
    app = create_app(audio_root=tmp_path, piano_renderer=MockPianoRenderer())
    audio_id = str(uuid.uuid4())
    directory = tmp_path / audio_id
    directory.mkdir()
    source = directory / "original.wav"
    sf.write(source, np.zeros((SAMPLE_RATE, 2)), SAMPLE_RATE)
    for name in ("vocals.wav", "instrumental.wav"):
        sf.write(directory / name, np.zeros((SAMPLE_RATE, 2)), SAMPLE_RATE)
    for name in ("pitch_analysis.json", "quantized_melody.json"):
        (directory / name).write_bytes(b"unchanged source sentinel")
    melody = harmony()
    write_harmony(directory, melody)
    app.state.audio_jobs.jobs[audio_id] = AudioJob(audio_id, source, status="completed", harmony_melody=melody)
    with TestClient(app) as client:
        yield client, audio_id, directory


def test_render_api_downloads_and_preservation(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    originals = {path.name: path.read_bytes() for path in directory.iterdir()}
    response = client.post(f"/api/audio/{audio_id}/render", json={"velocity": 55, "piano_gain": 0.6, "original_gain": 0.8})
    assert response.status_code == 200
    assert response.json()["sample_rate"] == 44100
    assert response.json()["channels"] == 2
    for filename, url in response.json()["files"].items():
        download = client.get(url)
        assert download.status_code == 200
        assert download.content == (directory / filename).read_bytes()
    assert all(note.velocity == 55 for note in pretty_midi.PrettyMIDI(str(directory / "harmony.mid")).instruments[0].notes)
    validate_wav(directory / "harmony_piano.wav")
    validate_wav(directory / "preview_mix.wav")
    for filename, content in originals.items():
        assert (directory / filename).read_bytes() == content


def test_missing_synthesis_preserves_midi(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    client.app.state.rendering_service.piano = FluidSynthPianoRenderer(soundfont=directory / "missing.sf2")
    response = client.post(f"/api/audio/{audio_id}/render")
    assert response.status_code == 503
    assert "HARMONYFINDER_SOUNDFONT" in response.json()["detail"]
    assert "MIDI remains available" in response.json()["detail"]
    assert client.get(f"/api/audio/{audio_id}/files/harmony.mid").status_code == 200
    assert client.get(f"/api/audio/{audio_id}/files/harmony_piano.wav").status_code == 409
    assert (directory / "harmony.mid").exists()
    assert not (directory / "harmony_piano.wav").exists()


def test_invalid_api_config_missing_harmony_and_unknown_files(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    for config in ({"velocity": 0}, {"velocity": 128}, {"velocity": 9.5}, {"piano_gain": -1}, {"original_gain": 3}):
        assert client.post(f"/api/audio/{audio_id}/render", json=config).status_code == 422
    assert not (directory / "harmony.mid").exists()
    assert client.post("/api/audio/not-a-uuid/render").status_code == 404
    assert client.get(f"/api/audio/{audio_id}/files/unlisted.wav").status_code == 404
    client.app.state.audio_jobs.jobs[audio_id].harmony_melody = None
    assert client.post(f"/api/audio/{audio_id}/render").status_code == 409


def test_failed_rerender_does_not_serve_stale_wavs(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    assert client.post(f"/api/audio/{audio_id}/render").status_code == 200
    client.app.state.rendering_service.piano = FluidSynthPianoRenderer(soundfont=directory / "missing.sf2")
    assert client.post(f"/api/audio/{audio_id}/render", json={"velocity": 10}).status_code == 503
    assert client.get(f"/api/audio/{audio_id}/files/harmony.mid").status_code == 200
    assert client.get(f"/api/audio/{audio_id}/files/preview_mix.wav").status_code == 409


def test_missing_fluidsynth_api_preserves_midi(
    ready_job: tuple[TestClient, str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, audio_id, directory = ready_job
    font = directory / "user.sf2"
    font.write_bytes(b"mock font")
    client.app.state.rendering_service.piano = FluidSynthPianoRenderer(font)
    monkeypatch.setattr("backend.app.audio.piano_renderer.shutil.which", lambda name: None)
    response = client.post(f"/api/audio/{audio_id}/render")
    assert response.status_code == 503
    assert "HARMONYFINDER_FLUIDSYNTH" in response.json()["detail"]
    assert client.get(f"/api/audio/{audio_id}/files/harmony.mid").status_code == 200


@pytest.mark.parametrize("rate,channels,level", [(22050, 2, 0.1), (44100, 1, 0.1), (44100, 2, 1.0)])
def test_invalid_wav_outputs_are_rejected(tmp_path: Path, rate: int, channels: int, level: float) -> None:
    output = tmp_path / "invalid.wav"
    sf.write(output, np.full((100, channels), level), rate, subtype="FLOAT")
    with pytest.raises(RenderError):
        validate_wav(output)


def test_mp3_decoder_fallback_preserves_alignment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original, piano, output = tmp_path / "original.mp3", tmp_path / "piano.wav", tmp_path / "mix.wav"
    original.write_bytes(b"MP3 test fixture")
    sf.write(piano, np.zeros((44100, 2)), 44100)
    real_soundfile = sf.SoundFile

    def soundfile(path: Path, *args: object, **kwargs: object):
        if Path(path) == original:
            raise sf.LibsndfileError(1, "MP3 decoder unavailable")
        return real_soundfile(path, *args, **kwargs)

    samples = np.zeros((44100, 2), dtype="<f4")
    samples[22050] = 0.5

    def decode(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args[args.index("-ac") + 1] == "2"
        assert args[args.index("-ar") + 1] == "44100"
        return subprocess.CompletedProcess(args, 0, samples.tobytes(), b"")

    monkeypatch.setattr("backend.app.audio.mixing.sf.SoundFile", soundfile)
    monkeypatch.setattr("backend.app.audio.mixing.shutil.which", lambda name: "ffmpeg")
    monkeypatch.setattr("backend.app.audio.mixing.subprocess.run", decode)
    mix_preview(original, piano, output)
    result = sf.read(output)[0]
    assert np.argmax(np.abs(result[:, 0])) == 22050
    assert result[22050, 0] == pytest.approx(0.4, abs=1 / 32768)


def test_synthesis_failure_keeps_midi(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job

    class FailingRenderer:
        def render(self, midi: Path, output: Path, duration_seconds: float, last_note_end: float | None) -> None:
            raise RenderError("mock inference-free synth failure")

    client.app.state.rendering_service.piano = FailingRenderer()
    assert client.post(f"/api/audio/{audio_id}/render").status_code == 500
    assert client.get(f"/api/audio/{audio_id}/files/harmony.mid").status_code == 200
    assert client.get(f"/api/audio/{audio_id}/files/harmony_piano.wav").status_code == 409


def test_rendering_blocks_duplicate_and_upstream_changes(ready_job: tuple[TestClient, str, Path]) -> None:
    client, audio_id, directory = ready_job
    client.app.state.audio_jobs.jobs[audio_id].render_processing = True
    assert client.post(f"/api/audio/{audio_id}/render").status_code == 409
    assert client.post(f"/api/audio/{audio_id}/quantize").status_code == 409
    assert client.post(f"/api/audio/{audio_id}/harmony", json={"interval": "octave"}).status_code == 409

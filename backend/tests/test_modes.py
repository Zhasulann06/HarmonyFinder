"""Real mode routing, bounded preparation and optional DSP API integration."""

import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.jobs import AudioJob
from backend.app.audio.rendering import RenderConfig
from backend.app.audio.vocal_pitch import VocalPitchDependencyError, VocalPitchError
from backend.tests.test_audio import MockSeparator, wait_for_status, wav_bytes
from backend.tests.test_dynamic_vocal import fixture
from backend.tests.test_rendering import MockPianoRenderer
from backend.tests.test_vocal_pitch import require_engine


@pytest.mark.parametrize("rate,channels", [(16000, 1), (44100, 2), (48000, 1)])
def test_vocals_only_preserves_samples_and_bypasses_demucs(tmp_path, rate, channels):
    stream = io.BytesIO()
    samples = np.repeat((0.2 * np.sin(2 * np.pi * 220 * np.arange(rate) / rate))[:, None], channels, axis=1)
    sf.write(stream, samples, rate, format="WAV", subtype="PCM_24")
    raw = stream.getvalue()
    app = create_app(audio_root=tmp_path, separator=MockSeparator(fail=True))
    with TestClient(app) as client:
        result = client.post("/api/audio/upload", files={"file": ("../voice.wav", raw)}, data={"input_mode": "vocals_only"})
        assert result.status_code == 201
        assert result.json()["input_mode"] == "vocals_only"
        audio_id = result.json()["audio_id"]
        assert result.json()["status"] == "queued"
        assert client.post(f"/api/audio/{audio_id}/separate").status_code == 202
        wait_for_status(client, audio_id, "completed")
        assert client.post(f"/api/audio/{audio_id}/separate").status_code == 409
        source, _ = sf.read(io.BytesIO(raw), always_2d=True)
        for stem in ("vocals", "instrumental"):
            response = client.get(f"/api/audio/{audio_id}/files/{stem}")
            audio, actual_rate = sf.read(io.BytesIO(response.content), always_2d=True)
            assert actual_rate == rate and audio.shape == source.shape
            np.testing.assert_array_equal(audio, source if stem == "vocals" else np.zeros_like(source))
        assert (tmp_path / audio_id / "original.wav").read_bytes() == raw
        assert client.post(f"/api/audio/{audio_id}/analyze-pitch").status_code == 200


@pytest.mark.parametrize("mode", [None, "full_song"])
def test_full_song_still_uses_separator(tmp_path, mode):
    app = create_app(audio_root=tmp_path, separator=MockSeparator(fail=True))
    with TestClient(app) as client:
        result = client.post("/api/audio/upload", files={"file": ("song.wav", wav_bytes())}, data={} if mode is None else {"input_mode": mode})
        assert result.json()["input_mode"] == "full_song"
        audio_id = result.json()["audio_id"]
        client.post(f"/api/audio/{audio_id}/separate")
        wait_for_status(client, audio_id, "failed")


def test_invalid_mode_and_preparation_failure(tmp_path):
    with TestClient(create_app(audio_root=tmp_path)) as client:
        assert client.post("/api/audio/upload", files={"file": ("a.wav", wav_bytes())}, data={"input_mode": "auto"}).status_code == 422
        assert not list(tmp_path.iterdir())
        response = client.post("/api/audio/upload", files={"file": ("a.wav", wav_bytes(rate=4000))}, data={"input_mode": "vocals_only"})
        audio_id = response.json()["audio_id"]
        client.post(f"/api/audio/{audio_id}/separate")
        assert "preparation failed" in wait_for_status(client, audio_id, "failed")["error"]
        assert not (tmp_path / audio_id / "vocals.wav").exists()


class MockVocal:
    def render(self, source, output, curve):
        audio, rate = sf.read(source, always_2d=True)
        assert curve.duration_seconds == len(audio) / rate
        sf.write(output, audio * 0.5, rate, subtype="FLOAT")


@pytest.fixture
def vocal_job(tmp_path):
    app = create_app(audio_root=tmp_path, piano_renderer=MockPianoRenderer())
    app.state.rendering_service.vocal = MockVocal()
    job = app.state.audio_jobs.new_upload(".wav")
    a, q, h = fixture()
    samples = 0.2 * np.sin(2 * np.pi * 220 * np.arange(round(a.duration_seconds * 44100)) / 44100)
    for name, values in (("original.wav", samples * 4), ("vocals.wav", samples), ("instrumental.wav", np.zeros_like(samples))):
        sf.write(job.source.parent / name, values, 44100, subtype="FLOAT")
    job.status = "completed"
    job.pitch_analysis, job.quantized_melody, job.harmony_melody = a, q, h
    for name, model in (("pitch_analysis.json", a), ("quantized_melody.json", q), ("harmony_melody.json", h)):
        (job.source.parent / name).write_text(model.model_dump_json(), encoding="utf-8")
    app.state.audio_jobs.jobs[job.audio_id] = job
    with TestClient(app) as client:
        yield client, job


def test_vocal_render_downloads_gains_and_mode_switch(vocal_job):
    client, job = vocal_job
    path = f"/api/audio/{job.audio_id}"
    before = {f.name: f.read_bytes() for f in job.source.parent.iterdir()}
    piano = client.post(path + "/render")
    assert piano.status_code == 200 and "harmony.mid" in piano.json()["files"]
    result = client.post(path + "/render", json={"output_mode": "vocal", "instrumental_gain": 0, "lead_vocal_gain": 0.7, "harmony_gain": 0.6})
    assert result.status_code == 200
    data = result.json()
    assert data["output_mode"] == "vocal" and "Experimental" in data["warning"]
    assert set(data["files"]) == {"harmony_vocals.wav", "preview_mix.wav"}
    for name, url in data["files"].items():
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == (job.source.parent / name).read_bytes()
    assert client.get(path + "/files/harmony.mid").status_code == 409
    assert client.get(path + "/files/harmony_piano.wav").status_code == 409
    mixed, rate = sf.read(job.source.parent / "preview_mix.wav", always_2d=True)
    lead, _ = sf.read(job.source.parent / "vocals.wav")
    # Original file is deliberately 4x louder: mixing it would fail this assertion.
    np.testing.assert_allclose(mixed[:, 0], lead * (0.7 + 0.5 * 0.6), atol=1/32768)
    assert len(mixed) == len(lead) and rate == 44100
    assert all((job.source.parent / name).read_bytes() == raw for name, raw in before.items())
    assert client.post(path + "/render").status_code == 200
    assert client.get(path + "/files/harmony_vocals.wav").status_code == 409


@pytest.mark.parametrize("missing", ["pitch_analysis", "quantized_melody", "harmony_melody", "status"])
def test_vocal_prerequisites(vocal_job, missing):
    client, job = vocal_job
    setattr(job, missing, "queued" if missing == "status" else None)
    assert client.post(f"/api/audio/{job.audio_id}/render", json={"output_mode": "vocal"}).status_code == 409


@pytest.mark.parametrize("config", [{"output_mode": "ai"}, {"output_mode": "vocal", "original_gain": 1}, {"output_mode": "vocal", "piano_gain": 1}])
def test_invalid_render_modes(vocal_job, config):
    client, job = vocal_job
    assert client.post(f"/api/audio/{job.audio_id}/render", json=config).status_code == 422


@pytest.mark.parametrize("failure,status", [(VocalPitchDependencyError("Install Rubber Band"), 503), (VocalPitchError("DSP failed"), 500)])
def test_vocal_dependency_failure_no_stale_downloads(vocal_job, failure, status):
    client, job = vocal_job
    path = f"/api/audio/{job.audio_id}"
    assert client.post(path + "/render", json={"output_mode": "vocal"}).status_code == 200
    class FailingVocal:
        def render(self, *args):
            raise failure
    client.app.state.rendering_service.vocal = FailingVocal()
    response = client.post(path + "/render", json={"output_mode": "vocal"})
    assert response.status_code == status and not job.render_processing
    assert client.get(path + "/files/harmony_vocals.wav").status_code == 409
    assert client.get(path + "/files/preview_mix.wav").status_code == 409


def test_vocal_rejects_incompatible_quantization_and_missing_stems(vocal_job):
    client, job = vocal_job
    path = f"/api/audio/{job.audio_id}/render"
    job.quantized_melody.mode = "chromatic"
    result = client.post(path, json={"output_mode": "vocal"})
    assert result.status_code == 422 and "scale-aware" in result.json()["detail"]
    job.quantized_melody.mode = "scale-aware"
    (job.source.parent / "instrumental.wav").unlink()
    assert client.post(path, json={"output_mode": "vocal"}).status_code == 422


@pytest.mark.parametrize("direction", ["above", "below"])
def test_native_vocal_render_through_api(vocal_job, direction):
    client, job = vocal_job
    require_engine()
    job.pitch_analysis, job.quantized_melody, job.harmony_melody = fixture(direction)
    client.app.state.rendering_service.vocal = DynamicVocalRenderer()
    result = client.post(f"/api/audio/{job.audio_id}/render", json={"output_mode": "vocal"})
    assert result.status_code == 200, result.text
    audio, rate = sf.read(job.source.parent / "harmony_vocals.wav", always_2d=True)
    assert audio.shape == (97020, 1) and rate == 44100
    assert np.isfinite(audio).all() and 0.01 < np.max(np.abs(audio)) <= 0.981
    assert not result.json()["mix_diagnostics"]["output"]["clipping_risk"]


def test_vocal_defaults_do_not_inherit_high_piano_gain():
    assert RenderConfig().harmony_gain == 8
    assert RenderConfig(output_mode="vocal").harmony_gain == 0.6
    assert RenderConfig(output_mode="vocal", harmony_gain=2).harmony_gain == 2

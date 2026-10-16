"""Stem gain, timing, safety, diagnostics, and API compatibility regression tests."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from backend.app.audio.mixing import SAMPLE_RATE, load_stereo, mix_preview
from backend.app.audio.render_errors import RenderError
from backend.app.audio.rendering import RenderConfig
from backend.app.audio.stem_mixer import mix_stems, mix_tracks
from backend.tests.test_rendering import ready_job  # noqa: F401 - shared rendering fixture


def tracks(tmp_path: Path) -> tuple[Path, Path, Path]:
    files = tuple(tmp_path / f"{name}.wav" for name in ("instrumental", "vocals", "piano"))
    for path, level in zip(files, (0.2, 0.1, 0.02)):
        sf.write(path, np.full((1000, 2), level), SAMPLE_RATE, subtype="FLOAT")
    return files


def test_independent_linear_gains_and_no_normalization(tmp_path: Path) -> None:
    paths = tracks(tmp_path)
    before = [p.read_bytes() for p in paths]
    output = tmp_path / "mix.wav"
    result = mix_stems(*paths, output, 0.85, 0.4, 8)
    assert sf.read(output)[0][100] == pytest.approx((0.37, 0.37), abs=1 / 32768)
    assert result.headroom_gain == 1
    assert result.gained_levels["instrumental"].rms == pytest.approx(0.17)
    assert result.gained_levels["lead_vocal"].rms == pytest.approx(0.04)
    assert result.gained_levels["harmony"].rms == pytest.approx(0.16)
    assert result.harmony_to_lead_rms_db == pytest.approx(20 * np.log10(4))
    mix_stems(*paths, output, 0.85, 0, 8)
    assert sf.read(output)[0][100] == pytest.approx((0.33, 0.33), abs=1 / 32768)
    assert before == [p.read_bytes() for p in paths]


def test_duration_mono_stereo_sample_rates_and_time_origin(tmp_path: Path) -> None:
    i, v, h = tracks(tmp_path)
    instrumental = np.zeros(22050); instrumental[11025] = 0.1
    sf.write(i, instrumental, 22050, subtype="FLOAT")
    vocal = np.zeros((48000, 2)); vocal[24000] = (-0.02, 0.02)
    sf.write(v, vocal, 48000, subtype="FLOAT")
    piano = np.zeros((int(1.25 * SAMPLE_RATE), 2)); piano[-100] = (0.1, 0.2)
    sf.write(h, piano, SAMPLE_RATE, subtype="FLOAT")
    result = mix_stems(i, v, h, tmp_path / "mix.wav", 1, 0, 1)
    samples = load_stereo(tmp_path / "mix.wav")
    assert len(samples) == len(piano)
    assert np.argmax(samples[:, 0]) in (22050, len(piano) - 100)
    assert samples[22050, 0] == pytest.approx(samples[22050, 1])
    assert samples[-100] == pytest.approx((0.1, 0.2), abs=1 / 32768)
    assert not np.any(samples[:21000])
    assert result.output.duration_seconds == pytest.approx(1.25, abs=1 / SAMPLE_RATE)
    assert result.output.sample_rate == SAMPLE_RATE and result.output.channels == 2
    # A resampled vocal impulse remains at the same 0.5-second timestamp.
    mix_stems(i, v, h, tmp_path / "v.wav", 0, 1, 0)
    assert np.argmax(np.abs(load_stereo(tmp_path / "v.wav")[:, 0])) == 22050


def test_longer_original_stems_and_negative_phase_are_preserved(tmp_path: Path) -> None:
    i, v, h = tracks(tmp_path)
    sf.write(i, np.full((2000, 2), 0.1), SAMPLE_RATE, subtype="FLOAT")
    sf.write(v, np.full((2000, 2), -0.1), SAMPLE_RATE, subtype="FLOAT")
    result = mix_stems(i, v, h, tmp_path / "mix.wav", 1, 1, 0)
    assert len(load_stereo(tmp_path / "mix.wav")) == 2000
    assert result.output.peak == 0


def test_silence_and_near_silence_never_auto_boost(tmp_path: Path) -> None:
    i, v, h = tracks(tmp_path)
    for path in (i, v, h):
        sf.write(path, np.zeros((100, 2)), SAMPLE_RATE)
    result = mix_stems(i, v, h, tmp_path / "mix.wav")
    assert result.output.rms == 0 and result.harmony_to_lead_rms_db is None
    assert result.headroom_gain == 1
    sf.write(h, np.full((100, 2), 1e-8), SAMPLE_RATE, subtype="FLOAT")
    result = mix_stems(i, v, h, tmp_path / "mix.wav")
    assert result.pre_protection.peak == pytest.approx(8e-8)
    assert result.harmony_to_lead_rms_db is None


def test_clipping_protection_is_downward_common_gain_only(tmp_path: Path) -> None:
    signal = np.array([[0.7, -0.7], [0.1, -0.1]])
    result = mix_tracks({"instrumental": signal, "lead_vocal": signal, "harmony": signal},
                        {"instrumental": 2, "lead_vocal": 2, "harmony": 12}, tmp_path / "mix.wav")
    assert result.pre_protection.clipping_risk
    assert result.headroom_gain == pytest.approx(0.98 / 11.2)
    assert result.output.peak <= 0.9801 and not result.output.clipping_risk
    samples = load_stereo(tmp_path / "mix.wav")
    assert samples[1, 0] / samples[0, 0] == pytest.approx(1 / 7, abs=0.001)


@pytest.mark.parametrize("field,value", [("instrumental_gain", -0.1), ("lead_vocal_gain", 2.01),
                                        ("harmony_gain", 12.01), ("harmony_gain", float("nan")),
                                        ("harmony_gain", float("inf"))])
def test_gain_validation(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        RenderConfig(**{field: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_track_rejected(tmp_path: Path, value: float) -> None:
    with pytest.raises(RenderError, match="finite"):
        mix_tracks({"harmony": np.full((10, 2), value)}, {"harmony": 1}, tmp_path / "bad.wav")


def test_new_and_legacy_config_semantics() -> None:
    assert RenderConfig().harmony_gain == 8 and not RenderConfig().legacy_mix
    assert RenderConfig(piano_gain=0.6).legacy_mix
    assert RenderConfig(original_gain=0).legacy_mix
    with pytest.raises(ValidationError, match="either legacy"):
        RenderConfig(piano_gain=0.6, harmony_gain=8)


def test_new_render_endpoint_uses_stems_and_returns_diagnostics(ready_job) -> None:
    client, audio_id, directory = ready_job
    sf.write(directory / "instrumental.wav", np.full((SAMPLE_RATE, 2), 0.1), SAMPLE_RATE, subtype="FLOAT")
    sf.write(directory / "vocals.wav", np.full((SAMPLE_RATE, 2), 0.2), SAMPLE_RATE, subtype="FLOAT")
    sf.write(directory / "original.wav", np.full((SAMPLE_RATE, 2), 0.8), SAMPLE_RATE, subtype="FLOAT")
    response = client.post(f"/api/audio/{audio_id}/render", json={"instrumental_gain": 0.5, "lead_vocal_gain": 0, "harmony_gain": 0})
    assert response.status_code == 200
    diagnostics = response.json()["mix_diagnostics"]
    assert diagnostics["mode"] == "stems" and diagnostics["gains"]["lead_vocal"] == 0
    assert load_stereo(directory / "preview_mix.wav")[22050] == pytest.approx((0.05, 0.05), abs=1 / 32768)
    assert client.get(response.json()["files"]["preview_mix.wav"]).status_code == 200


def test_legacy_request_preserves_original_mix(ready_job) -> None:
    client, audio_id, directory = ready_job
    sf.write(directory / "original.wav", np.full((SAMPLE_RATE, 2), 0.2), SAMPLE_RATE, subtype="FLOAT")
    response = client.post(f"/api/audio/{audio_id}/render", json={"original_gain": 0.8, "piano_gain": 0.6})
    assert response.status_code == 200
    assert response.json()["mix_diagnostics"]["mode"] == "original_legacy"
    expected = directory / "expected.wav"
    mix_preview(directory / "original.wav", directory / "harmony_piano.wav", expected, 0.8, 0.6)
    assert expected.read_bytes() == (directory / "preview_mix.wav").read_bytes()


def test_missing_stems_default_fallback_explicit_gains_error(ready_job) -> None:
    client, audio_id, directory = ready_job
    for name in ("vocals.wav", "instrumental.wav"):
        (directory / name).unlink()
    response = client.post(f"/api/audio/{audio_id}/render")
    assert response.status_code == 200
    assert response.json()["mix_diagnostics"]["mode"] == "original_fallback"
    assert response.json()["mix_diagnostics"]["warning"]
    assert client.post(f"/api/audio/{audio_id}/render", json={"harmony_gain": 8}).status_code == 422


def test_corrupt_stems_do_not_silently_fallback(ready_job) -> None:
    client, audio_id, directory = ready_job
    (directory / "vocals.wav").write_bytes(b"corrupt")
    assert client.post(f"/api/audio/{audio_id}/render").status_code == 500
    assert client.get(f"/api/audio/{audio_id}/files/harmony.mid").status_code == 200

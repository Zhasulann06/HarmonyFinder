"""Synthetic DSP checks plus mocked dependency failures; no model downloads."""

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from backend.app.audio import vocal_pitch as vp


def tone(path: Path, rate: int = 44100, channels: int = 1) -> np.ndarray:
    t = np.arange(2 * rate) / rate
    audio = np.zeros((len(t), channels), dtype=np.float32)
    window = np.zeros(len(t)); start, end = int(0.4 * rate), int(1.6 * rate)
    window[start:end] = 1
    ramp = int(0.02 * rate)
    window[start:start + ramp] = np.linspace(0, 1, ramp)
    window[end - ramp:end] = np.linspace(1, 0, ramp)
    audio[:] = (0.2 * np.sin(2 * np.pi * 440 * t) * window)[:, None]
    sf.write(path, audio, rate, subtype="FLOAT")
    return audio


def require_engine() -> vp.RubberBandVocalPitchShifter:
    shifter = vp.RubberBandVocalPitchShifter()
    try:
        shifter._dependency()
    except vp.VocalPitchDependencyError:
        if os.getenv("HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS") == "1":
            raise
        pytest.skip("Optional Rubber Band 3+ is not installed; set HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS=1 to require it")
    return shifter


@pytest.mark.parametrize("shift", [3, -3])
@pytest.mark.parametrize("rate,channels", [(16000, 1), (44100, 2), (48000, 1)])
def test_real_synthetic_pitch_direction_timing_and_channels(tmp_path: Path, shift: int, rate: int, channels: int) -> None:
    source, output = tmp_path / "vocal with spaces.wav", tmp_path / "shifted.wav"
    original = tone(source, rate, channels)
    before = source.read_bytes()
    report = require_engine().shift(source, output, shift)
    samples, actual_rate = sf.read(output, always_2d=True)
    assert actual_rate == rate and samples.shape == original.shape
    assert source.read_bytes() == before and report.frame_adjustment == 0
    assert np.all(np.isfinite(samples)) and report.output.clipped_samples == 0
    assert report.output.rms > 0.01
    # Analyze stable interior; no pYIN/model dependency is necessary for a pure tone.
    stable = samples[int(0.7 * rate):int(1.3 * rate), 0]
    spectrum = np.abs(np.fft.rfft(stable * np.hanning(len(stable))))
    detected = np.fft.rfftfreq(len(stable), 1 / rate)[int(np.argmax(spectrum))]
    assert detected == pytest.approx(440 * 2 ** (shift / 12), abs=3)
    assert np.max(np.abs(samples[:int(0.30 * rate)])) < 1e-5
    assert np.max(np.abs(samples[int(1.75 * rate):])) < 1e-5
    envelope = np.sqrt(np.mean(samples ** 2, axis=1))
    active = np.flatnonzero(envelope > 0.03)
    assert abs(active[0] / rate - 0.4) < 0.04
    assert abs(active[-1] / rate - 1.6) < 0.04
    if channels == 2:
        assert np.max(np.abs(samples[:, 0] - samples[:, 1])) < 1e-5


@pytest.mark.parametrize("channels", [1, 2])
def test_silence_does_not_need_dependency(tmp_path: Path, channels: int) -> None:
    source, output = tmp_path / "silent.wav", tmp_path / "out.wav"
    sf.write(source, np.zeros((8000, channels)), 8000)
    report = vp.RubberBandVocalPitchShifter(executable="missing").shift(source, output, 3)
    assert report.engine == "silence" and report.output.rms == 0
    assert report.output.frames == 8000 and report.output.channels == channels


def test_zero_shift_identity(tmp_path: Path) -> None:
    source, output = tmp_path / "in.wav", tmp_path / "out.wav"
    original = tone(source)
    report = vp.RubberBandVocalPitchShifter(executable="missing").shift(source, output, 0)
    assert report.engine == "identity"
    assert np.array_equal(sf.read(output, dtype="float32", always_2d=True)[0], original)


@pytest.mark.parametrize("shift", [13, -13, np.nan, np.inf, True, "3"])
def test_invalid_pitch_amount(tmp_path: Path, shift) -> None:
    with pytest.raises(ValueError, match="semitones"):
        vp.RubberBandVocalPitchShifter().shift(tmp_path / "missing.wav", tmp_path / "out.wav", shift)


@pytest.mark.parametrize("kind", ["missing", "corrupt", "nan", "inf", "channels", "overlong", "wrong_format", "empty"])
def test_invalid_input(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "bad.wav"
    if kind == "corrupt":
        source.write_bytes(b"broken")
    elif kind != "missing":
        values = np.zeros((100, 3 if kind == "channels" else 1))
        if kind in ("nan", "inf"):
            values[0] = float(kind)
        if kind == "overlong":
            values = np.zeros((31 * 8000, 1))
        if kind == "empty":
            values = np.zeros((0, 1))
        sf.write(source, values, 8000, format="FLAC" if kind == "wrong_format" else "WAV", subtype="PCM_16" if kind == "wrong_format" else "FLOAT")
    with pytest.raises(vp.InvalidVocalAudio):
        vp.RubberBandVocalPitchShifter().shift(source, tmp_path / "out.wav", 3)


def test_cannot_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "in.wav"; tone(source)
    with pytest.raises(ValueError, match="overwrite"):
        vp.RubberBandVocalPitchShifter().shift(source, source, 3)


def test_missing_dependency(tmp_path: Path) -> None:
    source = tmp_path / "in.wav"; tone(source)
    with pytest.raises(vp.VocalPitchDependencyError, match="HARMONYFINDER_RUBBERBAND"):
        vp.RubberBandVocalPitchShifter(executable=str(tmp_path / "missing.exe")).shift(source, tmp_path / "out.wav", 3)


@pytest.mark.parametrize("failure", ["old_version", "timeout", "corrupt", "short", "channels", "rate", "silence"])
def test_dependency_and_invalid_output_failures_preserve_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    source, output = tmp_path / "in.wav", tmp_path / "out.wav"
    tone(source); output.write_bytes(b"previous output")
    monkeypatch.setattr(vp.shutil, "which", lambda _: "rubberband.exe")
    def run(args, **kwargs):
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "2.0.0" if failure == "old_version" else "4.0.0", "")
        assert args.index("--formant") < len(args) - 2 and args[args.index("--time") + 1] == "1"
        assert kwargs["timeout"] == 120
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 120)
        if failure == "corrupt":
            Path(args[-1]).write_bytes(b"bad")
        else:
            audio, rate = sf.read(args[-2], always_2d=True)
            if failure == "short": audio = audio[:-100]
            if failure == "channels": audio = np.repeat(audio, 2, axis=1)
            if failure == "silence": audio *= 0
            sf.write(args[-1], audio, rate + 1 if failure == "rate" else rate, subtype="FLOAT")
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(vp.subprocess, "run", run)
    with pytest.raises(vp.VocalPitchError):
        vp.RubberBandVocalPitchShifter().shift(source, output, 3)
    assert output.read_bytes() == b"previous output"


def test_peak_protection_and_file_edge_fades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, output = tmp_path / "in.wav", tmp_path / "out.wav"
    sf.write(source, np.full((8000, 2), 0.5), 8000, subtype="FLOAT")
    monkeypatch.setattr(vp.shutil, "which", lambda _: "rubberband.exe")
    def run(args, **kwargs):
        if "--version" not in args:
            sf.write(args[-1], np.full((8000, 2), 2), 8000, subtype="FLOAT")
        return subprocess.CompletedProcess(args, 0, "4.0.0", "")
    monkeypatch.setattr(vp.subprocess, "run", run)
    report = vp.RubberBandVocalPitchShifter().shift(source, output, -3)
    samples = sf.read(output, always_2d=True)[0]
    assert np.max(np.abs(samples)) <= 0.980001
    assert samples[0, 0] == samples[-1, 0] == 0
    assert report.peak_protection_gain == pytest.approx(0.49)


def test_environment_relative_paths_are_root_anchored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARMONYFINDER_RUBBERBAND", "custom DSP/rubberband.exe")
    assert vp.RubberBandVocalPitchShifter().executable == str(vp.PROJECT_ROOT / "custom DSP/rubberband.exe")


def test_missing_input_does_not_replace_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "out.wav"; output.write_bytes(b"keep")
    with pytest.raises(vp.InvalidVocalAudio):
        vp.RubberBandVocalPitchShifter().shift(tmp_path / "missing.wav", output, 3)
    assert output.read_bytes() == b"keep"

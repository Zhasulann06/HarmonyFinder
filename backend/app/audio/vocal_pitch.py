"""Isolated offline waveform pitch shifting; no API or note-level processing."""

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from backend.app.audio.mixing import PEAK_LIMIT
from backend.app.core.config import PROJECT_ROOT, resolve_executable, resolve_project_path


LOCAL_RUBBERBAND = PROJECT_ROOT / "tools/rubberband-4.0.0/rubberband-4.0.0-gpl-executable-windows/rubberband.exe"


class InvalidVocalAudio(ValueError):
    """Input is not a bounded finite mono/stereo vocal WAV."""


class VocalPitchError(RuntimeError):
    """DSP failed or returned invalid audio."""


class VocalPitchDependencyError(VocalPitchError):
    """Optional Rubber Band executable cannot be used."""


@dataclass(frozen=True)
class VocalLevels:
    frames: int
    duration_seconds: float
    sample_rate: int
    channels: int
    peak: float
    rms: float
    clipped_samples: int


@dataclass(frozen=True)
class PitchShiftReport:
    semitones: float
    frequency_ratio: float
    engine: str
    input: VocalLevels
    output: VocalLevels
    processing_seconds: float
    peak_protection_gain: float
    frame_adjustment: int


class VocalPitchShifter(Protocol):
    def shift(self, source: Path, output: Path, semitones: float) -> PitchShiftReport:
        """Shift a complete waveform without changing its tempo."""


def vocal_levels(samples: np.ndarray, rate: int) -> VocalLevels:
    return VocalLevels(frames=len(samples), duration_seconds=len(samples) / rate,
                       sample_rate=rate, channels=samples.shape[1],
                       peak=float(np.max(np.abs(samples))),
                       rms=float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))),
                       clipped_samples=int(np.count_nonzero(np.abs(samples) >= 1)))


def read_vocal_wav(source: Path, *, max_seconds: float = 30.0) -> tuple[np.ndarray, int]:
    try:
        with sf.SoundFile(source) as audio:
            if (audio.format not in {"WAV", "WAVEX"} or not 8000 <= audio.samplerate <= 192000
                    or audio.channels not in (1, 2) or not 0 < audio.frames <= math.ceil(max_seconds * audio.samplerate)):
                raise InvalidVocalAudio("Use a mono/stereo WAV of at most 30 seconds at 8–192 kHz")
            rate = audio.samplerate
            samples = audio.read(dtype="float32", always_2d=True)
        if not np.all(np.isfinite(samples)):
            raise InvalidVocalAudio("Vocal audio contains NaN/Inf samples")
        return samples, rate
    except (sf.LibsndfileError, OSError) as exc:
        raise InvalidVocalAudio("Vocal WAV is missing, corrupt, or unreadable") from exc


def default_rubberband() -> str:
    override = os.getenv("HARMONYFINDER_RUBBERBAND")
    return resolve_executable(override) if override else str(LOCAL_RUBBERBAND) if LOCAL_RUBBERBAND.is_file() else "rubberband"


@dataclass
class RubberBandVocalPitchShifter:
    executable: str = field(default_factory=default_rubberband)
    timeout_seconds: float = 120.0

    def _dependency(self) -> tuple[str, str]:
        executable = shutil.which(resolve_executable(self.executable))
        hint = "Install Rubber Band 3+ (Windows 4.0.0 utility recommended) and set HARMONYFINDER_RUBBERBAND to rubberband.exe"
        if not executable:
            raise VocalPitchDependencyError(hint)
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=5, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise VocalPitchDependencyError(hint + "; check the executable and its DLLs") from exc
        match = re.search(r"(\d+)\.\d+\.\d+", result.stdout + result.stderr)
        if not match or int(match[1]) < 3:
            raise VocalPitchDependencyError("Rubber Band 3+ is required for the R3 engine")
        return executable, match[0]

    def shift(self, source: Path, output: Path, semitones: float) -> PitchShiftReport:
        if isinstance(semitones, bool) or not isinstance(semitones, (int, float)) or not math.isfinite(semitones) or not -12 <= semitones <= 12:
            raise ValueError("Pitch shift must be finite and in -12 to +12 semitones")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("DSP timeout must be positive and finite")
        source, output = resolve_project_path(source), resolve_project_path(output)
        if source == output or (source.exists() and output.exists() and os.path.samefile(source, output)):
            raise ValueError("Output must not overwrite the source vocal waveform")
        if output.suffix.lower() != ".wav":
            raise ValueError("Output must be a WAV file")
        samples, rate = read_vocal_wav(source)
        before = vocal_levels(samples, rate)
        started = time.perf_counter()
        output.parent.mkdir(parents=True, exist_ok=True)
        adjustment = 0
        engine = "identity" if semitones == 0 else "silence" if before.peak == 0 else ""
        with tempfile.TemporaryDirectory(prefix="vocal-shift-", dir=output.parent) as directory:
            stage = Path(directory)
            if engine:
                shifted = samples.copy()
            else:
                executable, version = self._dependency()
                engine = f"Rubber Band {version} R3, formant preserved"
                # FLOAT avoids intermediate PCM clipping/quantization; no resampling.
                input_file, raw = stage / "input.wav", stage / "shifted.wav"
                sf.write(input_file, samples, rate, subtype="FLOAT")
                args = [executable, "--fine", "--formant", "--time", "1", "--pitch", str(semitones),
                        "--ignore-clipping", "--quiet"]
                if before.channels == 2:
                    args.append("--centre-focus")
                args.extend([str(input_file), str(raw)])
                try:
                    subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   check=True, timeout=self.timeout_seconds)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise VocalPitchError("Rubber Band processing failed or timed out; check the installation and vocal input") from exc
                try:
                    shifted, out_rate = read_vocal_wav(raw, max_seconds=30 + 2 / rate)
                except InvalidVocalAudio as exc:
                    raise VocalPitchError("Rubber Band returned corrupt or nonfinite output") from exc
                if out_rate != rate or shifted.shape[1] != before.channels:
                    raise VocalPitchError("Rubber Band changed sample rate or channel count")
                adjustment = before.frames - len(shifted)
                # Only correct sample rounding, never hide truncation or stretch bugs.
                if abs(adjustment) > 2:
                    raise VocalPitchError("Rubber Band changed duration by more than two samples")
                shifted = shifted[:before.frames]
                if adjustment > 0:
                    shifted = np.pad(shifted, ((0, adjustment), (0, 0)))
                if before.rms > 1e-6 and vocal_levels(shifted, rate).rms <= 1e-7:
                    raise VocalPitchError("Rubber Band unexpectedly returned silence")
            # Leave phrase gaps to the DSP; soften only nonzero file boundaries.
            # No internal phrase cuts, silence gating, or fade at note boundaries.
            fade = min(round(0.005 * rate), len(shifted) // 2)
            if fade and engine not in {"identity", "silence"}:
                if np.any(samples[0]):
                    shifted[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
                if np.any(samples[-1]):
                    shifted[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
            peak = vocal_levels(shifted, rate).peak
            gain = min(1.0, PEAK_LIMIT / peak) if peak else 1.0
            shifted *= gain
            final = stage / "final.wav"
            sf.write(final, shifted, rate, subtype="FLOAT")
            valid, valid_rate = read_vocal_wav(final)
            after = vocal_levels(valid, valid_rate)
            if after.frames != before.frames or after.clipped_samples:
                raise VocalPitchError("Invalid pitch-shifted WAV output")
            final.replace(output)
        return PitchShiftReport(float(semitones), 2 ** (semitones / 12), engine, before, after,
                                time.perf_counter() - started, gain, adjustment)

"""Stereo conversion and synchronized, peak-safe preview mixing."""

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from backend.app.audio.render_errors import MissingRenderDependency, RenderError


SAMPLE_RATE = 44100
PEAK_LIMIT = 0.98


def load_stereo(path: Path, max_seconds: float = 32.0) -> np.ndarray:
    """Read bounded audio, preserving its time origin and leading silence."""
    try:
        with sf.SoundFile(path) as audio:
            if (not 0 < audio.samplerate <= 192000 or not 1 <= audio.channels <= 8
                    or audio.frames <= 0 or audio.frames / audio.samplerate > max_seconds
                    or audio.frames * audio.channels > 12_000_000):
                raise RenderError("Audio exceeds supported rendering limits")
            rate = audio.samplerate
            samples = audio.read(dtype="float32", always_2d=True)
    except (sf.LibsndfileError, OSError) as exc:
        if path.suffix.lower() != ".mp3":
            raise RenderError("Cannot decode rendering audio") from exc
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise MissingRenderDependency("Install FFmpeg and add ffmpeg.exe to PATH to decode the original MP3") from exc
        try:
            decoded = subprocess.run(
                [ffmpeg, "-v", "error", "-xerror", "-i", str(path), "-t", str(max_seconds + 1),
                 "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(SAMPLE_RATE), "-ac", "2", "-"],
                capture_output=True, timeout=60, check=True,
            )
            samples = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2).copy()
            rate = SAMPLE_RATE
            if not 0 < len(samples) <= math.ceil(max_seconds * rate):
                raise RenderError("Decoded original audio exceeds rendering limits")
        except (subprocess.SubprocessError, OSError, ValueError) as decode_exc:
            raise RenderError("FFmpeg could not decode the original MP3") from decode_exc
    if not np.all(np.isfinite(samples)):
        raise RenderError("Audio contains nonfinite samples")
    if samples.shape[1] != 2:
        samples = np.repeat(samples.mean(axis=1, keepdims=True), 2, axis=1)
    if rate != SAMPLE_RATE:
        divisor = math.gcd(rate, SAMPLE_RATE)
        samples = resample_poly(samples, SAMPLE_RATE // divisor, rate // divisor, axis=0)
    return samples


def write_safe_wav(output: Path, samples: np.ndarray) -> None:
    if samples.ndim != 2 or samples.shape[1] != 2 or len(samples) == 0 or not np.all(np.isfinite(samples)):
        raise RenderError("Invalid stereo render output")
    peak = float(np.max(np.abs(samples)))
    if peak > PEAK_LIMIT:
        samples = samples * (PEAK_LIMIT / peak)
    sf.write(output, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")


def validate_wav(path: Path, max_seconds: float = 32.0) -> float:
    try:
        with sf.SoundFile(path) as audio:
            if (audio.format != "WAV" or audio.samplerate != SAMPLE_RATE or audio.channels != 2
                    or not 0 < audio.frames <= math.ceil(max_seconds * SAMPLE_RATE)):
                raise RenderError("Expected a bounded 44100 Hz stereo WAV output")
            duration = audio.frames / SAMPLE_RATE
            samples = audio.read(dtype="float32", always_2d=True)
        if not np.all(np.isfinite(samples)) or np.max(np.abs(samples)) >= 1:
            raise RenderError("WAV output is clipped or invalid")
        return duration
    except (sf.LibsndfileError, OSError) as exc:
        raise RenderError("Missing or corrupt WAV output") from exc


def mix_preview(original: Path, piano: Path, output: Path, original_gain: float = 0.8, piano_gain: float = 0.6) -> float:
    if any(not math.isfinite(gain) or not 0 <= gain <= 2 for gain in (original_gain, piano_gain)):
        raise ValueError("Mix gains must be finite and in 0-2")
    backing = load_stereo(original, max_seconds=30.0)
    harmony = load_stereo(piano)
    mixed = np.zeros((max(len(backing), len(harmony)), 2), dtype=np.float32)
    mixed[:len(backing)] += backing * original_gain
    mixed[:len(harmony)] += harmony * piano_gain
    write_safe_wav(output, mixed)
    return validate_wav(output)

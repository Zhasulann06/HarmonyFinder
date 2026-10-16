"""Bounded content validation for supported audio formats."""

import json
import shutil
import subprocess
import wave
from pathlib import Path


class InvalidAudioError(ValueError):
    """The file is not valid audio of the claimed format."""


class DecoderUnavailableError(RuntimeError):
    """The required audio decoder is not installed."""


def validate_audio(path: Path, suffix: str, max_duration: float) -> float:
    """Validate content and return its duration in seconds."""
    if suffix == ".wav":
        return _validate_wav(path, max_duration)
    if suffix == ".mp3":
        return _validate_mp3(path, max_duration)
    raise InvalidAudioError("Only WAV and MP3 audio is supported")


def _validate_wav(path: Path, max_duration: float) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
            frames = audio.getnframes()
            if rate <= 0 or frames <= 0 or audio.getnchannels() <= 0:
                raise InvalidAudioError("WAV contains no playable audio")
            duration = frames / rate
            if duration > max_duration:
                raise InvalidAudioError("Audio exceeds 30 seconds")
            remaining = frames
            while remaining:
                chunk = audio.readframes(min(65536, remaining))
                if not chunk:
                    raise InvalidAudioError("WAV audio is truncated")
                remaining -= len(chunk) // (audio.getnchannels() * audio.getsampwidth())
            return duration
    except (wave.Error, EOFError, OSError, ZeroDivisionError) as exc:
        raise InvalidAudioError("Invalid or corrupt WAV audio") from exc


def _validate_mp3(path: Path, max_duration: float) -> float:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise DecoderUnavailableError("FFmpeg and ffprobe are required for MP3 uploads")
    try:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=format_name,duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=15, check=True,
        )
        metadata = json.loads(probe.stdout)["format"]
        if "mp3" not in metadata["format_name"].split(","):
            raise InvalidAudioError("File content is not MP3 audio")
        duration = float(metadata["duration"])
        if not 0 < duration <= max_duration:
            raise InvalidAudioError("Audio exceeds 30 seconds or is empty")
        subprocess.run(
            [ffmpeg, "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
            capture_output=True, timeout=45, check=True,
        )
        return duration
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError,
            KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidAudioError("Invalid or corrupt MP3 audio") from exc

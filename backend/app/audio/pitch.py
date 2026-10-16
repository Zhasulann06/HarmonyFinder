"""Bounded, monophonic pitch detection using librosa pYIN."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf

from backend.app.audio.pitch_models import PitchAnalysis, PitchFrame
from backend.app.audio.segmentation import segment_notes


class PitchDetectionError(RuntimeError):
    """Pitch analysis could not be completed."""


class InvalidPitchAudioError(PitchDetectionError):
    """The input is not a supported, bounded vocal WAV recording."""


class PitchDetector(Protocol):
    def detect(self, source: Path) -> PitchAnalysis:
        """Analyze uncorrected vocal pitch without changing the source audio."""


@dataclass(frozen=True)
class PyinPitchDetector:
    sample_rate: int = 16000
    hop_length: int = 160
    frame_length: int = 1024
    fmin_hz: float = 65.40639132514966  # C2
    fmax_hz: float = 1046.5022612023945  # C6
    max_duration_seconds: float = 30.0

    def detect(self, source: Path) -> PitchAnalysis:
        import librosa

        try:
            with sf.SoundFile(source) as audio:
                if (audio.format != "WAV" or not 0 < audio.frames
                        or not 1 <= audio.channels <= 2
                        or not 0 < audio.samplerate <= 192000
                        or audio.frames / audio.samplerate > self.max_duration_seconds):
                    raise InvalidPitchAudioError("Expected a nonempty WAV of at most 30 seconds")
                original_rate = audio.samplerate
                duration = audio.frames / original_rate
                samples = audio.read(dtype="float32", always_2d=True)
        except (OSError, RuntimeError, ValueError) as exc:
            raise InvalidPitchAudioError("Invalid or unsupported vocal WAV audio") from exc
        if not np.all(np.isfinite(samples)):
            raise InvalidPitchAudioError("Vocal WAV contains invalid sample values")
        try:
            mono = samples.mean(axis=1)
            signal = librosa.resample(mono, orig_sr=original_rate, target_sr=self.sample_rate)
            step = self.hop_length / self.sample_rate
            count = int(np.ceil(duration / step))
            if np.max(np.abs(signal)) < 1e-6:
                frequencies = np.full(count, np.nan)
                flags = np.zeros(count, dtype=bool)
                probabilities = np.zeros(count)
            else:
                frequencies, flags, probabilities = librosa.pyin(
                    signal, sr=self.sample_rate, fmin=self.fmin_hz, fmax=self.fmax_hz,
                    frame_length=self.frame_length, hop_length=self.hop_length,
                    resolution=0.1, fill_na=np.nan, center=True,
                )
                rms = librosa.feature.rms(
                    y=signal, frame_length=self.frame_length, hop_length=self.hop_length,
                    center=True, pad_mode="constant",
                )[0]
                # A -60 dBFS energy gate prevents silence from becoming a note.
                flags = flags & (rms >= 0.001) & np.isfinite(frequencies)
            frames: list[PitchFrame] = []
            for index in range(min(count, len(frequencies))):
                voiced = bool(flags[index])
                hz = float(frequencies[index]) if voiced else None
                probability = float(probabilities[index])
                frames.append(PitchFrame(
                    time_seconds=index * step, voiced=voiced, f0_hz=hz,
                    midi_pitch=69 + 12 * np.log2(hz / 440) if hz is not None else None,
                    voiced_probability=probability if np.isfinite(probability) else None,
                ))
            return PitchAnalysis(
                duration_seconds=duration, sample_rate=self.sample_rate,
                hop_length=self.hop_length, frame_length=self.frame_length,
                fmin_hz=self.fmin_hz, fmax_hz=self.fmax_hz, frames=frames,
                notes=segment_notes(frames, duration, step),
            )
        except Exception as exc:
            raise PitchDetectionError("pYIN pitch detection failed") from exc

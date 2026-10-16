"""Harmonic-chroma major/minor triad detector with explicit uncertainty."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

PITCHES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
HOP_SECONDS = 0.5
ANALYSIS_RATE = 11025


@dataclass(frozen=True)
class ChordFrame:
    start: float
    end: float
    label: str
    confidence: float
    margin: float
    fit: float
    rms: float
    alternatives: tuple[tuple[str, float], ...]

    @property
    def status(self) -> str:
        if self.label in {"no_chord", "ambiguous"}:
            return self.label
        return "low_confidence" if self.confidence < 0.5 else "chord"


def templates() -> tuple[list[str], np.ndarray]:
    labels, vectors = [], []
    for root in range(12):
        for quality, third in (("major", 4), ("minor", 3)):
            vector = np.zeros(12)
            vector[[root, (root + third) % 12, (root + 7) % 12]] = (1.0, 0.9, 0.75)
            vector /= np.linalg.norm(vector)
            labels.append(f"{PITCHES[root]}:{quality}")
            vectors.append(vector)
    return labels, np.stack(vectors)


LABELS, TEMPLATES = templates()


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    if not path.is_file():
        raise ValueError(f"Missing audio: {path}")
    data, rate = sf.read(path, always_2d=True, dtype="float32")
    if not len(data) or rate <= 0 or not np.all(np.isfinite(data)):
        raise ValueError("Audio must be finite and nonempty")
    if len(data) / rate > 31:
        raise ValueError("Limit this experiment to 31 seconds")
    mono = data.mean(axis=1)
    if rate != ANALYSIS_RATE:
        from math import gcd
        divisor = gcd(rate, ANALYSIS_RATE)
        mono = resample_poly(mono, ANALYSIS_RATE // divisor, rate // divisor)
    return np.asarray(mono, dtype=np.float32), ANALYSIS_RATE


def harmonic_chroma(audio: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    if audio.ndim != 1 or not len(audio) or not np.all(np.isfinite(audio)):
        raise ValueError("Expected finite mono audio")
    stft = np.abs(librosa.stft(audio, n_fft=4096, hop_length=512))
    harmonic, _ = librosa.decompose.hpss(stft, margin=(2.0, 4.0))
    chroma = librosa.feature.chroma_stft(S=harmonic, sr=rate, n_fft=4096,
                                         hop_length=512, tuning=0)
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=rate,
                                   hop_length=512)
    return chroma, times


def classify(chroma: np.ndarray, rms: float, peak_rms: float) -> ChordFrame:
    if chroma.shape != (12,) or not np.all(np.isfinite(chroma)):
        raise ValueError("Expected finite 12-bin chroma")
    if rms < max(0.0015, peak_rms * 0.035) or chroma.sum() < 1e-6:
        return ChordFrame(0, 0, "no_chord", 0, 0, 0, rms, ())
    normalized = np.maximum(chroma, 0)
    normalized /= max(np.linalg.norm(normalized), 1e-12)
    scores = TEMPLATES @ normalized
    order = np.argsort(scores)[::-1]
    best, second = int(order[0]), int(order[1])
    fit = float(scores[best])
    margin = float(scores[best] - scores[second])
    confidence = float(np.clip((fit - 0.52) / 0.38, 0, 1) *
                       np.clip(margin / 0.16, 0, 1))
    alternatives = tuple((LABELS[int(index)], float(scores[index])) for index in order[:3])
    label = LABELS[best] if fit >= 0.70 and margin >= 0.035 else "ambiguous"
    if label == "ambiguous":
        confidence = min(confidence, 0.49)
    return ChordFrame(0, 0, label, confidence, margin, fit, rms, alternatives)


def smooth(frames: list[ChordFrame]) -> list[ChordFrame]:
    """Suppress isolated weak chord blips; never overwrite no-chord/ambiguous."""
    result = frames.copy()
    for index in range(1, len(frames) - 1):
        left, current, right = frames[index - 1:index + 2]
        if (left.label == right.label and left.label not in {"ambiguous", "no_chord"}
                and current.label not in {"ambiguous", "no_chord"}
                and current.label != left.label and current.confidence < 0.55):
            result[index] = ChordFrame(current.start, current.end, left.label,
                                       min(current.confidence, left.confidence, right.confidence),
                                       current.margin, current.fit, current.rms,
                                       current.alternatives)
    return result


def detect(audio: np.ndarray, rate: int) -> tuple[list[ChordFrame], np.ndarray, np.ndarray]:
    if rate != ANALYSIS_RATE or audio.ndim != 1 or not len(audio):
        raise ValueError("Use mono audio at the experiment analysis rate")
    chroma, times = harmonic_chroma(audio, rate)
    duration = len(audio) / rate
    rms = np.array([float(np.sqrt(np.mean(audio[int(start * rate):min(len(audio), int((start + HOP_SECONDS) * rate))] ** 2)))
                    for start in np.arange(0, duration, HOP_SECONDS)])
    peak = float(rms.max(initial=0))
    frames = []
    for index, start in enumerate(np.arange(0, duration, HOP_SECONDS)):
        end = min(duration, start + HOP_SECONDS)
        selected = (times >= start) & (times < end)
        vector = np.median(chroma[:, selected], axis=1) if selected.any() else np.zeros(12)
        measured = classify(vector, float(rms[index]), peak)
        frames.append(ChordFrame(float(start), float(end), measured.label,
                                 measured.confidence, measured.margin, measured.fit,
                                 measured.rms, measured.alternatives))
    return smooth(frames), chroma, times


def timeline(frames: list[ChordFrame]) -> list[dict]:
    if not frames:
        return []
    segments = []
    for frame in frames:
        if segments and segments[-1]["label"] == frame.label and abs(segments[-1]["end"] - frame.start) < 1e-6:
            segments[-1]["end"] = frame.end
            segments[-1]["confidence"] = min(segments[-1]["confidence"], frame.confidence)
        else:
            segments.append({"start": frame.start, "end": frame.end,
                             "label": frame.label, "confidence": frame.confidence})
    return segments

"""Synthetic known-label tests; no model downloads or real-audio ground truth."""

import numpy as np
import pytest
import xml.etree.ElementTree as ET

from experiments.chord_recognition.detector import (
    ANALYSIS_RATE, ChordFrame, classify, detect, smooth, timeline,
)
from experiments.chord_recognition.rank_keys import compare, vocabulary
from experiments.chord_recognition.run_analysis import svg_chroma
from experiments.chord_recognition.flag_confidence import status


def triad(midi: tuple[int, int, int], seconds: float = 2.0,
          plucked: bool = False) -> np.ndarray:
    t = np.arange(round(seconds * ANALYSIS_RATE)) / ANALYSIS_RATE
    result = np.zeros_like(t)
    for pitch in midi:
        fundamental = 440 * 2 ** ((pitch - 69) / 12)
        for harmonic, amplitude in ((1, 1), (2, 0.22), (3, 0.10)):
            result += amplitude * np.sin(2 * np.pi * fundamental * harmonic * t)
    envelope = np.exp(-0.7 * t) if plucked else np.ones_like(t)
    return (result * envelope / 5).astype(np.float32)


@pytest.mark.parametrize("pitches,label", [
    ((60, 64, 67), "C:major"),
    ((64, 67, 72), "C:major"),  # inversion-independent
    ((57, 60, 64), "A:minor"),
    ((55, 59, 62), "G:major"),
])
def test_known_triads(pitches, label) -> None:
    frames, _, _ = detect(triad(pitches, plucked=True), ANALYSIS_RATE)
    assert frames[1].label == label
    assert frames[1].confidence > 0


def test_changes_and_silence() -> None:
    audio = np.concatenate((np.zeros(ANALYSIS_RATE, dtype=np.float32),
                            triad((60, 64, 67)), triad((57, 60, 64))))
    frames, _, _ = detect(audio, ANALYSIS_RATE)
    assert frames[0].label == "no_chord"
    assert frames[3].label == "C:major"
    assert frames[7].label == "A:minor"
    assert len(timeline(frames)) >= 3


def test_ambiguous_chroma_not_forced_into_chord() -> None:
    vector = np.zeros(12)
    vector[[0, 3, 4, 7]] = 1
    assert classify(vector, 0.2, 0.2).label == "ambiguous"


def test_weak_blip_smoothed_but_unknown_preserved() -> None:
    def frame(label: str, confidence: float) -> ChordFrame:
        return ChordFrame(0, 0.5, label, confidence, 0.1, 0.8, 0.2, ())
    result = smooth([frame("C:major", 0.8), frame("G:major", 0.2),
                     frame("C:major", 0.8), frame("ambiguous", 0.1),
                     frame("C:major", 0.8)])
    assert result[1].label == "C:major"
    assert result[3].label == "ambiguous"


def test_invalid_input() -> None:
    with pytest.raises(ValueError):
        detect(np.array([[0.1]], dtype=np.float32), ANALYSIS_RATE)


def test_relative_keys_share_triad_vocabulary() -> None:
    assert vocabulary(2, "major") == vocabulary(11, "natural_minor")
    frames = [{"start": 0, "end": 1, "label": "D:major"},
              {"start": 1, "end": 2, "label": "ambiguous"}]
    scores = compare(frames)
    assert scores[0]["compatible_seconds"] == 1
    assert scores[0]["key"] in {"D major", "B natural_minor"}


def test_chroma_svg_is_valid() -> None:
    svg = svg_chroma(np.ones((12, 3)), np.array([0, 0.5, 1]), [], 1.5)
    assert ET.fromstring(svg).tag.endswith("svg")


def test_explicit_low_confidence_status() -> None:
    frame = ChordFrame(0, 0.5, "D:major", 0.2, 0.04, 0.8, 0.1, ())
    assert frame.status == "low_confidence"
    assert status({"label": frame.label, "confidence": frame.confidence}) == "low_confidence"

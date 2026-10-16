"""Analyze one existing stem and emit a reviewable timeline plus SVG chroma."""

import argparse
from dataclasses import asdict
import hashlib
from html import escape
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from experiments.chord_recognition.detector import PITCHES, detect, load_audio, timeline


ROOT = Path(__file__).resolve().parent
SHARED_DIATONIC_TRIADS = {"D:major", "E:minor", "F#:minor", "G:major",
                          "A:major", "B:minor"}  # C# diminished not in this prototype.


def svg_chroma(chroma: np.ndarray, times: np.ndarray, frames: list, duration: float) -> str:
    width, height = 1100, 390
    left, top, plot_width, row_height = 62, 32, 1000, 22
    count = chroma.shape[1]
    # Normalize per column to show pitch-class structure rather than volume.
    normalized = chroma / np.maximum(np.max(chroma, axis=0, keepdims=True), 1e-9)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             'role="img" aria-label="Harmonic chroma and chord timeline">',
             '<rect width="100%" height="100%" fill="#161726"/>',
             '<text x="62" y="22" fill="white" font-size="15">Harmonic chroma · chord candidates</text>']
    cell_width = plot_width / max(count, 1)
    for pitch_class in range(12):
        y = top + (11 - pitch_class) * row_height
        parts.append(f'<text x="14" y="{y + 15}" fill="#ddd" font-size="12">{PITCHES[pitch_class]}</text>')
        for index in range(count):
            level = float(np.clip(normalized[pitch_class, index], 0, 1))
            lightness = 13 + round(60 * level)
            x = left + index * cell_width
            parts.append(f'<rect x="{x:.2f}" y="{y}" width="{cell_width + .1:.2f}" '
                         f'height="{row_height - 1}" fill="hsl(268 70% {lightness}%)"/>')
    marker_y = top + 12 * row_height + 8
    for frame in frames:
        x = left + plot_width * frame.start / duration
        w = plot_width * (frame.end - frame.start) / duration
        color = "#8163c7" if frame.label not in {"ambiguous", "no_chord"} else (
            "#ac8b50" if frame.label == "ambiguous" else "#555666")
        parts.append(f'<rect x="{x:.2f}" y="{marker_y}" width="{w:.2f}" height="15" '
                     f'fill="{color}" opacity="{0.35 + 0.65 * frame.confidence:.2f}"/>')
    last_label = None
    for frame in frames:
        if frame.label != last_label:
            x = left + plot_width * frame.start / duration
            label = escape(frame.label)
            parts.append(f'<text x="{x:.2f}" y="{marker_y + 32}" fill="#eee" font-size="10">{label}</text>')
        last_label = frame.label
    for second in range(0, int(duration) + 1, 2):
        x = left + plot_width * second / duration
        parts.append(f'<text x="{x:.2f}" y="{height - 10}" fill="#aaa" font-size="11">{second}s</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    input_path, output = args.input.resolve(), args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new output directory under experiments/chord_recognition/runs")
    info = sf.info(input_path)
    started = time.perf_counter()
    audio, rate = load_audio(input_path)
    frames, chroma, times = detect(audio, rate)
    elapsed = time.perf_counter() - started
    segments = timeline(frames)
    duration = len(audio) / rate
    chord_seconds = sum(frame.end - frame.start for frame in frames
                        if frame.label not in {"ambiguous", "no_chord"})
    fitting_seconds = sum(frame.end - frame.start for frame in frames
                          if frame.label in SHARED_DIATONIC_TRIADS)
    report = {"source": str(input_path),
              "source_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
              "source_audio": {"samplerate": info.samplerate, "channels": info.channels,
                               "duration_seconds": info.duration, "subtype": info.subtype},
              "analysis_rate": rate, "processing_seconds": elapsed,
              "method": "11.025-kHz mono; 4096-point STFT; HPSS harmonic component; chroma_stft; 0.5-s median; inversion-independent major/minor triad cosine templates; isolated weak-blip smoothing",
              "frames": [{**asdict(frame), "status": frame.status} for frame in frames],
              "timeline": segments,
              "summary": {"classified_chord_seconds": chord_seconds,
                          "ambiguous_seconds": sum(frame.end - frame.start for frame in frames if frame.label == "ambiguous"),
                          "no_chord_seconds": sum(frame.end - frame.start for frame in frames if frame.label == "no_chord"),
                          "shared_D_major_B_minor_triad_seconds": fitting_seconds,
                          "shared_fraction_among_classified": fitting_seconds / chord_seconds if chord_seconds else None,
                          "note": "D major/B natural minor share this diatonic triad set; result does not establish tonic or mode. C# diminished is unsupported."},
              "ground_truth": "unknown for real stems; predictions require human review"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "chord_timeline.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (output / "chroma.svg").write_text(svg_chroma(chroma, times, frames, duration), encoding="utf-8")
    print(json.dumps({"output": str(output), "processing_seconds": elapsed,
                      "summary": report["summary"], "timeline": segments}, indent=2))


if __name__ == "__main__":
    main()

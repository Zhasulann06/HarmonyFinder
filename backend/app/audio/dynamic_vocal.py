"""One continuous Rubber Band pitch-map invocation, never note-by-note stitching."""

import math
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from backend.app.audio.harmony_curve import HarmonyPitchCurve
from backend.app.audio.mixing import PEAK_LIMIT
from backend.app.audio.vocal_pitch import (RubberBandVocalPitchShifter, VocalPitchError,
    VocalPitchDependencyError, InvalidVocalAudio, VocalLevels, read_vocal_wav, vocal_levels)
from backend.app.core.config import resolve_project_path

QualityPreset = Literal["formant_stereo", "formant_independent", "formant_short", "no_formants"]
PRESETS = {
    "formant_stereo": ("--formant", "--centre-focus"),
    "formant_independent": ("--formant",),
    "formant_short": ("--formant", "--centre-focus", "--window-short"),
    "no_formants": ("--centre-focus",),
}


@dataclass(frozen=True)
class DynamicVocalReport:
    engine: str
    preset: str
    input: VocalLevels
    output: VocalLevels
    processing_seconds: float
    frame_adjustment: int
    peak_protection_gain: float
    shift_min: float
    shift_max: float
    map_points: int


class DynamicVocalRenderer(RubberBandVocalPitchShifter):
    def render(self, source: Path, output: Path, curve: HarmonyPitchCurve,
               *, preset: QualityPreset = "formant_stereo") -> DynamicVocalReport:
        curve.validate()
        if preset not in PRESETS:
            raise ValueError("Unsupported Rubber Band quality preset")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("DSP timeout must be positive and finite")
        source, output = resolve_project_path(source), resolve_project_path(output)
        if source == output or (source.exists() and output.exists() and source.samefile(output)):
            raise ValueError("Output must not overwrite source")
        if output.suffix.lower() != ".wav": raise ValueError("Output must be WAV")
        audio, rate = read_vocal_wav(source)
        before = vocal_levels(audio, rate)
        if not math.isclose(curve.duration_seconds, before.duration_seconds, abs_tol=1 / rate):
            raise ValueError("Curve duration differs from source waveform")
        started = time.perf_counter()
        output.parent.mkdir(parents=True, exist_ok=True)
        points = curve.points
        times = np.array([p.time_seconds for p in points])
        shifts = np.array([p.shift_semitones for p in points])
        gains = np.array([p.gain for p in points])
        with tempfile.TemporaryDirectory(prefix="dynamic-vocal-", dir=output.parent) as temporary:
            stage = Path(temporary)
            adjustment = 0; version = "silent"
            if before.peak == 0 or not np.any(gains):
                shifted = np.zeros_like(audio)
            else:
                executable, version = self._dependency()
                try:
                    help_text = subprocess.run([executable, "--full-help"], capture_output=True, text=True,
                                               encoding="utf-8", errors="replace", timeout=5, check=False)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise VocalPitchDependencyError("Cannot inspect Rubber Band pitch-map support") from exc
                if "--pitchmap" not in help_text.stdout + help_text.stderr:
                    raise VocalPitchDependencyError("This Rubber Band CLI has no --pitchmap support")
                # The CLI's --ignore-clipping actually clamps even FLOAT samples.
                # Fixed input headroom plus explicit rail checks prevent accepting that distortion.
                headroom = 0.125 / max(1.0, before.peak)
                sf.write(stage / "input.wav", audio * headroom, rate, subtype="FLOAT")
                mapping = {min(before.frames - 1, round(p.time_seconds * rate)): p.shift_semitones for p in points}
                (stage / "pitch.map").write_text("".join(f"{frame} {shift:.9f}\n" for frame, shift in sorted(mapping.items())), encoding="ascii")
                flags = [flag for flag in PRESETS[preset] if flag != "--centre-focus" or before.channels == 2]
                args = [executable, "--fine", *flags, "--time", "1", "--pitchmap", str(stage / "pitch.map"),
                        "--ignore-clipping", "--quiet", str(stage / "input.wav"), str(stage / "raw.wav")]
                try:
                    subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   check=True, timeout=self.timeout_seconds)
                    shifted, out_rate = read_vocal_wav(stage / "raw.wav", max_seconds=30.05)
                except (OSError, subprocess.SubprocessError, InvalidVocalAudio) as exc:
                    raise VocalPitchError("Continuous pitch-map DSP failed, timed out, or returned invalid WAV") from exc
                if out_rate != rate or shifted.shape[1] != before.channels:
                    raise VocalPitchError("Pitch-map processing changed rate/channels")
                if np.max(np.abs(shifted)) >= 0.999:
                    raise VocalPitchError("Native CLI output reached the clipping rails; refusing distorted output")
                adjustment = before.frames - len(shifted)
                # Do not turn a real-time truncation into an apparently successful render.
                if abs(adjustment) > 2:
                    raise VocalPitchError(f"Pitch-map duration mismatch: {adjustment} frames; native API integration needed")
                shifted = shifted[:before.frames] / headroom
                if adjustment > 0: shifted = np.pad(shifted, ((0, adjustment), (0, 0)))
                if before.rms > 1e-6 and vocal_levels(shifted, rate).rms <= 1e-7:
                    raise VocalPitchError("Unexpected silence from continuous pitch shifting")
            envelope = np.interp(np.arange(before.frames) / rate, times, gains).astype(np.float32)
            shifted *= envelope[:, None]
            fade = min(round(0.005 * rate), len(shifted) // 2)
            if fade:
                if np.any(audio[0]): shifted[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
                if np.any(audio[-1]): shifted[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
            peak = vocal_levels(shifted, rate).peak
            gain = min(1.0, PEAK_LIMIT / peak) if peak else 1.0
            shifted *= gain
            sf.write(stage / "final.wav", shifted, rate, subtype="FLOAT")
            valid, _ = read_vocal_wav(stage / "final.wav")
            after = vocal_levels(valid, rate)
            if after.frames != before.frames or after.clipped_samples: raise VocalPitchError("Invalid final vocal WAV")
            (stage / "final.wav").replace(output)
        return DynamicVocalReport(f"Rubber Band {version} R3 pitchmap", preset, before, after,
                                  time.perf_counter() - started, adjustment, gain,
                                  float(shifts.min()), float(shifts.max()), len(points))

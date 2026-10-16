"""Independent, time-aligned stem gains and transparent headroom protection."""

import math
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from pydantic import BaseModel

from backend.app.audio.mixing import PEAK_LIMIT, SAMPLE_RATE, load_stereo, validate_wav
from backend.app.audio.render_errors import RenderError


class SignalLevels(BaseModel):
    peak: float
    rms: float
    duration_seconds: float
    sample_rate: int = SAMPLE_RATE
    channels: int = 2
    clipping_risk: bool


class MixDiagnostics(BaseModel):
    mode: Literal["stems", "original_legacy", "original_fallback"]
    input_levels: dict[str, SignalLevels]
    gained_levels: dict[str, SignalLevels]
    pre_protection: SignalLevels
    output: SignalLevels
    headroom_gain: float
    gains: dict[str, float]
    harmony_to_lead_rms_db: float | None
    warning: str | None = None


def signal_levels(samples: np.ndarray) -> SignalLevels:
    if (samples.ndim != 2 or samples.shape[1] != 2 or not len(samples)
            or not np.all(np.isfinite(samples))):
        raise RenderError("Expected finite nonempty stereo samples")
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return SignalLevels(peak=peak, rms=rms, duration_seconds=len(samples) / SAMPLE_RATE,
                        clipping_risk=peak >= 1.0)


def mix_tracks(
    tracks: dict[str, np.ndarray], gains: dict[str, float], output: Path,
    mode: Literal["stems", "original_legacy", "original_fallback"] = "stems",
) -> MixDiagnostics:
    """No trimming, pitch changes, leveling, delay, or compression.

    Only a common downward gain protects headroom when the sum exceeds 0.98.
    The attenuation is reported and preserves relative track gain ratios.
    """
    if not tracks or tracks.keys() != gains.keys():
        raise ValueError("Each track requires an independent gain")
    for name, gain in gains.items():
        limit = 12 if name == "harmony" else 2
        if not math.isfinite(gain) or not 0 <= gain <= limit:
            raise ValueError(f"{name} gain must be finite and in 0-{limit}")
    input_levels = {name: signal_levels(track) for name, track in tracks.items()}
    frames = max(len(track) for track in tracks.values())
    mixed = np.zeros((frames, 2), dtype=np.float64)
    gained_levels: dict[str, SignalLevels] = {}
    # Report all contributions over the same padded output timeline.
    for name, track in tracks.items():
        contribution = np.zeros_like(mixed)
        contribution[:len(track)] = track.astype(np.float64) * gains[name]
        gained_levels[name] = signal_levels(contribution)
        mixed += contribution
    before = signal_levels(mixed)
    attenuation = min(1.0, PEAK_LIMIT / before.peak) if before.peak else 1.0
    sf.write(output, mixed * attenuation, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    validate_wav(output)
    rendered = signal_levels(load_stereo(output))
    lead = gained_levels.get("lead_vocal")
    harmony = gained_levels.get("harmony")
    ratio = (20 * math.log10(harmony.rms / lead.rms)
             if lead and harmony and lead.rms > 1e-6 and harmony.rms > 1e-6 else None)
    return MixDiagnostics(mode=mode, input_levels=input_levels, gained_levels=gained_levels,
                          pre_protection=before, output=rendered, headroom_gain=attenuation,
                          gains=gains, harmony_to_lead_rms_db=ratio)


def mix_stems(instrumental: Path, lead_vocal: Path, harmony: Path, output: Path,
              instrumental_gain: float = 0.85, lead_vocal_gain: float = 0.40,
              harmony_gain: float = 8.0) -> MixDiagnostics:
    return mix_tracks(
        {"instrumental": load_stereo(instrumental, 30), "lead_vocal": load_stereo(lead_vocal, 30),
         "harmony": load_stereo(harmony)},
        {"instrumental": instrumental_gain, "lead_vocal": lead_vocal_gain, "harmony": harmony_gain},
        output,
    )

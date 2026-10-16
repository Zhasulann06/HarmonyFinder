"""Render harmony MIDI first, then optional piano and synchronized preview."""

import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.audio.midi_renderer import MidiRenderer
from backend.app.audio.mixing import mix_preview, validate_wav
from backend.app.audio.piano_renderer import PianoRenderer
from backend.app.audio.render_errors import RenderInputError
from backend.app.audio.stem_mixer import MixDiagnostics, mix_stems, mix_tracks, signal_levels
from backend.app.audio.mixing import load_stereo
from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.harmony_curve import build_harmony_curve
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizedMelody
from backend.app.audio.harmony import HarmonyMelody
from backend.app.audio.vocal_pitch import VocalPitchError, VocalPitchDependencyError
from backend.app.audio.render_errors import MissingRenderDependency, RenderError


RENDER_FILES = ("harmony.mid", "harmony_piano.wav", "preview_mix.wav")
DOWNLOAD_FILES = (*RENDER_FILES, "harmony_vocals.wav")


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_mode: Literal["piano", "vocal"] = "piano"
    velocity: int = Field(default=90, strict=True, ge=1, le=127)
    piano_gain: float = Field(default=0.6, ge=0, le=2, allow_inf_nan=False)
    original_gain: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)
    instrumental_gain: float = Field(default=0.85, ge=0, le=2, allow_inf_nan=False)
    lead_vocal_gain: float = Field(default=0.40, ge=0, le=2, allow_inf_nan=False)
    harmony_gain: float = Field(default=8.0, ge=0, le=12, allow_inf_nan=False)

    @property
    def legacy_mix(self) -> bool:
        return bool(self.model_fields_set & {"original_gain", "piano_gain"})

    @model_validator(mode="after")
    def reject_ambiguous_gains(self) -> "RenderConfig":
        if self.output_mode == "vocal":
            if self.legacy_mix:
                raise ValueError("Vocal output requires the three stem gains, not legacy piano/original gains")
            if "harmony_gain" not in self.model_fields_set:
                self.harmony_gain = 0.6
        if self.legacy_mix and self.model_fields_set & {"instrumental_gain", "lead_vocal_gain", "harmony_gain"}:
            raise ValueError("Use either legacy original_gain/piano_gain or the three stem gains, not both")
        return self


class RenderResponse(BaseModel):
    audio_id: str
    status: Literal["completed"] = "completed"
    sample_rate: int = 44100
    channels: int = 2
    duration_seconds: float
    files: dict[str, str]
    mix_diagnostics: MixDiagnostics | None = None
    output_mode: Literal["piano", "vocal"] = "piano"
    warning: str | None = None


class RenderingService:
    def __init__(self, piano: PianoRenderer) -> None:
        self.piano = piano
        self.midi = MidiRenderer()
        self.vocal = DynamicVocalRenderer()

    def render_vocal(self, directory: Path, analysis: PitchAnalysis, quantized: QuantizedMelody,
                     harmony: HarmonyMelody, config: RenderConfig, available: set[str],
                     diagnostics: dict[str, MixDiagnostics]) -> float:
        if harmony.interval.startswith("diatonic_") and (
            quantized.mode != "scale-aware" or quantized.key != harmony.key or quantized.scale != harmony.scale
        ):
            raise RenderInputError("Diatonic vocal harmony requires scale-aware quantization in the same selected key and scale")
        if not all((directory / name).is_file() for name in ("vocals.wav", "instrumental.wav")):
            raise RenderInputError("Vocal rendering requires prepared vocals.wav and instrumental.wav")
        try:
            curve = build_harmony_curve(analysis, quantized, harmony)
            with tempfile.TemporaryDirectory(prefix="render-vocal-", dir=directory) as temporary:
                stage = Path(temporary)
                self.vocal.render(directory / "vocals.wav", stage / "harmony_vocals.wav", curve)
                (stage / "harmony_vocals.wav").replace(directory / "harmony_vocals.wav")
                available.add("harmony_vocals.wav")
                measured = mix_stems(directory / "instrumental.wav", directory / "vocals.wav",
                                     directory / "harmony_vocals.wav", stage / "preview_mix.wav",
                                     config.instrumental_gain, config.lead_vocal_gain, config.harmony_gain)
                (stage / "preview_mix.wav").replace(directory / "preview_mix.wav")
                available.add("preview_mix.wav")
                diagnostics["mix"] = measured
                return measured.output.duration_seconds
        except VocalPitchDependencyError as exc:
            raise MissingRenderDependency(str(exc)) from exc
        except ValueError as exc:
            raise RenderInputError(str(exc)) from exc
        except VocalPitchError as exc:
            raise RenderError(str(exc)) from exc

    def render(self, directory: Path, original: Path, config: RenderConfig, available: set[str],
               diagnostics: dict[str, MixDiagnostics] | None = None) -> float:
        with tempfile.TemporaryDirectory(prefix="render-", dir=directory) as temporary:
            stage = Path(temporary)
            melody = self.midi.render(directory / "harmony_melody.json", stage / "harmony.mid", config.velocity)
            # MIDI is committed independently, so missing optional dependencies
            # do not discard the usable MIDI file.
            (stage / "harmony.mid").replace(directory / "harmony.mid")
            available.add("harmony.mid")
            self.piano.render(
                directory / "harmony.mid", stage / "harmony_piano.wav", melody.duration_seconds,
                max((note.end_time for note in melody.notes), default=None),
            )
            validate_wav(stage / "harmony_piano.wav")
            (stage / "harmony_piano.wav").replace(directory / "harmony_piano.wav")
            available.add("harmony_piano.wav")
            piano = directory / "harmony_piano.wav"
            output = stage / "preview_mix.wav"
            instrumental, vocals = directory / "instrumental.wav", directory / "vocals.wav"
            if config.legacy_mix:
                # Preserve the old sum and gain interpretation exactly.
                duration = mix_preview(original, piano, output, config.original_gain, config.piano_gain)
                measured = mix_tracks({"original": load_stereo(original, 30), "harmony": load_stereo(piano)},
                                      {"original": config.original_gain, "harmony": config.piano_gain},
                                      stage / "diagnostic_mix.wav", mode="original_legacy")
                measured.output = signal_levels(load_stereo(output))
            elif instrumental.is_file() and vocals.is_file():
                measured = mix_stems(instrumental, vocals, piano, output,
                                     config.instrumental_gain, config.lead_vocal_gain, config.harmony_gain)
                duration = measured.output.duration_seconds
            elif config.model_fields_set & {"instrumental_gain", "lead_vocal_gain", "harmony_gain"} or instrumental.exists() or vocals.exists():
                raise RenderInputError("Independent stem mixing requires both vocals.wav and instrumental.wav; separate this audio again")
            else:
                # Historical jobs without stems still render with the old defaults.
                measured = mix_tracks({"original": load_stereo(original, 30), "harmony": load_stereo(piano)},
                                      {"original": config.original_gain, "harmony": config.piano_gain},
                                      output, mode="original_fallback")
                measured.warning = "Separated stems are unavailable; original-plus-piano fallback cannot independently control the lead vocal"
                duration = measured.output.duration_seconds
            if diagnostics is not None:
                diagnostics["mix"] = measured
            (stage / "preview_mix.wav").replace(directory / "preview_mix.wav")
            available.add("preview_mix.wav")
            return duration

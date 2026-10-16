"""Optional FluidSynth CLI piano rendering using a configured SoundFont."""

import math
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
import pretty_midi
import soundfile as sf

from backend.app.audio.mixing import SAMPLE_RATE, write_safe_wav, validate_wav
from backend.app.audio.render_errors import MissingRenderDependency, RenderError
from backend.app.core.config import (
    default_fluidsynth_executable, default_soundfont_path,
    resolve_executable, resolve_project_path,
)


RELEASE_SECONDS = 0.75
logger = logging.getLogger(__name__)


class PianoRenderer(Protocol):
    def render(self, midi: Path, output: Path, duration_seconds: float, last_note_end: float | None) -> None:
        """Render stereo piano at 44100 Hz, aligned with the MIDI time origin."""


@dataclass
class FluidSynthPianoRenderer:
    soundfont: Path | None = field(default_factory=lambda: Path(default_soundfont_path()))
    executable: str = field(default_factory=default_fluidsynth_executable)

    def __post_init__(self) -> None:
        if self.soundfont is not None:
            self.soundfont = resolve_project_path(self.soundfont)
        self.executable = resolve_executable(self.executable)

    def render(self, midi: Path, output: Path, duration_seconds: float, last_note_end: float | None) -> None:
        midi = resolve_project_path(midi)
        output = resolve_project_path(output)
        if not math.isfinite(duration_seconds) or not 0 <= duration_seconds <= 30:
            raise RenderError("Invalid piano render duration")
        if last_note_end is not None and (not math.isfinite(last_note_end) or not 0 < last_note_end <= duration_seconds):
            raise RenderError("Invalid last-note time")
        target_duration = max(1 / SAMPLE_RATE, duration_seconds,
                              last_note_end + RELEASE_SECONDS if last_note_end is not None else 0)
        target_frames = math.ceil(target_duration * SAMPLE_RATE)
        if last_note_end is None:
            # An empty harmony is silence, not a substitute instrument.
            write_safe_wav(output, np.zeros((target_frames, 2), dtype=np.float32))
            return
        if not self.soundfont or not self.soundfont.is_file() or self.soundfont.suffix.lower() != ".sf2":
            raise MissingRenderDependency("Set HARMONYFINDER_SOUNDFONT to an existing piano .sf2 file, then restart the API")
        executable = shutil.which(self.executable)
        if not executable:
            raise MissingRenderDependency("Install FluidSynth and set HARMONYFINDER_FLUIDSYNTH to fluidsynth.exe, or add it to PATH; restart the API")
        with tempfile.TemporaryDirectory(prefix="piano-", dir=output.parent) as temporary:
            directory = Path(temporary)
            playback = directory / "playback.mid"
            raw = directory / "raw.wav"
            try:
                data = pretty_midi.PrettyMIDI(str(midi))
                data.text_events.append(pretty_midi.Text("Release tail", target_duration))
                data.write(str(playback))
                completed = subprocess.run(
                    [executable, "-ni", "-q", "-F", str(raw), "-T", "wav", "-O", "float",
                     "-r", str(SAMPLE_RATE), "-g", "0.2", "-R", "0", "-C", "0",
                     "-o", "player.timing-source=sample", str(self.soundfont.resolve()), str(playback)],
                    capture_output=True, text=True, timeout=120, check=True,
                )
                diagnostics = (completed.stdout + completed.stderr).lower()
                if "failed to load soundfont" in diagnostics or "no preset found" in diagnostics:
                    logger.error("FluidSynth SoundFont error: %s", completed.stderr[-2000:])
                    raise RenderError("SoundFont could not provide the MIDI bank 0/program 0 piano preset")
                with sf.SoundFile(raw) as audio:
                    if (audio.format != "WAV" or audio.samplerate != SAMPLE_RATE or audio.channels != 2
                            or not math.floor(last_note_end * SAMPLE_RATE) <= audio.frames <= 45 * SAMPLE_RATE):
                        raise RenderError("FluidSynth produced an invalid or truncated WAV")
                    samples = audio.read(dtype="float32", always_2d=True)
                if not np.all(np.isfinite(samples)):
                    raise RenderError("FluidSynth produced nonfinite audio")
                samples = samples[:target_frames]
                if len(samples) < target_frames:
                    samples = np.pad(samples, ((0, target_frames - len(samples)), (0, 0)))
                # Keep leading silence; fade only the final 20 ms of the release.
                fade = min(len(samples), round(0.02 * SAMPLE_RATE))
                samples[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
                write_safe_wav(output, samples)
                validate_wav(output)
            except (subprocess.SubprocessError, OSError, ValueError, sf.LibsndfileError) as exc:
                if isinstance(exc, subprocess.SubprocessError):
                    logger.error("FluidSynth process error: %s", str(getattr(exc, "stderr", ""))[-2000:])
                raise RenderError("FluidSynth rendering failed; check its installation, DLLs, and the SoundFont piano preset") from exc

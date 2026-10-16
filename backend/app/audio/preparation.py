"""Prepare a validated vocal-only recording without separation or resampling."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def prepare_vocals(source: Path, directory: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="prepare-", dir=directory) as temporary:
        stage = Path(temporary)
        decoded = source
        try:
            sf.info(source)
        except (sf.LibsndfileError, OSError):
            executable = shutil.which("ffmpeg")
            if not executable:
                raise ValueError("Install FFmpeg to decode this recording")
            decoded = stage / "decoded.wav"
            subprocess.run([executable, "-v", "error", "-xerror", "-i", str(source),
                            "-t", "30.01", "-c:a", "pcm_f32le", str(decoded)],
                           capture_output=True, timeout=45, check=True)
        with sf.SoundFile(decoded) as stream:
            if (not 8000 <= stream.samplerate <= 192000 or stream.channels not in (1, 2)
                    or not 0 < stream.frames <= 30 * stream.samplerate):
                raise ValueError("Vocal input must be mono/stereo, 8–192 kHz and at most 30 seconds")
            rate = stream.samplerate
            samples = stream.read(dtype="float32", always_2d=True)
        if not np.all(np.isfinite(samples)):
            raise ValueError("Vocal input contains non-finite samples")
        sf.write(stage / "vocals.wav", samples, rate, subtype="FLOAT")
        sf.write(stage / "instrumental.wav", np.zeros_like(samples), rate, subtype="FLOAT")
        for name in ("vocals.wav", "instrumental.wav"):
            (stage / name).replace(directory / name)

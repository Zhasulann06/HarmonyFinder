"""Vocal separation interface and optional Demucs implementation."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol


class SeparationError(RuntimeError):
    """Separation could not produce both stems."""


class AudioSeparator(Protocol):
    """A separator writes synchronized WAV stems to an output directory."""

    def separate(self, source: Path, output_dir: Path) -> None:
        """Write vocals.wav and instrumental.wav into output_dir."""


class DemucsSeparator:
    """Run Demucs' htdemucs two-stem vocals model on CPU."""

    def separate(self, source: Path, output_dir: Path) -> None:
        try:
            import demucs  # noqa: F401 - detect optional installation before launching
        except ImportError as exc:
            raise SeparationError(
                "Demucs is not installed; install backend/requirements-demucs.txt"
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir = output_dir / "demucs_work"
        try:
            subprocess.run(
                [sys.executable, "-m", "demucs", "--two-stems", "vocals",
                 "-n", "htdemucs", "-d", "cpu", "--out", str(work_dir), str(source)],
                capture_output=True, text=True, timeout=1800, check=True,
            )
            stems = work_dir / "htdemucs" / source.stem
            shutil.copyfile(stems / "vocals.wav", output_dir / "vocals.wav")
            shutil.copyfile(stems / "no_vocals.wav", output_dir / "instrumental.wav")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise SeparationError("Demucs vocal separation failed") from exc
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

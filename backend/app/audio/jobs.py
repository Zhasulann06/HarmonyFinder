"""Local upload storage and in-process separation jobs."""

import asyncio
import logging
import shutil
import uuid
import soundfile as sf
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from backend.app.audio.separator import AudioSeparator
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizedMelody
from backend.app.audio.harmony import HarmonyMelody
from backend.app.audio.preparation import prepare_vocals


JobStatus = Literal["queued", "processing", "completed", "failed"]
InputMode = Literal["full_song", "vocals_only"]
logger = logging.getLogger(__name__)


@dataclass
class AudioJob:
    audio_id: str
    source: Path
    status: JobStatus = "queued"
    error: str | None = None
    pitch_analysis: PitchAnalysis | None = None
    pitch_processing: bool = False
    quantized_melody: QuantizedMelody | None = None
    harmony_melody: HarmonyMelody | None = None
    render_processing: bool = False
    rendered_files: set[str] = field(default_factory=set)
    input_mode: InputMode = "full_song"


class AudioJobs:
    """Process-local job registry; jobs do not survive a server restart."""

    def __init__(self, root: Path, separator: AudioSeparator) -> None:
        self.root = root
        self.separator = separator
        self.jobs: dict[str, AudioJob] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def new_upload(self, suffix: str) -> AudioJob:
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            audio_id = str(uuid.uuid4())
            directory = self.root / audio_id
            try:
                directory.mkdir()
                return AudioJob(audio_id, directory / f"original{suffix}")
            except FileExistsError:
                continue

    def get(self, audio_id: str) -> AudioJob | None:
        try:
            if str(uuid.UUID(audio_id)) != audio_id:
                return None
        except ValueError:
            return None
        return self.jobs.get(audio_id)

    def start(self, job: AudioJob) -> None:
        task = asyncio.create_task(self._run(job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, job: AudioJob) -> None:
        job.status = "processing"
        directory = job.source.parent
        try:
            processor = prepare_vocals if job.input_mode == "vocals_only" else self.separator.separate
            await asyncio.to_thread(processor, job.source, directory)
            await asyncio.to_thread(self._check_stems, directory)
        except Exception:
            logger.exception("Separation failed for audio ID %s", job.audio_id)
            job.error = ("Vocal preparation failed; verify mono/stereo audio at 8–192 kHz and FFmpeg availability; check server logs"
                         if job.input_mode == "vocals_only" else "Vocal separation failed; check server logs")
            job.status = "failed"
            for name in ("vocals.wav", "instrumental.wav"):
                (directory / name).unlink(missing_ok=True)
        else:
            job.status = "completed"

    @staticmethod
    def _check_stems(directory: Path) -> None:
        details: list[tuple[int, int, int]] = []
        for name in ("vocals.wav", "instrumental.wav"):
            with sf.SoundFile(directory / name) as audio:
                if audio.frames <= 0:
                    raise ValueError("Empty output stem")
                details.append((audio.samplerate, audio.frames, audio.channels))
        if details[0] != details[1]:
            raise ValueError("Output stems are not synchronized")

    def discard_upload(self, job: AudioJob) -> None:
        shutil.rmtree(job.source.parent)

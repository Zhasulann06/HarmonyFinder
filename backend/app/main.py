"""FastAPI application entry point."""

import asyncio
from pathlib import Path

from fastapi import FastAPI

from backend.app.api.routes.audio import router as audio_router
from backend.app.api.routes.health import router as health_router
from backend.app.audio.jobs import AudioJobs
from backend.app.audio.separator import AudioSeparator, DemucsSeparator
from backend.app.audio.pitch import PitchDetector, PyinPitchDetector
from backend.app.audio.piano_renderer import PianoRenderer, FluidSynthPianoRenderer
from backend.app.audio.rendering import RenderingService
from backend.app.core.config import settings


def create_app(
    *, separator: AudioSeparator | None = None, audio_root: Path | None = None,
    pitch_detector: PitchDetector | None = None,
    piano_renderer: PianoRenderer | None = None,
) -> FastAPI:
    """Create and configure the HarmonyFinder API."""
    application = FastAPI(title=settings.service_name)
    application.state.audio_jobs = AudioJobs(
        audio_root or settings.audio_root, separator or DemucsSeparator()
    )
    application.state.pitch_detector = pitch_detector or PyinPitchDetector()
    application.state.pitch_semaphore = asyncio.Semaphore(1)
    application.state.rendering_service = RenderingService(piano_renderer or FluidSynthPianoRenderer(
        soundfont=Path(settings.soundfont_path) if settings.soundfont_path else None,
        executable=settings.fluidsynth_executable,
    ))
    application.state.render_semaphore = asyncio.Semaphore(1)
    application.include_router(health_router, prefix=settings.api_prefix)
    application.include_router(audio_router, prefix=settings.api_prefix)
    return application


app = create_app()


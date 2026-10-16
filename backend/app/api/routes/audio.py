"""Upload, separate, inspect, and download audio."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.audio.jobs import AudioJob, AudioJobs, JobStatus, InputMode
from backend.app.audio.pitch import InvalidPitchAudioError
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizationConfig, QuantizedMelody, quantize_melody
from backend.app.audio.harmony import HarmonyConfig, HarmonyMelody, generate_harmony
from backend.app.audio.rendering import DOWNLOAD_FILES, RenderConfig, RenderResponse
from backend.app.audio.render_errors import MissingRenderDependency, RenderError, RenderInputError
from backend.app.audio.validation import (
    DecoderUnavailableError, InvalidAudioError, validate_audio,
)
from backend.app.core.config import settings


router = APIRouter(prefix="/audio", tags=["audio"])
logger = logging.getLogger(__name__)


class UploadResponse(BaseModel):
    audio_id: str
    status: JobStatus
    duration_seconds: float
    input_mode: InputMode = "full_song"


class StatusResponse(BaseModel):
    audio_id: str
    status: JobStatus
    error: str | None = None


def _jobs(request: Request) -> AudioJobs:
    return request.app.state.audio_jobs


def _job(request: Request, audio_id: str) -> AudioJob:
    job = _jobs(request).get(audio_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    return job


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_audio(request: Request, file: UploadFile = File(...),
                       input_mode: InputMode = Form("full_song")) -> UploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3"}:
        raise HTTPException(status_code=415, detail="Only WAV and MP3 audio is supported")
    jobs = _jobs(request)
    job = jobs.new_upload(suffix)
    job.input_mode = input_mode
    try:
        size = 0
        with job.source.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Audio exceeds 20 MB")
                output.write(chunk)
        duration = await asyncio.to_thread(
            validate_audio, job.source, suffix, settings.max_duration_seconds
        )
    except (InvalidAudioError, DecoderUnavailableError, HTTPException) as exc:
        jobs.discard_upload(job)
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, DecoderUnavailableError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()
    jobs.jobs[job.audio_id] = job
    return UploadResponse(audio_id=job.audio_id, status=job.status, duration_seconds=duration, input_mode=input_mode)


@router.post("/{audio_id}/separate", response_model=StatusResponse, status_code=202)
async def separate_audio(request: Request, audio_id: str) -> StatusResponse:
    job = _job(request, audio_id)
    if job.status != "queued":
        raise HTTPException(status_code=409, detail="Separation already requested")
    job.status = "processing"
    _jobs(request).start(job)
    return StatusResponse(audio_id=audio_id, status=job.status)


@router.get("/{audio_id}/status", response_model=StatusResponse)
def audio_status(request: Request, audio_id: str) -> StatusResponse:
    job = _job(request, audio_id)
    return StatusResponse(audio_id=audio_id, status=job.status, error=job.error)


@router.get("/{audio_id}/files/{stem}")
def download_stem(request: Request, audio_id: str, stem: str) -> FileResponse:
    if stem not in {"vocals", "instrumental", *DOWNLOAD_FILES}:
        raise HTTPException(status_code=404, detail="Stem not found")
    job = _job(request, audio_id)
    if stem in DOWNLOAD_FILES:
        if stem not in job.rendered_files:
            raise HTTPException(status_code=409, detail="Rendered file is not available; call the render endpoint")
        path = job.source.parent / stem
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Rendered file not found")
        return FileResponse(path, media_type="audio/midi" if stem.endswith(".mid") else "audio/wav", filename=stem)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Separation is not completed")
    return FileResponse(
        job.source.parent / f"{stem}.wav", media_type="audio/wav",
        filename=f"{stem}.wav",
    )


def _analyze_and_export(request: Request, job: AudioJob) -> PitchAnalysis:
    directory = job.source.parent
    result = request.app.state.pitch_detector.detect(directory / "vocals.wav")
    temporary = directory / "pitch_analysis.json.tmp"
    try:
        temporary.write_text(
            json.dumps(result.model_dump(), allow_nan=False, indent=2), encoding="utf-8"
        )
        temporary.replace(directory / "pitch_analysis.json")
    finally:
        temporary.unlink(missing_ok=True)
    return result


@router.post("/{audio_id}/analyze-pitch", response_model=PitchAnalysis)
async def analyze_pitch(request: Request, audio_id: str) -> PitchAnalysis:
    job = _job(request, audio_id)
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Separation is not completed")
    if job.pitch_processing:
        raise HTTPException(status_code=409, detail="Pitch analysis is already processing")
    if job.pitch_analysis is not None:
        return job.pitch_analysis
    job.pitch_processing = True
    try:
        # Only one CPU analysis runs at a time in this process.
        async with request.app.state.pitch_semaphore:
            result = await asyncio.to_thread(_analyze_and_export, request, job)
        job.pitch_analysis = result
        return result
    except InvalidPitchAudioError as exc:
        raise HTTPException(status_code=422, detail="Invalid or unsupported vocal WAV audio") from exc
    except Exception as exc:
        logger.exception("Pitch analysis failed for audio ID %s", audio_id)
        raise HTTPException(status_code=500, detail="Pitch analysis failed; check server logs") from exc
    finally:
        job.pitch_processing = False


@router.get("/{audio_id}/pitch", response_model=PitchAnalysis)
def get_pitch(request: Request, audio_id: str) -> PitchAnalysis:
    job = _job(request, audio_id)
    if job.pitch_analysis is None:
        detail = "Pitch analysis is processing" if job.pitch_processing else "Pitch analysis is not available"
        raise HTTPException(status_code=409, detail=detail)
    return job.pitch_analysis


@router.post("/{audio_id}/quantize", response_model=QuantizedMelody)
async def quantize_pitch(
    request: Request, audio_id: str,
    config: QuantizationConfig = Body(default=QuantizationConfig()),
) -> QuantizedMelody:
    job = _job(request, audio_id)
    if job.render_processing:
        raise HTTPException(status_code=409, detail="Rendering is processing")
    if job.pitch_analysis is None:
        raise HTTPException(status_code=409, detail="Pitch analysis is not available")
    directory = job.source.parent
    temporary = directory / "quantized_melody.json.tmp"
    try:
        result = quantize_melody(job.pitch_analysis, config)
        temporary.write_text(
            json.dumps(result.model_dump(), allow_nan=False, indent=2), encoding="utf-8"
        )
        temporary.replace(directory / "quantized_melody.json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Quantized melody export failed for audio ID %s", audio_id)
        raise HTTPException(status_code=500, detail="Quantization export failed; check server logs") from exc
    finally:
        temporary.unlink(missing_ok=True)
    job.quantized_melody = result
    job.harmony_melody = None
    job.rendered_files.clear()
    return result


@router.get("/{audio_id}/quantized", response_model=QuantizedMelody)
def get_quantized_melody(request: Request, audio_id: str) -> QuantizedMelody:
    job = _job(request, audio_id)
    if job.quantized_melody is None:
        raise HTTPException(status_code=409, detail="Quantized melody is not available")
    return job.quantized_melody


@router.post("/{audio_id}/harmony", response_model=HarmonyMelody)
async def create_harmony(request: Request, audio_id: str, config: HarmonyConfig) -> HarmonyMelody:
    job = _job(request, audio_id)
    if job.render_processing:
        raise HTTPException(status_code=409, detail="Rendering is processing")
    if job.quantized_melody is None:
        raise HTTPException(status_code=409, detail="Quantized melody is not available")
    temporary = job.source.parent / "harmony_melody.json.tmp"
    try:
        result = generate_harmony(job.quantized_melody, config)
        temporary.write_text(
            json.dumps(result.model_dump(), allow_nan=False, indent=2), encoding="utf-8"
        )
        temporary.replace(job.source.parent / "harmony_melody.json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Harmony export failed for audio ID %s", audio_id)
        raise HTTPException(status_code=500, detail="Harmony export failed; check server logs") from exc
    finally:
        temporary.unlink(missing_ok=True)
    job.harmony_melody = result
    job.rendered_files.clear()
    return result


@router.get("/{audio_id}/harmony", response_model=HarmonyMelody)
def get_harmony(request: Request, audio_id: str) -> HarmonyMelody:
    job = _job(request, audio_id)
    if job.harmony_melody is None:
        raise HTTPException(status_code=409, detail="Harmony melody is not available")
    return job.harmony_melody


@router.post("/{audio_id}/render", response_model=RenderResponse)
async def render_harmony(
    request: Request, audio_id: str, config: RenderConfig = Body(default=RenderConfig()),
) -> RenderResponse:
    job = _job(request, audio_id)
    if job.harmony_melody is None:
        raise HTTPException(status_code=409, detail="Harmony melody is not available")
    if job.render_processing:
        raise HTTPException(status_code=409, detail="Rendering is already processing")
    if config.output_mode == "vocal" and (
        job.status != "completed" or job.pitch_analysis is None or job.quantized_melody is None
    ):
        raise HTTPException(status_code=409, detail="Vocal rendering requires completed preprocessing, pitch analysis and quantization")
    job.render_processing = True
    job.rendered_files.clear()
    try:
        async with request.app.state.render_semaphore:
            diagnostics = {}
            if config.output_mode == "vocal":
                duration = await asyncio.to_thread(
                    request.app.state.rendering_service.render_vocal, job.source.parent,
                    job.pitch_analysis, job.quantized_melody, job.harmony_melody,
                    config, job.rendered_files, diagnostics,
                )
            else:
                duration = await asyncio.to_thread(
                    request.app.state.rendering_service.render, job.source.parent, job.source,
                    config, job.rendered_files, diagnostics,
                )
        return RenderResponse(
            audio_id=audio_id, duration_seconds=duration,
            files={name: f"{settings.api_prefix}/audio/{audio_id}/files/{name}" for name in sorted(job.rendered_files)},
            mix_diagnostics=diagnostics.get("mix"),
            output_mode=config.output_mode,
            warning=("Experimental vocal harmony: robotic artifacts, early pitch transitions and missing consonants may occur. Not production quality."
                     if config.output_mode == "vocal" else None),
        )
    except RenderInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MissingRenderDependency as exc:
        midi_hint = f" MIDI remains available at {settings.api_prefix}/audio/{audio_id}/files/harmony.mid" if "harmony.mid" in job.rendered_files else ""
        raise HTTPException(status_code=503, detail=str(exc) + midi_hint) from exc
    except (RenderError, OSError) as exc:
        logger.exception("Rendering failed for audio ID %s", audio_id)
        raise HTTPException(status_code=500, detail="Rendering failed; check server logs. Completed render files remain downloadable") from exc
    finally:
        job.render_processing = False

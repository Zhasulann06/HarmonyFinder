"""Application settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOCAL_FLUIDSYNTH = PROJECT_ROOT / "tools" / "fluidsynth-v2.6.1-win10-x64-cpp11" / "bin" / "fluidsynth.exe"
LOCAL_SOUNDFONT = PROJECT_ROOT / "assets" / "soundfonts" / "FluidR3 GM2-2.SF2"


def resolve_project_path(value: str | Path) -> Path:
    """Anchor relative filesystem paths to the repository, not the shell."""
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def resolve_executable(value: str) -> str:
    """Keep bare commands for PATH lookup; resolve explicit filesystem paths."""
    if Path(value).is_absolute() or "/" in value or "\\" in value:
        return str(resolve_project_path(value))
    return value


def default_fluidsynth_executable() -> str:
    override = os.getenv("HARMONYFINDER_FLUIDSYNTH")
    if override:
        return resolve_executable(override)
    return str(LOCAL_FLUIDSYNTH) if LOCAL_FLUIDSYNTH.is_file() else "fluidsynth"


def default_soundfont_path() -> str:
    override = os.getenv("HARMONYFINDER_SOUNDFONT")
    return str(resolve_project_path(override)) if override else str(LOCAL_SOUNDFONT)


@dataclass(frozen=True, slots=True)
class Settings:
    """Application settings shared across modules."""

    service_name: str = "HarmonyFinder API"
    api_prefix: str = "/api"
    audio_root: Path = Path(__file__).resolve().parents[2] / "data" / "audio"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_duration_seconds: float = 30.0
    soundfont_path: str | None = field(default_factory=default_soundfont_path)
    fluidsynth_executable: str = field(default_factory=default_fluidsynth_executable)


settings = Settings()


"""Local defaults and overrides without launching external synthesis."""

from pathlib import Path

import pytest

from backend.app.audio.piano_renderer import FluidSynthPianoRenderer
from backend.app.audio.render_errors import MissingRenderDependency
from backend.app.core import config
from backend.app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARMONYFINDER_FLUIDSYNTH", raising=False)
    monkeypatch.delenv("HARMONYFINDER_SOUNDFONT", raising=False)


def test_defaults_are_anchored_to_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = config.Settings()
    assert Path(settings.soundfont_path) == config.PROJECT_ROOT / "assets/soundfonts/FluidR3 GM2-2.SF2"
    # Simulate a present local executable independently of the developer's setup.
    local = tmp_path / "local fluidsynth.exe"
    local.touch()
    monkeypatch.setattr(config, "LOCAL_FLUIDSYNTH", local)
    renderer = FluidSynthPianoRenderer()
    assert renderer.executable == str(local)
    assert renderer.soundfont == config.LOCAL_SOUNDFONT


def test_relative_environment_overrides_ignore_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARMONYFINDER_FLUIDSYNTH", "custom tools/fluid synth.exe")
    monkeypatch.setenv("HARMONYFINDER_SOUNDFONT", "custom fonts/My Piano.SF2")
    settings = config.Settings()
    renderer = FluidSynthPianoRenderer()
    assert settings.fluidsynth_executable == str(config.PROJECT_ROOT / "custom tools/fluid synth.exe")
    assert settings.soundfont_path == str(config.PROJECT_ROOT / "custom fonts/My Piano.SF2")
    assert renderer.executable == settings.fluidsynth_executable
    assert renderer.soundfont == Path(settings.soundfont_path)


def test_absolute_overrides_take_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executable, font = tmp_path / "override.exe", tmp_path / "piano.sf2"
    monkeypatch.setenv("HARMONYFINDER_FLUIDSYNTH", str(executable))
    monkeypatch.setenv("HARMONYFINDER_SOUNDFONT", str(font))
    renderer = FluidSynthPianoRenderer()
    assert renderer.executable == str(executable)
    assert renderer.soundfont == font
    # An invalid override must not silently use the installed local SoundFont.
    with pytest.raises(MissingRenderDependency, match="HARMONYFINDER_SOUNDFONT"):
        renderer.render(tmp_path / "unused.mid", tmp_path / "unused.wav", 1, 0.5)


def test_system_command_override_and_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LOCAL_FLUIDSYNTH", tmp_path / "missing.exe")
    assert config.Settings().fluidsynth_executable == "fluidsynth"
    monkeypatch.setenv("HARMONYFINDER_FLUIDSYNTH", "system-fluidsynth")
    assert FluidSynthPianoRenderer().executable == "system-fluidsynth"


def test_api_uses_configured_paths_independently_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    # App settings are read at startup; inject freshly constructed settings.
    settings = config.Settings()
    monkeypatch.setattr("backend.app.main.settings", settings)
    renderer = create_app().state.rendering_service.piano
    assert renderer.soundfont == Path(settings.soundfont_path)
    assert renderer.executable == settings.fluidsynth_executable

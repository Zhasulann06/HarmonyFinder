"""Errors shared by MIDI, piano, and preview rendering."""


class RenderInputError(ValueError):
    """Rendering input is invalid."""


class RenderError(RuntimeError):
    """Rendering failed or produced invalid output."""


class MissingRenderDependency(RenderError):
    """An optional synthesizer, SoundFont, or decoder is unavailable."""

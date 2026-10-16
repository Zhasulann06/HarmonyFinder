"""Shared pitch classes, scales, and MIDI note naming."""

PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
KEYS = {name: index for index, name in enumerate(PITCH_CLASSES)}
KEYS.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})
SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "natural_minor": (0, 2, 3, 5, 7, 8, 10)}


def normalize_key(value: str | None) -> str | None:
    if value is None:
        return None
    name = value.strip().capitalize()
    if name not in KEYS:
        raise ValueError("Key must be one of the 12 tonic pitch classes")
    return PITCH_CLASSES[KEYS[name]]


def midi_to_note_name(note: int) -> str:
    """Name notes with sharps and MIDI 60 = C4."""
    return f"{PITCH_CLASSES[note % 12]}{note // 12 - 1}"

"""Compare detected chord vocabulary with major/natural-minor keys; no key inference."""

import argparse
import json
from pathlib import Path

from experiments.chord_recognition.detector import PITCHES

ROOT = Path(__file__).resolve().parent
MAJOR_DEGREES = ((0, "major"), (2, "minor"), (4, "minor"),
                 (5, "major"), (7, "major"), (9, "minor"))
MINOR_DEGREES = ((0, "minor"), (3, "major"), (5, "minor"),
                 (7, "minor"), (8, "major"), (10, "major"))


def vocabulary(root: int, mode: str) -> set[str]:
    degrees = MAJOR_DEGREES if mode == "major" else MINOR_DEGREES
    return {f"{PITCHES[(root + step) % 12]}:{quality}" for step, quality in degrees}


def compare(frames: list[dict]) -> list[dict]:
    classified = sum(frame["end"] - frame["start"] for frame in frames
                     if frame["label"] not in {"ambiguous", "no_chord"})
    scores = []
    for root, name in enumerate(PITCHES):
        for mode in ("major", "natural_minor"):
            allowed = vocabulary(root, mode)
            seconds = sum(frame["end"] - frame["start"] for frame in frames
                          if frame["label"] in allowed)
            scores.append({"key": f"{name} {mode}", "compatible_seconds": seconds,
                           "classified_seconds": classified,
                           "fraction": seconds / classified if classified else None,
                           "vocabulary": sorted(allowed)})
    return sorted(scores, key=lambda item: item["compatible_seconds"], reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new key comparison JSON within experiment runs")
    source = json.loads(args.timeline.read_text(encoding="utf-8"))
    scores = compare(source["frames"])
    report = {"scores": scores,
              "interpretation": "Vocabulary compatibility only, not a key estimate or accuracy measure. Relative major/minor pairs share triads; ambiguous/no-chord frames are excluded; diminished chords are not modeled."}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(scores[:8], indent=2))


if __name__ == "__main__":
    main()

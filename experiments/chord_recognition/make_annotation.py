"""Build a non-destructive human chord-review worksheet from a timeline."""

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new worksheet CSV inside experiment runs")
    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    fields = ("start_seconds", "end_seconds", "predicted", "minimum_confidence",
              "human_chord", "human_no_chord_or_ambiguous", "review_notes")
    with output.open("x", encoding="utf-8-sig", newline="") as artifact:
        writer = csv.DictWriter(artifact, fieldnames=fields)
        writer.writeheader()
        for segment in timeline["timeline"]:
            writer.writerow({"start_seconds": segment["start"],
                             "end_seconds": segment["end"],
                             "predicted": segment["label"],
                             "minimum_confidence": round(segment["confidence"], 3),
                             "human_chord": "", "human_no_chord_or_ambiguous": "",
                             "review_notes": ""})
    print(output)


if __name__ == "__main__":
    main()

"""Explicitly tag low-confidence, ambiguous and no-chord real-audio spans."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def status(frame: dict) -> str:
    if frame["label"] in {"ambiguous", "no_chord"}:
        return frame["label"]
    return "low_confidence" if frame["confidence"] < 0.5 else "chord"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new status JSON inside experiment runs")
    source = json.loads(args.timeline.read_text(encoding="utf-8"))
    rows = [{"start": frame["start"], "end": frame["end"],
             "label": frame["label"], "confidence": frame["confidence"],
             "status": status(frame)} for frame in source["frames"]]
    seconds = {kind: sum(row["end"] - row["start"] for row in rows if row["status"] == kind)
               for kind in ("chord", "low_confidence", "ambiguous", "no_chord")}
    report = {"threshold": "labelled chord with heuristic confidence < 0.5 is low_confidence",
              "status_seconds": seconds, "frames": rows}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(seconds, indent=2))


if __name__ == "__main__":
    main()

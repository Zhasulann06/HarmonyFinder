"""Summarize local transition overshoot for existing Phase 4C-2 renders."""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
NAMES = ("harmony-above-baseline80-20261017", "harmony-above-short30-20261017",
         "harmony-above-motion30-20261017", "harmony-below-baseline80-20261017",
         "harmony-below-short30-20261017")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runs").resolve()) or output.exists():
        parser.error("Choose a new JSON inside the isolated runs")
    rows = []
    for name in NAMES:
        run = ROOT / "runs" / name
        schedule = json.loads((run / "shift_map.json").read_text(encoding="utf-8"))
        metrics = json.loads((run / "melodic_metrics.json").read_text(encoding="utf-8"))
        with np.load(run / "melodic_measured_f0.npz") as contours:
            times, source, generated = (contours[key] for key in
                                        ("times_seconds", "source_hz", "generated_hz"))
        boundary_rows = []
        all_overshoot = []
        for boundary, measured in zip(schedule["boundaries"], metrics["boundaries"]):
            near = abs(times - boundary["center_seconds"]) <= 0.1
            valid = near & (source > 1) & (generated > 1)
            relative = 1200 * np.log2(generated[valid] / source[valid])
            low = 100 * min(boundary["from_semitones"], boundary["to_semitones"])
            high = 100 * max(boundary["from_semitones"], boundary["to_semitones"])
            overshoot = np.maximum(np.maximum(low - relative, relative - high), 0)
            all_overshoot.extend(overshoot.tolist())
            boundary_rows.append({"center_seconds": boundary["center_seconds"],
                                  "placement": boundary.get("placement", "unspecified"),
                                  "voiced_frames": int(valid.sum()),
                                  "overshoot_p90_cents": float(np.percentile(overshoot, 90))
                                  if len(overshoot) else None,
                                  "overshoot_max_cents": float(np.max(overshoot))
                                  if len(overshoot) else None,
                                  "crossing_error_ms": measured.get("crossing_error_ms")})
        rows.append({"label": schedule["label"], "boundaries": boundary_rows,
                     "all_boundary_voiced_frames": len(all_overshoot),
                     "overshoot_p90_cents": float(np.percentile(all_overshoot, 90))
                     if all_overshoot else None,
                     "overshoot_max_cents": float(max(all_overshoot))
                     if all_overshoot else None})
    report = {"definition": "Generated/source relative shift beyond the pair of intended adjacent note offsets, evaluated within +/-100 ms of boundaries where both F0s are voiced. Values include F0 estimator errors and natural pitch motion; not a perceptual artifact score.",
              "runs": rows}
    with output.open("x", encoding="utf-8") as artifact:
        json.dump(report, artifact, indent=2, allow_nan=False)
    for row in rows:
        print(row["label"], row["overshoot_p90_cents"], row["overshoot_max_cents"])


if __name__ == "__main__":
    main()

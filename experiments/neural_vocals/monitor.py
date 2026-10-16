"""Run the isolated trial while sampling device-wide NVIDIA memory (not just tensors)."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg-rate", type=float, default=0.7)
    parser.add_argument("--shift-map", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    run = args.run.resolve()
    if not run.is_relative_to(root / "runs") or not run.is_dir():
        parser.error("Use an existing isolated comparison run")
    log = run / "inference_console.txt"
    telemetry = run / "gpu_samples.jsonl"
    summary = run / "monitor_report.json"
    if any(path.exists() for path in (log, telemetry, summary)):
        raise RuntimeError("Use a new attempt directory; preserve previous telemetry")
    started = time.perf_counter()
    samples = []
    with log.open("x", encoding="utf-8") as console, telemetry.open("x", encoding="utf-8") as output:
        command = [sys.executable, "-u", str(root / "seed_runner.py"),
                   "--run", str(run), "--steps", str(args.steps),
                   "--cfg-rate", str(args.cfg_rate)]
        if args.shift_map:
            command.extend(["--shift-map", str(args.shift_map)])
        process = subprocess.Popen(command,
                                   stdout=console, stderr=subprocess.STDOUT)
        while process.poll() is None:
            tick = time.perf_counter() - started
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=index,memory.used,memory.free,utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10, check=True)
                values = [int(x.strip()) for x in result.stdout.splitlines()[0].split(",")]
                entry = dict(zip(("gpu_index", "used_mib", "free_mib", "utilization_percent"), values))
                entry["elapsed_seconds"] = tick
                samples.append(entry)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                entry = {"elapsed_seconds": tick, "sampling_error": str(exc)}
            output.write(json.dumps(entry) + "\n")
            output.flush()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    report = {"exit_code": process.returncode, "wall_seconds": time.perf_counter() - started,
              "runner_pid": process.pid, "valid_samples": len(samples),
              "peak_device_used_mib": max((x["used_mib"] for x in samples), default=None),
              "scope": "Device-wide sampled memory includes other processes/driver; may miss subsecond peaks. Tensor peaks exist in seed_report.json only if model loading was reached."}
    summary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()

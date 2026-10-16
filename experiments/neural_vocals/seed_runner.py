"""Local-only Seed-VC V1 invocation; run with the separate experiment Python."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg-rate", type=float, default=0.7)
    parser.add_argument("--shift-map", type=Path, help="Optional known control probe, not a harmony engine")
    args = parser.parse_args()
    if not 1 <= args.steps <= 50:
        parser.error("Use 1–50 diffusion steps")
    if not 0 <= args.cfg_rate <= 1:
        parser.error("Use a CFG rate between 0 and 1")
    run = args.run.resolve()
    if not run.is_relative_to((ROOT / "runs").resolve()) or not (run / "original_vocals.wav").is_file():
        parser.error("Use a prepared comparison run under experiments/neural_vocals/runs")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        parser.error("Use experiments/neural_vocals/.venv; never use the app environment")
    schedule = None
    shift_map_path = args.shift_map.resolve() if args.shift_map else None
    if args.shift_map:
        if shift_map_path != (run / "shift_map.json").resolve():
            parser.error("Use the shift_map.json inside the prepared run")
        schedule = json.loads(shift_map_path.read_text(encoding="utf-8"))
        label = schedule.get("label")
        if label not in {"dynamic_plus_3_4", "dynamic_minus_3_4"} and not (
            isinstance(label, str)
            and re.fullmatch(r"harmony_(above|below)_(baseline80|short30|motion30)", label)
        ):
            parser.error("Use a declared dynamic experiment label")
    report_path = run / ("seed_map_report.json" if schedule else "seed_report.json")
    labels = (schedule["label"],) if schedule else ("neural_plus_3", "neural_minus_3")
    if report_path.exists() or any((run / label).exists() for label in labels):
        parser.error("Preserve the existing result; use a new attempt directory with identical inputs")
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
    sys.path.insert(0, str(PROJECT))
    sys.path.insert(0, str(ROOT / "vendor" / "seed-vc"))
    os.chdir(ROOT / "vendor" / "seed-vc")
    try:
        import numpy as np
        import torch
        import yaml
        import soundfile as sf
    except (ImportError, OSError) as exc:
        report = {"stage": "dependency_preflight", "models_loaded": False,
                  "error": {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
                  "packages": dict(sorted((dist.metadata["Name"], dist.version)
                                          for dist in importlib.metadata.distributions())),
                  "action": "Resolve the isolated dependencies or Windows runtime DLL error; app .venv stays unchanged"}
        with (run / f"prerequisite_failure-{time.time_ns()}.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        raise RuntimeError(report["action"]) from exc
    from experiments.neural_vocals.control import target_f0
    from experiments.neural_vocals.resources import cpu_memory

    if not torch.cuda.is_available():
        raise RuntimeError("The experiment requires CUDA torch; app CPU torch must not be replaced")
    torch.set_num_threads(2)
    report = {"device": torch.cuda.get_device_name(), "torch": torch.__version__,
              "cuda_runtime": torch.version.cuda, "steps": args.steps, "cfg_rate": args.cfg_rate,
              "python": sys.version, "executable": sys.executable,
              "packages": dict(sorted((dist.metadata["Name"], dist.version)
                                      for dist in importlib.metadata.distributions())),
              "gpu_free_total_before": list(torch.cuda.mem_get_info()), "renders": {},
              "cpu_memory_before": cpu_memory(), "pid": os.getpid()}
    started = time.perf_counter()
    try:
        import inference
        source_code = ROOT / "vendor" / "seed-vc" / "inference.py"
        report["upstream_inference_sha256"] = hashlib.sha256(source_code.read_bytes()).hexdigest()
        assets = ROOT / "assets"
        lookup = {("lj1995/VoiceConversionWebUI", "rmvpe.pt"): assets / "rmvpe" / "rmvpe.pt",
                  ("funasr/campplus", "campplus_cn_common.bin"): assets / "campplus" / "campplus_cn_common.bin"}

        def local_asset(repo: str, filename: str, config_filename=None):
            if config_filename is not None or (repo, filename) not in lookup:
                raise RuntimeError(f"Unplanned model request blocked: {repo}/{filename}")
            return str(lookup[repo, filename])

        inference.load_custom_model_from_hf = local_asset
        config = yaml.safe_load((assets / "seed" / "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml").read_text())
        config["model_params"]["vocoder"]["name"] = str(assets / "bigvgan")
        config["model_params"]["speech_tokenizer"]["name"] = str(assets / "whisper")
        local_config = run / "local_seed_config.yml"
        local_config.write_text(yaml.safe_dump(config), encoding="utf-8")
        common = dict(f0_condition=True, auto_f0_adjust=False, length_adjust=1.0, inference_cfg_rate=args.cfg_rate,
                      fp16=True, diffusion_steps=args.steps, source=str(run / "original_vocals.wav"),
                      target=str(run / "reference_same_singer.wav"),
                      checkpoint=str(assets / "seed" / "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth"),
                      config=str(local_config))
        load_start = time.perf_counter()
        models = inference.load_models(SimpleNamespace(**common))
        torch.cuda.synchronize()
        report["model_load_seconds"] = time.perf_counter() - load_start
        report["load_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["load_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        report["cpu_memory_after_load"] = cpu_memory()
        # Reuse loaded official modules across fixed-shift trials.
        inference.load_models = lambda _: models
        trials = [(3, "neural_plus_3"), (-3, "neural_minus_3")]
        if schedule:
            trials = [(0, schedule["label"])]
            original_f0 = models[2]
            calls = 0
            target_contour = None

            def controlled_f0(audio, **kwargs):
                nonlocal calls, target_contour
                contour = original_f0(audio, **kwargs)
                calls += 1
                if calls == 2:  # Official main extracts reference first, source second.
                    target_contour = target_f0(
                        contour, times=np.array(schedule["times"]), shifts=np.array(schedule["shifts"])
                    )
                    with (run / "injected_f0.npz").open("xb") as artifact:
                        np.savez_compressed(artifact, source_hz=contour, target_hz=target_contour,
                                            times_seconds=np.arange(len(contour)) * 0.01)
                    return target_contour
                return contour

            inference.load_models = lambda _: (*models[:2], controlled_f0, *models[3:])
            original_regulator_forward = models[0].length_regulator.forward
            regulator_calls = 0

            def checked_regulator(*regulator_args, **regulator_kwargs):
                nonlocal regulator_calls
                regulator_calls += 1
                if regulator_calls == 1:
                    supplied = regulator_kwargs.get("f0")
                    expected = (torch.from_numpy(target_contour).to(supplied.device)[None]
                                if target_contour is not None and supplied is not None else None)
                    if expected is not None and supplied.shape == expected.shape:
                        report["f0_forward_max_abs_error_hz"] = float((supplied - expected).abs().max().item())
                        report["f0_forward_voiced_count"] = int((supplied > 1).sum().item())
                    if (expected is None or supplied.shape != expected.shape
                            or not torch.allclose(supplied, expected, rtol=1e-5, atol=1e-3)):
                        raise RuntimeError("External F0 was not passed intact into the source length regulator")
                    report["external_f0_verified_at_regulator"] = True
                    report["source_f0_frames"] = len(target_contour)
                return original_regulator_forward(*regulator_args, **regulator_kwargs)

            models[0].length_regulator.forward = checked_regulator
            report["shift_map_sha256"] = hashlib.sha256(shift_map_path.read_bytes()).hexdigest()
            report["shift_map"] = schedule
        for shift, label in trials:
            destination = run / label
            destination.mkdir(exist_ok=False)
            torch.manual_seed(1234)
            np.random.seed(1234)
            torch.cuda.reset_peak_memory_stats()
            tick = time.perf_counter()
            inference.main(SimpleNamespace(**common, semi_tone_shift=shift, output=str(destination)))
            if schedule and (calls != 2 or regulator_calls != 2 or not report.get("external_f0_verified_at_regulator")):
                raise RuntimeError("Unexpected Seed-VC F0 or length-regulator call sequence")
            torch.cuda.synchronize()
            output = list(destination.glob("*.wav"))
            if len(output) != 1:
                raise RuntimeError("Expected one raw inference WAV")
            audio, rate = sf.read(output[0], always_2d=True)
            if not len(audio) or not np.all(np.isfinite(audio)) or not np.any(audio) or np.max(np.abs(audio)) >= 1:
                raise RuntimeError("Neural output is empty, silent, non-finite or sample-clipped")
            report["renders"][label] = {"path": str(output[0].relative_to(run)), "seconds": time.perf_counter() - tick,
                "rate": rate, "channels": audio.shape[1], "frames": len(audio),
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "gpu_free_total_after": list(torch.cuda.mem_get_info()), "cpu_memory_after": cpu_memory()}
            named_output = run / f"{label}.wav"
            if named_output.exists():
                raise RuntimeError("Refusing to overwrite a previous comparison output")
            # Preserve the raw generator file; expose the requested comparison name via a hard link.
            os.link(output[0], named_output)
            print(json.dumps({label: report["renders"][label]}), flush=True)
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        if torch.cuda.is_initialized():
            report["peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            report["peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        raise
    finally:
        report["total_seconds"] = time.perf_counter() - started
        report["cpu_memory_final"] = cpu_memory()
        if report_path.exists():
            raise RuntimeError("Refusing to overwrite a prior inference report")
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()

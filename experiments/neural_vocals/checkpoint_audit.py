"""Read-only audit of the pinned Seed-VC checkpoint against its V1 config."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor" / "seed-vc"))

from modules.commons import build_model, recursive_munch  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to((ROOT / "runs").resolve()):
        parser.error("Write a new JSON file inside experiments/neural_vocals/runs")
    config_path = ROOT / "assets" / "seed" / "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml"
    checkpoint_path = ROOT / "assets" / "seed" / "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    params = recursive_munch(config["model_params"])
    params.dit_type = "DiT"
    model = build_model(params, stage="DiT")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    checkpoint_net = checkpoint["net"]
    sections: dict[str, dict] = {}
    for section, module in model.items():
        expected = module.state_dict()
        raw_stored = checkpoint_net.get(section, {})
        # Match the official loader's DDP-prefix normalization, without changing
        # checkpoint tensors or the in-memory checkpoint dictionary.
        stored = {key.removeprefix("module."): value for key, value in raw_stored.items()}
        matched = sorted(k for k in expected.keys() & stored.keys() if expected[k].shape == stored[k].shape)
        trainable = dict(module.named_parameters())
        shape_mismatch = {
            key: {"model": list(expected[key].shape), "checkpoint": list(stored[key].shape)}
            for key in sorted(expected.keys() & stored.keys())
            if expected[key].shape != stored[key].shape
        }
        missing = sorted(expected.keys() - stored.keys())
        unexpected = {key: list(stored[key].shape) for key in sorted(stored.keys() - expected.keys())}
        sections[section] = {
            "model_keys": len(expected), "checkpoint_keys": len(stored), "matched_keys": len(matched),
            "ddp_prefixed_checkpoint_keys": sum(k.startswith("module.") for k in raw_stored),
            "matched_parameters": sum(expected[k].numel() for k in matched),
            "model_parameters": sum(t.numel() for t in expected.values()),
            "trainable_parameter_keys": len(trainable),
            "unmatched_trainable_parameter_keys": sorted(set(trainable) - set(matched)),
            "missing_model_keys": missing, "unexpected_checkpoint_keys": unexpected,
            "shape_mismatches": shape_mismatch,
        }
        if section == "cfm" and "estimator.input_pos" in shape_mismatch:
            local = expected["estimator.input_pos"]
            saved = stored["estimator.input_pos"]
            sections[section]["input_pos_shared_prefix_identical"] = bool(
                torch.equal(local[:len(saved)], saved)
            )
    result = {
        "checkpoint": str(checkpoint_path), "checkpoint_sha256": sha256(checkpoint_path),
        "config": str(config_path), "config_sha256": sha256(config_path),
        "checkpoint_top_level_keys": sorted(checkpoint.keys()),
        "checkpoint_net_sections": sorted(checkpoint_net.keys()),
        "config_final_layer_type": config["model_params"]["DiT"]["final_layer_type"],
        "sections": sections,
        "scope": "Read-only CPU shape audit; no checkpoint parameters changed or loaded into the model",
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

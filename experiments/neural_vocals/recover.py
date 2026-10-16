"""Resume the approved Phase 4B-1 downloads from pinned official sources."""

import argparse
import concurrent.futures
import json
import os
import shutil
import time
from pathlib import Path

from experiments.neural_vocals.download_assets import ROOT, download_file, request, sha256
from experiments.neural_vocals.range_transfer import transfer

WHEELSETS = {"2.4.0": [
    ("torch-2.4.0+cu121-cp311-cp311-win_amd64.whl", 2441950418,
     "bada31485e04282b9f099da39b774484d3e4c431b7ea0df3663817295ae764e4"),
    ("torchaudio-2.4.0+cu121-cp311-cp311-win_amd64.whl", 4115561,
     "1e399d274eefd35d77224c2c308bdbfcd7300cfa2c080e098aa8f215d7aba482"),
], "2.4.1": [
    ("torch-2.4.1+cu121-cp311-cp311-win_amd64.whl", 2444893595,
     "bc1e21d7412a2f06f552a9afb92c56c8b23d174884e9383259c3cf5db4687c98"),
    ("torchaudio-2.4.1+cu121-cp311-cp311-win_amd64.whl", 4115589,
     "06095d5941a2843663a230bef739680541e0a491caf41df8fb1552eeefd212b0"),
]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["models", "wheels"])
    parser.add_argument("--max-seconds", type=int, default=7200)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=6,
                        help="Bounded range requests per large file (default: 6)")
    parser.add_argument("--torch-version", choices=tuple(WHEELSETS), default="2.4.0",
                        help="2.4.1 needs a separate 2.45 GB download approval; default reuses 2.4.0")
    args = parser.parse_args()
    if shutil.disk_usage(ROOT).free < 15_000_000_000:
        raise RuntimeError("Keep at least 15 GB free before recovering this experiment")
    deadline = time.monotonic() + args.max_seconds
    items = []
    if args.kind == "models":
        manifest = json.loads((ROOT / "asset_manifest.json").read_text())
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            # Reuse the upstream-bundled CAMPPlus only after matching the official LFS hash.
            bundled = ROOT / "vendor" / "seed-vc" / entry["name"]
            if not path.exists() and entry["name"] == "campplus_cn_common.bin" and bundled.is_file():
                if sha256(bundled) != entry["sha256"]:
                    raise ValueError("Bundled CAMPPlus hash mismatch")
                path.parent.mkdir(parents=True, exist_ok=True)
                os.link(bundled, path)
                print("Reused verified CAMPPlus via hard link; no duplicate weight bytes", flush=True)
            url = f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{entry['name']}"
            items.append((url, path, entry["bytes"], entry["sha256"]))
    else:
        for name, size, digest in WHEELSETS[args.torch_version]:
            url = "https://download.pytorch.org/whl/cu121/" + name.replace("+", "%2B")
            if size is None:
                import urllib.request
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as response:
                    size = int(response.headers["Content-Length"])
            items.append((url, ROOT / "assets" / "wheels" / name, size, digest))

    def fetch(item):
        url, path, size, digest = item
        transfer(url, path, size, digest, deadline=deadline, workers=args.workers)
        return {"path": str(path.relative_to(ROOT)), "bytes": size, "sha256": sha256(path)}

    results, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3 if args.kind == "models" else 2) as pool:
        futures = {pool.submit(fetch, item): item for item in items}
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"path": str(item[1]), "url": item[0], "error_type": type(exc).__name__, "error": str(exc)})
    report = ROOT / f"recovery_{args.kind}-{time.time_ns()}.json"
    report.write_text(json.dumps({"verified": results, "failures": failures}, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError(f"Downloads incomplete; partials preserved. See {report}")
    print(f"Verified all {args.kind}: {report}", flush=True)


if __name__ == "__main__":
    main()

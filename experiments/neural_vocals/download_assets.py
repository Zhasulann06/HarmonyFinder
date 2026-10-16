"""Pinned public assets, size/hash verification; no audio is sent anywhere."""

import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED_REVISION = "51383efd921027683c89e5348211d93ff12ac2a8"
REPOSITORIES = {
    "seed": ("Plachta/Seed-VC", "257283f9f41585055e8f858fba4fd044e5caed6e", [
        "DiT_seed_v2_uvit_whisper_base_f0_44k_bigvgan_pruned_ft_ema_v2.pth",
        "config_dit_mel_seed_uvit_whisper_base_f0_44k.yml", "README.md"]),
    "bigvgan": ("nvidia/bigvgan_v2_44khz_128band_512x", "95a9d1dcb12906c03edd938d77b9333d6ded7dfb", [
        "bigvgan_generator.pt", "config.json", "LICENSE", "README.md"]),
    "whisper": ("openai/whisper-small", "973afd24965f72e36ca33b3055d56a652f456b4d", [
        "model.safetensors", "config.json", "preprocessor_config.json", "README.md"]),
    "rmvpe": ("lj1995/VoiceConversionWebUI", "e6d0c1a17da07c33557852f9dfa2bd44cc75737d", ["rmvpe.pt", "README.md"]),
    "campplus": ("funasr/campplus", "e4b6ede7ce16997aff4ae69fbca1f0175e2afede", ["campplus_cn_common.bin", "README.md"]),
}


def request(url: str, headers: dict[str, str] | None = None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HarmonyFinder-Phase4A", **(headers or {})}), timeout=30)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, path: Path, size: int, expected_hash: str | None,
                  *, deadline: float, chunk_size: int = 8 * 1024 * 1024) -> None:
    """Resume only verified HTTP ranges; partial files never become usable assets."""
    if path.exists():
        if path.stat().st_size == size and (expected_hash is None or sha256(path) == expected_hash):
            return
        raise ValueError(f"Refusing to overwrite unverified asset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        raise ValueError("Partial download exceeds declared size")
    while offset < size:
        if time.monotonic() >= deadline:
            raise TimeoutError("Download time budget reached; rerun to resume verified ranges")
        end = min(size - 1, offset + chunk_size - 1)
        for attempt in range(6):
            offset = partial.stat().st_size if partial.exists() else 0
            end = min(size - 1, offset + chunk_size - 1)
            try:
                with request(url, {"Range": f"bytes={offset}-{end}"}) as response:
                    expected_range = f"bytes {offset}-{end}/{size}"
                    complete_small_file = response.status == 200 and offset == 0 and end == size - 1
                    if not complete_small_file and (response.status != 206 or response.headers.get("Content-Range") != expected_range):
                        raise ValueError("Server did not honor the exact requested range; refusing to append")
                    with partial.open("ab") as output:
                        remaining = end - offset + 1
                        while remaining:
                            if time.monotonic() >= deadline:
                                raise TimeoutError("Download time budget reached; partial data retained")
                            block = response.read(min(64 * 1024, remaining))
                            if not block:
                                raise OSError("Truncated HTTP range")
                            output.write(block)
                            offset += len(block)
                            remaining -= len(block)
                break
            except (OSError, urllib.error.URLError) as exc:
                event = {"url": url, "file": str(path), "attempt": attempt + 1,
                         "partial_bytes": partial.stat().st_size if partial.exists() else 0,
                         "error_type": type(exc).__name__, "error": str(exc)}
                with (path.parent / "download_errors.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps(event) + "\n")
                print(json.dumps(event), flush=True)
                if attempt == 5 or time.monotonic() >= deadline:
                    raise
                time.sleep(min(2 ** attempt, 8))
        print(f"{path.name}: {offset}/{size} bytes", flush=True)
    if expected_hash is not None and sha256(partial) != expected_hash:
        raise ValueError("Downloaded file hash differs; partial retained for inspection")
    partial.replace(path)


def download_source(deadline: float) -> None:
    """Fetch code/config/licences only, verifying Git blob hashes; omit sample audio."""
    with request(f"https://api.github.com/repos/Plachtaa/seed-vc/git/trees/{SEED_REVISION}?recursive=1") as response:
        tree = json.load(response)
    root = ROOT / "vendor" / "seed-vc"
    inventory = []
    for item in tree["tree"]:
        relative = Path(item["path"])
        if item["type"] != "blob" or relative.parts[0] in {"examples", ".github"}:
            continue
        if relative.suffix not in {".py", ".yaml", ".yml", ".json", ".txt", ".md"} and relative.name != "LICENSE":
            continue
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root.resolve()) or item["size"] > 2_000_000:
            raise ValueError("Unsafe or excessive source file")
        if destination.exists():
            data = destination.read_bytes()
        else:
            if time.monotonic() >= deadline:
                raise TimeoutError("Source download budget reached; rerun to continue")
            with request(f"https://raw.githubusercontent.com/Plachtaa/seed-vc/{SEED_REVISION}/{item['path']}") as response:
                data = response.read(item["size"] + 1)
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if len(data) != item["size"] or blob != item["sha"]:
            raise ValueError("Source file does not match pinned Git blob")
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        inventory.append({"path": item["path"], "bytes": len(data), "git_blob": blob})
    (root.parent / "source_manifest.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Verified {len(inventory)} pinned source/config/licence files", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly download the reported assets")
    parser.add_argument("--max-seconds", type=int, default=900, help="Bounded download budget; rerun to resume")
    parser.add_argument("--source-only", action="store_true", help="Fetch the pinned source archive without model weights")
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error("--max-seconds must be positive")
    deadline = time.monotonic() + args.max_seconds
    manifest = []
    for local, (repo, revision, names) in REPOSITORIES.items():
        with request(f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&expand=false") as response:
            tree = {entry["path"]: entry for entry in json.load(response)}
        for name in names:
            entry = tree[name]
            manifest.append({"repo": repo, "revision": revision, "name": name, "bytes": entry["size"],
                             "sha256": entry.get("lfs", {}).get("oid"), "path": f"assets/{local}/{name}"})
    print(json.dumps({"total_asset_bytes": sum(x["bytes"] for x in manifest), "file_count": len(manifest)}, indent=2), flush=True)
    if not args.download:
        return
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "asset_manifest.json").write_text(json.dumps({"seed_source_revision": SEED_REVISION, "files": manifest}, indent=2), encoding="utf-8")
    for entry in ([] if args.source_only else manifest):
        path = ROOT / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size == entry["bytes"] and (not entry["sha256"] or sha256(path) == entry["sha256"]):
            print(f"Verified existing {path.name}", flush=True)
            continue
        url = f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{entry['name']}"
        print(f"Downloading {entry['name']} ({entry['bytes']} bytes)", flush=True)
        download_file(url, path, entry["bytes"], entry["sha256"], deadline=deadline)
        entry["verified_sha256"] = sha256(path)
    download_source(deadline)
    (ROOT / "asset_manifest.json").write_text(json.dumps({"seed_source_revision": SEED_REVISION, "files": manifest}, indent=2), encoding="utf-8")
    print("Assets verified; no inference has been run.", flush=True)


if __name__ == "__main__":
    main()

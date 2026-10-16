"""Bounded concurrent HTTP ranges; publish only after whole-file SHA-256 verification."""

import concurrent.futures
import json
import time
from pathlib import Path

from experiments.neural_vocals.download_assets import download_file, request, sha256


def transfer(url: str, path: Path, size: int, digest: str | None, *, deadline: float,
             workers: int = 6, block_size: int = 4 * 1024 * 1024) -> None:
    if path.exists() or size <= block_size:
        download_file(url, path, size, digest, deadline=deadline)
        return
    partial = path.with_suffix(path.suffix + ".partial")
    path.parent.mkdir(parents=True, exist_ok=True)
    start = partial.stat().st_size if partial.exists() else 0
    if start > size:
        raise ValueError("Oversized partial file")
    pieces = path.parent / (path.name + ".parts")
    pieces.mkdir(exist_ok=True)

    def fetch(bounds):
        lo, hi = bounds
        piece = pieces / f"{lo}-{hi}.part"
        for attempt in range(6):
            if time.monotonic() >= deadline:
                raise TimeoutError("Range transfer deadline reached; partials retained")
            have = piece.stat().st_size if piece.exists() else 0
            if have == hi - lo + 1:
                return piece
            if have > hi - lo + 1:
                raise ValueError("Oversized range piece")
            try:
                with request(url, {"Range": f"bytes={lo + have}-{hi}"}) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {lo + have}-{hi}/{size}":
                        raise ValueError("Exact range not honored")
                    with piece.open("ab") as output:
                        remaining = hi - lo + 1 - have
                        while remaining:
                            if time.monotonic() >= deadline:
                                raise TimeoutError("Range transfer deadline reached")
                            data = response.read(min(64 * 1024, remaining))
                            if not data:
                                raise OSError("Truncated range response")
                            output.write(data)
                            remaining -= len(data)
                return piece
            except OSError as exc:
                event = {"url": url, "range": [lo, hi], "type": type(exc).__name__, "error": str(exc)}
                with (path.parent / "download_errors.jsonl").open("a", encoding="utf-8") as log:
                    log.write(json.dumps(event) + "\n")
                if attempt == 5 or time.monotonic() >= deadline:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("Range retries exhausted")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        # Only one window is scheduled at a time: memory/disk overhead is bounded.
        while start < size:
            bounds = [(lo, min(size - 1, lo + block_size - 1))
                      for lo in range(start, min(size, start + workers * block_size), block_size)]
            for (lo, hi), piece in zip(bounds, pool.map(fetch, bounds)):
                with partial.open("ab") as output, piece.open("rb") as incoming:
                    while data := incoming.read(1024 * 1024):
                        output.write(data)
                start = hi + 1
                piece.unlink()  # Owned temporary bytes, now retained in the contiguous partial.
            print(f"{path.name}: {start}/{size} bytes", flush=True)
    if partial.stat().st_size != size or (digest is not None and sha256(partial) != digest):
        raise ValueError("Whole-file size/hash mismatch; partial retained, never published")
    partial.replace(path)

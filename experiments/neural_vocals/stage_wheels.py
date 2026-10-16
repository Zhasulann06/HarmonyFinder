"""Stage compatible PyPI wheels with resumable ranges and published SHA-256 checks."""

import argparse
import concurrent.futures
import json
import time
import urllib.request
from urllib.parse import urlparse

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

from experiments.neural_vocals.download_assets import ROOT
from experiments.neural_vocals.range_transfer import transfer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", help="Explicit name==version pins only")
    args = parser.parse_args()
    tags = list(sys_tags())
    records = []
    for pin in args.packages:
        name, version = pin.split("==")
        if not all(c.isalnum() or c in "-_." for c in name + version):
            parser.error("Invalid package pin")
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as response:
            metadata = json.load(response)
        candidates = []
        for item in metadata["urls"]:
            if item["packagetype"] != "bdist_wheel":
                continue
            _, _, _, wheel_tags = parse_wheel_filename(item["filename"])
            ranking = [i for i, tag in enumerate(tags) if tag in wheel_tags]
            if ranking:
                candidates.append((min(ranking), item))
        if not candidates:
            raise RuntimeError(f"No compatible wheel for {pin}")
        item = min(candidates, key=lambda x: x[0])[1]
        if urlparse(item["url"]).hostname != "files.pythonhosted.org":
            raise RuntimeError("Unexpected wheel host")
        records.append(item)
    deadline = time.monotonic() + 3600

    def fetch(item):
        transfer(item["url"], ROOT / "assets" / "wheels" / item["filename"],
                 item["size"], item["digests"]["sha256"], deadline=deadline)
        print(f"Verified PyPI wheel: {item['filename']}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(fetch, records))
    (ROOT / f"pypi_wheels-{time.time_ns()}.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

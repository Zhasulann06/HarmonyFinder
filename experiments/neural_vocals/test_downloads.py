"""Mocked transfers verify resume safety without downloading checkpoints."""

import hashlib
import io
import time

import pytest

from experiments.neural_vocals import download_assets as downloader


class Response(io.BytesIO):
    status = 206

    def __init__(self, data: bytes, content_range: str):
        super().__init__(data)
        self.headers = {"Content-Range": content_range}


def test_resume_verifies_size_hash_and_range(tmp_path, monkeypatch):
    path = tmp_path / "weights.pt"
    path.with_suffix(".pt.partial").write_bytes(b"abc")
    requested = []

    def request(url, headers):
        requested.append(headers["Range"])
        return Response(b"def", "bytes 3-5/6")

    monkeypatch.setattr(downloader, "request", request)
    downloader.download_file("https://example.invalid", path, 6, hashlib.sha256(b"abcdef").hexdigest(), deadline=time.monotonic() + 5)
    assert requested == ["bytes=3-5"]
    assert path.read_bytes() == b"abcdef"
    assert not path.with_suffix(".pt.partial").exists()


def test_wrong_range_never_appends_or_publishes(tmp_path, monkeypatch):
    path = tmp_path / "weights.pt"
    partial = path.with_suffix(".pt.partial")
    partial.write_bytes(b"abc")
    monkeypatch.setattr(downloader, "request", lambda *args: Response(b"abc", "bytes 0-2/6"))
    with pytest.raises(ValueError, match="range"):
        downloader.download_file("url", path, 6, None, deadline=time.monotonic() + 5)
    assert partial.read_bytes() == b"abc" and not path.exists()


def test_bad_hash_is_not_an_inference_asset(tmp_path, monkeypatch):
    path = tmp_path / "weights.pt"
    monkeypatch.setattr(downloader, "request", lambda *args: Response(b"abc", "bytes 0-2/3"))
    with pytest.raises(ValueError, match="hash"):
        downloader.download_file("url", path, 3, "wrong", deadline=time.monotonic() + 5)
    assert not path.exists()


def test_deadline_and_existing_files_are_preserved(tmp_path):
    path = tmp_path / "weights.pt"
    with pytest.raises(TimeoutError):
        downloader.download_file("url", path, 3, None, deadline=time.monotonic() - 1)
    path.write_bytes(b"user data")
    with pytest.raises(ValueError, match="overwrite"):
        downloader.download_file("url", path, 3, None, deadline=time.monotonic() + 5)
    assert path.read_bytes() == b"user data"


def test_parallel_ranges_resume_and_verify_whole_file(tmp_path, monkeypatch):
    from experiments.neural_vocals import range_transfer
    content = b"abcdefghijklmnopqrstuvwxyz"
    path = tmp_path / "weights.pt"
    path.with_suffix(".pt.partial").write_bytes(content[:3])
    requests = []

    def request(url, headers):
        lo, hi = map(int, headers["Range"].split("=")[1].split("-"))
        requests.append((lo, hi))
        return Response(content[lo:hi+1], f"bytes {lo}-{hi}/{len(content)}")

    monkeypatch.setattr(range_transfer, "request", request)
    range_transfer.transfer("url", path, len(content), hashlib.sha256(content).hexdigest(),
                            deadline=time.monotonic()+5, workers=3, block_size=4)
    assert path.read_bytes() == content
    assert min(lo for lo, _ in requests) == 3
    assert not list((tmp_path / "weights.pt.parts").glob("*.part"))


def test_parallel_ranges_reject_incorrect_range(tmp_path, monkeypatch):
    from experiments.neural_vocals import range_transfer
    path = tmp_path / "weights.pt"
    monkeypatch.setattr(range_transfer, "request", lambda *args: Response(b"abc", "bytes 0-2/100"))
    with pytest.raises(ValueError, match="range"):
        range_transfer.transfer("url", path, 20, None, deadline=time.monotonic()+5, block_size=4, workers=2)
    assert not path.exists()


def test_http_200_is_allowed_only_for_complete_small_file(tmp_path, monkeypatch):
    response = Response(b"abc", "")
    response.status = 200
    monkeypatch.setattr(downloader, "request", lambda *args: response)
    path = tmp_path / "config.json"
    downloader.download_file("url", path, 3, hashlib.sha256(b"abc").hexdigest(), deadline=time.monotonic()+5)
    assert path.read_bytes() == b"abc"

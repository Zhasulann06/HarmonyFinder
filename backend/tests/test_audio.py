"""Upload and separation API tests without model downloads."""

import io
import subprocess
import sys
import time
import types
import uuid
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.audio.validation import InvalidAudioError, validate_audio
from backend.app.audio.separator import DemucsSeparator, SeparationError


def wav_bytes(seconds: float = 0.1, rate: int = 8000) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(seconds * rate))
    return stream.getvalue()


class MockSeparator:
    def __init__(self, *, fail: bool = False, mismatch: bool = False) -> None:
        self.fail = fail
        self.mismatch = mismatch

    def separate(self, source: Path, output_dir: Path) -> None:
        assert source.exists()
        if self.fail:
            raise RuntimeError("mock inference failed")
        (output_dir / "vocals.wav").write_bytes(wav_bytes())
        (output_dir / "instrumental.wav").write_bytes(
            wav_bytes(seconds=0.2 if self.mismatch else 0.1)
        )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with TestClient(create_app(separator=MockSeparator(), audio_root=tmp_path)) as test_client:
        yield test_client


def upload(client: TestClient, content: bytes, name: str = "song.wav"):
    return client.post("/api/audio/upload", files={"file": (name, content)})


def wait_for_status(client: TestClient, audio_id: str, target: str) -> dict[str, object]:
    for _ in range(100):
        response = client.get(f"/api/audio/{audio_id}/status")
        if response.json()["status"] == target:
            return response.json()
        time.sleep(0.01)
    pytest.fail(f"Job did not reach {target}")


def test_valid_wav_upload_and_unique_ids(client: TestClient, tmp_path: Path) -> None:
    first = upload(client, wav_bytes())
    second = upload(client, wav_bytes())
    assert first.status_code == second.status_code == 201
    audio_id = first.json()["audio_id"]
    assert uuid.UUID(audio_id)
    assert audio_id != second.json()["audio_id"]
    assert first.json()["status"] == "queued"
    assert first.json()["duration_seconds"] == pytest.approx(0.1)
    assert (tmp_path / audio_id / "original.wav").read_bytes() == wav_bytes()
    assert client.get(f"/api/audio/{audio_id}/status").json()["status"] == "queued"


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("song.txt", b"text", 415),
        ("song.wav", b"not audio", 422),
        ("song.wav", b"RIFF\x00\x00", 422),
        ("song.wav", b"\x00" * 40, 422),
    ],
)
def test_invalid_uploads(
    client: TestClient, tmp_path: Path, name: str, content: bytes, expected: int
) -> None:
    assert upload(client, content, name).status_code == expected
    assert list(tmp_path.iterdir()) == []


def test_upload_size_limit(client: TestClient, tmp_path: Path) -> None:
    response = upload(client, b"a" * (20 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_upload_duration_limit(client: TestClient, tmp_path: Path) -> None:
    response = upload(client, wav_bytes(seconds=30.01))
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_mp3_requires_ffmpeg(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.app.audio.validation.shutil.which", lambda name: None)
    assert upload(client, b"not audio", "song.mp3").status_code == 503
    assert list(tmp_path.iterdir()) == []


def test_mp3_content_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "song.mp3"
    source.write_bytes(b"test data")
    monkeypatch.setattr(
        "backend.app.audio.validation.shutil.which", lambda name: name
    )
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[0] == "ffprobe":
            return subprocess.CompletedProcess(
                args, 0, '{"format":{"format_name":"mp3","duration":"1.5"}}', ""
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("backend.app.audio.validation.subprocess.run", fake_run)
    assert validate_audio(source, ".mp3", 30) == 1.5
    assert [call[0] for call in calls] == ["ffprobe", "ffmpeg"]

    def corrupt_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("backend.app.audio.validation.subprocess.run", corrupt_run)
    with pytest.raises(InvalidAudioError):
        validate_audio(source, ".mp3", 30)


def test_uploaded_name_cannot_select_storage_path(
    client: TestClient, tmp_path: Path
) -> None:
    response = upload(client, wav_bytes(), "../../escape.wav")
    assert response.status_code == 201
    audio_id = response.json()["audio_id"]
    assert (tmp_path / audio_id / "original.wav").exists()
    assert not (tmp_path.parent / "escape.wav").exists()
    assert client.get("/api/audio/not-a-uuid/status").status_code == 404
    assert client.get("/api/audio/%2e%2e/status").status_code == 404


def test_successful_separation_and_downloads(client: TestClient) -> None:
    audio_id = upload(client, wav_bytes()).json()["audio_id"]
    assert client.get(f"/api/audio/{audio_id}/files/vocals").status_code == 409
    start = client.post(f"/api/audio/{audio_id}/separate")
    assert start.status_code == 202
    assert start.json()["status"] == "processing"
    assert client.post(f"/api/audio/{audio_id}/separate").status_code == 409
    assert wait_for_status(client, audio_id, "completed")["error"] is None
    for stem in ("vocals", "instrumental"):
        result = client.get(f"/api/audio/{audio_id}/files/{stem}")
        assert result.status_code == 200
        assert result.content == wav_bytes()


@pytest.mark.parametrize("separator", [MockSeparator(fail=True), MockSeparator(mismatch=True)])
def test_failed_separation(
    tmp_path: Path, separator: MockSeparator
) -> None:
    with TestClient(create_app(separator=separator, audio_root=tmp_path)) as client:
        audio_id = upload(client, wav_bytes()).json()["audio_id"]
        assert client.post(f"/api/audio/{audio_id}/separate").status_code == 202
        status = wait_for_status(client, audio_id, "failed")
        assert status["error"]
        assert client.get(f"/api/audio/{audio_id}/files/vocals").status_code == 409
        assert not (tmp_path / audio_id / "vocals.wav").exists()


def test_demucs_adapter_uses_two_stem_cpu_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "demucs", types.ModuleType("demucs"))
    source = tmp_path / "original.wav"
    source.write_bytes(wav_bytes())
    output = tmp_path / "output"
    commands: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        stem_dir = output / "demucs_work" / "htdemucs" / "original"
        stem_dir.mkdir(parents=True)
        (stem_dir / "vocals.wav").write_bytes(wav_bytes())
        (stem_dir / "no_vocals.wav").write_bytes(wav_bytes())
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("backend.app.audio.separator.subprocess.run", fake_run)
    DemucsSeparator().separate(source, output)
    assert commands[0][1:8] == [
        "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-d"
    ]
    assert "cpu" in commands[0]
    assert (output / "vocals.wav").exists()
    assert (output / "instrumental.wav").exists()
    assert not (output / "demucs_work").exists()


def test_demucs_adapter_reports_inference_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "demucs", types.ModuleType("demucs"))
    source = tmp_path / "original.wav"
    source.write_bytes(wav_bytes())

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("backend.app.audio.separator.subprocess.run", fake_run)
    with pytest.raises(SeparationError):
        DemucsSeparator().separate(source, tmp_path / "output")

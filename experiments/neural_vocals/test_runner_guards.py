"""Runner boundaries fail before importing or loading any neural dependency."""

from pathlib import Path
import builtins
import json
import os
import sys

import pytest

from experiments.neural_vocals import seed_runner


def test_runner_refuses_app_environment(tmp_path: Path, monkeypatch, capsys) -> None:
    run = tmp_path / "runs" / "attempt"
    run.mkdir(parents=True)
    (run / "original_vocals.wav").touch()
    monkeypatch.setattr(seed_runner, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner", "--run", str(run)])
    with pytest.raises(SystemExit) as error:
        seed_runner.main()
    assert error.value.code == 2
    assert "never use the app environment" in capsys.readouterr().err
    assert list(run.iterdir()) == [run / "original_vocals.wav"]


def test_runner_preserves_previous_report(tmp_path: Path, monkeypatch, capsys) -> None:
    run = tmp_path / "runs" / "attempt"
    run.mkdir(parents=True)
    (run / "original_vocals.wav").touch()
    previous = run / "seed_report.json"
    previous.write_text('{"previous": true}', encoding="utf-8")
    monkeypatch.setattr(seed_runner, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(sys, "argv", ["runner", "--run", str(run)])
    with pytest.raises(SystemExit) as error:
        seed_runner.main()
    assert error.value.code == 2
    assert "Preserve the existing result" in capsys.readouterr().err
    assert previous.read_text() == '{"previous": true}'


def test_windows_dll_failure_is_recorded_before_model_loading(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "runs" / "attempt"
    run.mkdir(parents=True)
    (run / "original_vocals.wav").touch()
    (tmp_path / "vendor" / "seed-vc").mkdir(parents=True)
    monkeypatch.setattr(seed_runner, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", ["runner", "--run", str(run)])
    monkeypatch.chdir(tmp_path)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    original_import = builtins.__import__

    def fail_torch(name, *args, **kwargs):
        if name == "torch":
            raise OSError("[WinError 126] fbgemm.dll dependency missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_torch)
    with pytest.raises(RuntimeError, match="Windows runtime DLL"):
        seed_runner.main()
    report = json.loads(next(run.glob("prerequisite_failure-*.json")).read_text())
    assert report["models_loaded"] is False
    assert report["stage"] == "dependency_preflight"
    assert report["error"]["type"] == "OSError"
    assert "WinError 126" in report["error"]["message"]
    assert not (run / "seed_report.json").exists()

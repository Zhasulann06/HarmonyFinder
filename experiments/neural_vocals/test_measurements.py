"""Technical screens do not imply perceptual naturalness."""

import numpy as np

from experiments.neural_vocals.compare import silence_metrics
from experiments.neural_vocals.resources import cpu_memory


def test_silence_screen_detects_spill_and_dropout() -> None:
    source = np.array([0.0] * 10 + [0.1] * 10)[:, None]
    output = np.array([0.1] * 10 + [0.0] * 10)[:, None]
    result = silence_metrics(source, output, 1000)
    assert result["quiet_source_blocks"] == 1
    assert result["quiet_blocks_exceeding_minus_40_dbfs"] == 1
    assert result["active_blocks_becoming_quiet"] == 1


def test_no_silence_is_reported_as_not_measured() -> None:
    audio = np.ones((100, 1)) * 0.1
    assert silence_metrics(audio, audio, 1000)["quiet_output_rms_max"] is None


def test_memory_probe_reports_positive_counts_if_supported() -> None:
    result = cpu_memory()
    if result is not None:
        assert result["working_set_bytes"] > 0
        assert result["peak_working_set_bytes"] >= result["working_set_bytes"]

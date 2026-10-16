"""No torch, checkpoint or network is needed for these control contract tests."""

import numpy as np
import pytest
import json
from pathlib import Path

from experiments.neural_vocals.control import target_f0


@pytest.mark.parametrize("shift", [3, 4, -3, -4])
def test_fixed_shifts_and_unvoiced(shift: float) -> None:
    source = np.array([0, 220, 440, 0], dtype=float)
    result = target_f0(source, shift)
    np.testing.assert_allclose(result[[1, 2]], source[[1, 2]] * 2 ** (shift / 12), rtol=1e-6)
    np.testing.assert_array_equal(result[[0, 3]], [0, 0])
    np.testing.assert_array_equal(source, [0, 220, 440, 0])


def test_frame_level_dynamic_map_is_not_one_scalar_shift() -> None:
    source = np.array([220, 220, 0, 220, 220])
    result = target_f0(source, times=np.array([0, .01, .03, .04]), shifts=np.array([3, 4, -3, -4]))
    np.testing.assert_allclose(12 * np.log2(result[[0, 1, 3, 4]] / 220), [3, 4, -3, -4], atol=1e-5)
    assert result[2] == 0


@pytest.mark.parametrize("source,shift", [([float('nan')], 3), ([-1], 3), ([], 3), ([220], 13), ([1000], 4), ([50], -4)])
def test_reject_invalid_or_out_of_range(source, shift) -> None:
    with pytest.raises(ValueError):
        target_f0(np.array(source), shift)


@pytest.mark.parametrize("times,shifts", [([0, .01], [3, 4]), ([0, .04, .02], [3, 4, 3]), ([0, .04], [3, 15])])
def test_reject_incomplete_or_bad_map(times, shifts) -> None:
    with pytest.raises(ValueError):
        target_f0(np.full(5, 220), times=np.array(times), shifts=np.array(shifts))


@pytest.mark.parametrize("run_name,levels", [
    ("dynamic_plus_3_4.json", (3, 4, 3, 4)),
    ("dynamic_minus_3_4.json", (-3, -4, -3, -4)),
])
def test_experiment_maps_preserve_vibrato_and_unvoiced(run_name, levels) -> None:
    path = Path(__file__).resolve().parent / "fixtures" / run_name
    schedule = json.loads(path.read_text(encoding="utf-8"))
    t = np.arange(600) * .01
    source = 150 * 2 ** ((.18 * np.sin(2 * np.pi * 5 * t)) / 12)
    source[(t >= 1.9) & (t < 2.1)] = 0
    source[(t >= 4.0) & (t < 4.5)] = 0
    result = target_f0(source, times=np.array(schedule["times"]), shifts=np.array(schedule["shifts"]))
    for second, wanted in zip((.5, 1.7, 3.1, 5.0), levels):
        index = round(second * 100)
        assert 12 * np.log2(result[index] / source[index]) == pytest.approx(wanted, abs=.001)
    assert np.all(result[source == 0] == 0)
    # The variable shift is additive in semitones; source vibrato remains intact.
    first = round(.5 * 100)
    second = round(.55 * 100)
    source_motion = 12 * np.log2(source[second] / source[first])
    output_motion = 12 * np.log2(result[second] / result[first])
    assert output_motion == pytest.approx(source_motion, abs=.001)
    # Smoothstep has no instantaneous pitch step and eases into the ramp.
    start, quarter = round(1.31 * 100), round(1.33 * 100)
    initial = 12 * np.log2(result[start] / source[start])
    at_quarter = 12 * np.log2(result[quarter] / source[quarter])
    assert at_quarter - initial == pytest.approx((levels[1] - levels[0]) * .15625, abs=.001)

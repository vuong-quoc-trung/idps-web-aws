"""Locked publisher operating points and metrics, no optimizer work."""

import numpy as np
import pytest

from idps_ai.common import PipelineError
from idps_ai.training.publisher_evaluation import (
    fit_balanced_threshold,
    group_metrics,
    metrics,
    wilson,
)


def test_calibration_strict_greater_and_highest_exact_tie():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.2, 0.8, 0.9])
    fitted = fit_balanced_threshold(y, s)
    assert fitted["threshold"] == 0.2 and fitted["fit_partition"] == "CALIBRATION"
    result = metrics(y, s, fitted["threshold"])
    assert (result["TP"], result["FP"], result["TN"], result["FN"]) == (2, 0, 2, 0)
    assert result["average_precision"] == result["F1"] == 1
    constant = fit_balanced_threshold(y, np.full(4, 0.7))
    assert constant["threshold"] == 0.7
    no_flags = metrics(y, np.full(4, 0.7), 0.7)
    assert no_flags["precision"] is None and no_flags["recall"] == 0 and no_flags["FPR"] == 0
    assert no_flags["average_precision"] == 0.5


def test_wilson_zero_denominators_and_group_dependence():
    assert wilson(0, 0) is None
    interval = wilson(0, 184)
    assert interval[0] == 0 and interval[1] > 0.01
    y = np.array([0, 0, 0, 1])
    s = np.array([0.9, 0.9, 0.9, 0.9])
    raw = metrics(y, s, 0.5)
    grouped = group_metrics(y, s, 0.5, np.array([1, 1, 1, 2]))
    assert raw["precision"] == 0.25 and grouped["precision"] == 0.5
    assert grouped["groups"] == 2


def test_invalid_labels_and_scores_do_not_get_coerced():
    with pytest.raises(PipelineError):
        metrics([0, 0.5], [0.2, 0.3], 0.5)
    with pytest.raises(PipelineError):
        metrics([0, 1], [0.2, np.nan], 0.5)
    with pytest.raises(PipelineError):
        fit_balanced_threshold([0, 0], [0.2, 0.3])

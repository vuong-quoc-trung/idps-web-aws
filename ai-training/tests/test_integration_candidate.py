"""Behavioral checks for the one-candidate study and safety decision boundaries."""

import importlib.util
from pathlib import Path

import numpy as np


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numeric_mask_stateless_and_never_mutates_content_or_source():
    study = script("integration-request-study.py")
    x = np.ones((256, 588), np.float32)
    a, n = study.masked_batch(x, 31, 4, 0.25)
    b, m = study.masked_batch(x, 31, 4, 0.25)
    assert np.array_equal(a, b) and n == m and 0 < n < len(x)
    assert np.array_equal(a[:, 76:], x[:, 76:]) and np.all(x == 1)
    assert not np.array_equal(a, study.masked_batch(x, 31, 5, 0.25)[0])


def test_guard_hard_stop_precedes_pause_or_resume():
    g = script("integration-guard.py")
    assert g.control_action(80, 0, True, 30) == "KILL"
    assert g.control_action(72, 0, False, 0) == "FREEZE"
    assert g.control_action(66, 7, False, 0) == "FREEZE"
    assert g.control_action(67, 0, True, 4.9) == "WAIT"
    assert g.control_action(67, 0, True, 5) == "THAW"
    assert g.control_action(60, 0, False, 0, True) == "FREEZE"

"""Sampler/strict-threshold/retention invariants without training or private data."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def module(name):
    s = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / f"{name}.py"
    )
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_duplicate_views_not_counted_twice_and_conflicting_labels_rejected():
    m = module("train-request-v3-pilot")
    x = np.zeros((3, 634), np.float32)
    x[2, 1] = 1
    assert m.canonical_indices(
        x, np.array([0, 0, 1]), np.ones(3, bool), np.array(["b", "a", "c"])
    ).tolist() == [1, 2]
    with pytest.raises(AssertionError, match="Mixed labels"):
        m.canonical_indices(x, np.array([1, 0, 1]), np.ones(3, bool), np.array(["b", "a", "c"]))


def test_lineage_interleaving_is_seeded_once_per_view_and_RNG_resumable():
    m = module("train-request-v3-pilot")
    groups = ["a"] * 5 + ["b"] * 2 + ["c"]
    rng = np.random.default_rng(17)
    first = m.order_for_epoch(rng, groups)
    state = rng.bit_generator.state
    second = m.order_for_epoch(rng, groups)
    restored = np.random.default_rng()
    restored.bit_generator.state = state
    assert np.array_equal(m.order_for_epoch(restored, groups), second)
    assert sorted(first) == list(range(8))
    assert len({groups[i] for i in first[:3]}) == 3


def test_threshold_equality_is_negative_and_no_flags_precision_is_undefined():
    e = module("evaluate-request-v3-pilot")
    r = e.metrics(np.array([0, 1]), np.array([0.5, 0.5]), 0.5)
    assert r["FP"] == r["TP"] == 0 and r["precision"] is None
    assert e.binomial_interval(0, 0) is None
    assert e.binomial_interval(0, 11)[1] > 0.01


def test_acceptance_requires_gains_and_identity_based_no_new_false_positive():
    e = module("evaluate-request-v3-pilot")
    family = np.array(
        [
            "xss",
            "xss",
            "cmd_injection",
            "cmd_injection",
            "sqli",
            "path_traversal",
            "benign",
            "benign",
        ]
    )
    y = np.array([1] * 6 + [0, 0])
    base = np.array([0, 0, 0, 0, 1, 1, 1, 0], bool)
    cand = np.array([1] * 7 + [0], bool)
    flags = {"frozen": base, "calibration_only": base, "challenger": cand}
    assert e.retention(y, family, flags)["decision"].startswith("CASE_A")
    # Same FP count but different benign identity must FAIL.
    cand = cand.copy()
    cand[6:] = [0, 1]
    flags["challenger"] = cand
    assert not e.retention(y, family, flags)["checks"]["no_new_benign_ID_vs_either_reference"]
    assert e.retention(y, family, flags)["decision"].startswith("CASE_B")

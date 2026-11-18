"""Regression tests for strict threshold ties and irreducible feature ambiguity."""

import numpy as np
from calibration_pilot import collision_bound, cut_at_cap, waf_tuning


def test_cut_respects_strict_ties_at_weighted_boundary():
    scores = np.array([0.1, 0.4, 0.4, 0.9])
    mass = np.array([1.0, 0.2, 0.3, 0.5])
    assert cut_at_cap(scores, mass, target=0.25) == 0.4
    assert cut_at_cap(scores, mass, target=0.20) == 0.9


def test_collision_ceiling_never_treats_mixed_views_as_free_positive():
    labels = np.array([0] * 100 + [1, 1, 1])
    ids = np.array([0] * 98 + [1, 1] + [1, 1, 2])
    out = collision_bound(labels, ids, 3)
    assert out["mixed_label_vectors"] == 1
    assert out["hindsight_zero_FPR_URI100_recall_ceiling"] == 1 / 3
    assert out["hindsight_fractional_upper_bound_at_1pct_FPR"] == 2 / 3


def test_waf_reader_decodes_only_registered_tuning_suffix(tmp_path):
    x = np.zeros((5, 244), np.float32)
    x[:3] = np.nan  # Reading FIT as part of the result must fail validation.
    x[3:, 99] = [0.25, 0.50]
    path = tmp_path / "cohort.npz"
    np.savez(path, x=x, nfit=3, y=np.array([0, 0, 1, 0, 1]), component=np.arange(5))
    frame = waf_tuning(path)
    np.testing.assert_array_equal(frame["y"], [0, 1])
    np.testing.assert_array_equal(frame["group"], [3, 4])
    np.testing.assert_array_equal(frame["x"][:, 99], [0.25, 0.50])

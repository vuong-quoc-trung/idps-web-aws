import numpy as np
from r18_train import WeightedSwiGLU
from r24_data import census
from r24_eval import confusion, fp_cut
from r24_pilot import ARCH, warm_start


def test_fp_budget_never_breaks_equal_score_group():
    y = np.array([0, 0, 0, 1, 1])
    s = np.array([0.80, 0.80, 0.70, 0.90, 0.75])
    assert fp_cut(y, s, 1) == 0.80
    assert confusion(y, s > fp_cut(y, s, 1))["tn_fp_fn_tp"] == [3, 0, 1, 1]
    assert confusion(y, s > fp_cut(y, s, 2))["tn_fp_fn_tp"] == [1, 2, 0, 2]


def test_census_preserves_original_class_counts_in_conflicting_vector():
    x = np.array([[0, 1], [0, 1], [1, 1]], dtype=np.float32)
    y = np.array([0, 1, 1])
    unique, counts, index, summary = census(x, y)
    np.testing.assert_array_equal(unique[index], x)
    np.testing.assert_array_equal(counts, [[1, 1], [0, 1]])
    assert summary["mixed"] == 1 and summary["originals_in_mixed"] == 2


def test_uri100_warm_start_keeps_predictions_and_resets_optimizer():
    weights = np.array([0.9, 1.1])
    objective = {
        "kind": "partial_binary_v1",
        "smoothing": 0.005,
        "family_weight": 0.0,
        "binary_class_weights": weights.tolist(),
    }
    base = WeightedSwiGLU(76, ARCH["width"], ARCH["core"], 12, objective=objective)
    base.steps = 55
    x = np.random.default_rng(4).random((9, 100), dtype=np.float32)
    arm = warm_start(base, 100, weights)
    assert arm.steps == 0 and not any(a.any() for a in arm.m.values())
    assert not arm.parameters["Win"][76:].any()
    np.testing.assert_allclose(arm.predict(x)[0], base.predict(x[:, :76])[0], atol=1e-7)
    assert sum(a.size for a in arm.parameters.values()) == ARCH["parameters"]

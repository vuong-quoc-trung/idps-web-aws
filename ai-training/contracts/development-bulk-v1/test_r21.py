import numpy as np
from r21_ablation import group_counts, overlap
from r21_quality import SCHEMES, advances, dual_cut, weight_ablation


def test_weight_changes_preserve_all_original_label_cells():
    counts = np.array([[6, 4], [8, 0], [0, 2], [3, 1]])
    expected_groups, expected_labels = np.nonzero(counts)
    score = np.array([0.4, 0.6, 0.99, 0.5])
    for scheme in SCHEMES:
        groups, labels, weight = weight_ablation(counts, score, scheme)
        np.testing.assert_array_equal(groups, expected_groups)
        np.testing.assert_array_equal(labels, expected_labels)
        assert np.all(weight > 0)
        benign, anomaly = np.bincount(labels, weights=weight)
        assert np.isclose(benign, anomaly) == (scheme != "class_mass_preserved")


def test_dropping_a_column_can_create_mixed_vectors_without_dropping_requests():
    x = np.array([[5], [5], [7]])
    counts = np.array([[3, 0], [0, 4], [5, 1]])
    unique, merged, inverse = group_counts(x, counts)
    np.testing.assert_array_equal(unique, [[5], [7]])
    np.testing.assert_array_equal(merged, [[3, 4], [5, 1]])
    np.testing.assert_array_equal(inverse, [0, 0, 1])
    assert dual_cut(merged, np.array([0.9, 0.1])) == 0.9


def test_projection_can_introduce_exact_and_bucket_overlap_across_roles():
    fit = np.array([[0.01, 1.0], [0.04, 2.0], [0.8, 3.0]], dtype=np.float32)
    tune = np.array([[0.01, 4.0]], dtype=np.float32)
    assert not overlap(fit, tune).any()
    np.testing.assert_array_equal(overlap(fit[:, :1], tune[:, :1]), [True, False, False])
    np.testing.assert_array_equal(
        overlap(np.floor(fit[:, :1] * 16), np.floor(tune[:, :1] * 16)),
        [True, True, False],
    )


def test_tuning_nomination_and_holdout_veto_use_both_estimands():
    def metrics(request_recall, vector_recall, vector_fpr=0.01):
        return {
            "original_request": {"recall": request_recall, "fpr": 0.009, "ap": 0.95},
            "vector_balanced": {"recall": vector_recall, "fpr": vector_fpr, "ap": 0.95},
        }

    reference = metrics(0.6, 0.64)
    assert advances(metrics(0.63, 0.64), reference, tuning=True)
    assert not advances(metrics(0.61, 0.64), reference, tuning=True)
    assert not advances(metrics(0.65, 0.63), reference, tuning=False)
    assert not advances(metrics(0.65, 0.67, 0.02), reference, tuning=False)

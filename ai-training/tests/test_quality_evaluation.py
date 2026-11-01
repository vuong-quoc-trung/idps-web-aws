import numpy as np


def test_grouped_metrics_keep_threshold_fixed_and_refuse_few_group_certainty():
    from idps_ai.training.generalization import grouped_binary_metrics

    report = grouped_binary_metrics(
        [0, 0, 1, 1], [0.8, 0.1, 0.9, 0.2], ["one", "one", "two", "two"], 0.5
    )
    assert report["metrics"]["fpr"] == report["metrics"]["recall"] == 0.5
    assert report["observed_groups"] == 2
    assert report["cluster_bootstrap_95pct"] is None
    assert report["threshold"] == 0.5
    assert report["threshold_fitted"] is False


def test_group_bootstrap_is_reproducible_and_counts_groups_not_rows():
    from idps_ai.training.generalization import grouped_binary_metrics

    y = np.tile([0, 1], 12)
    scores = np.tile([0.1, 0.8], 12)
    groups = np.repeat(np.arange(12), 2)
    a = grouped_binary_metrics(y, scores, groups, 0.5, replicates=100, seed=17)
    b = grouped_binary_metrics(y, scores, groups, 0.5, replicates=100, seed=17)
    assert a == b
    assert a["metrics"]["recall"] == 1.0 and a["metrics"]["fpr"] == 0
    assert a["cluster_bootstrap_95pct"]["recall"] == [1.0, 1.0]
    assert a["iid_wilson_FPR_95pct"][1] > 0
    assert a["independent_label_review"] is False

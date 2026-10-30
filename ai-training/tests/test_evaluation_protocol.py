import numpy as np


def test_grouped_calibration_and_selection_are_disjoint_and_never_read_test_labels(prepared):
    from idps_ai.training.protocol import evaluate_independent, validation_groups

    protocol = validation_groups(prepared)
    assert not set(protocol["calibration_groups"]) & set(protocol["selection_groups"])
    assert len(protocol["calibration_indices"]) + len(protocol["selection_indices"]) == len(
        protocol["groups"]
    )
    labels = np.array([0, 1] * ((len(protocol["groups"]) + 1) // 2))[: len(protocol["groups"])]
    scores = np.where(labels, 0.8, 0.2).astype(np.float32)
    report = evaluate_independent(labels, scores, None, protocol, bootstrap_repeats=20)
    assert report["test_labels_used"] is False
    assert report["selection"]["recall"] == 1
    assert report["selection"]["precision"] == 1
    assert report["calibration"]["fit_partition"] == "val_calibration_groups"
    assert report["selection"]["partition"] == "val_selection_groups"
    assert report["bootstrap"]["group_count"] == len(protocol["selection_groups"])

import numpy as np


def test_request_only_projection_marks_missing_without_fabricated_clock_or_actor():
    from idps_ai.training.generalization import missing_context_view

    columns = [
        "query_length",
        "role_ADMIN",
        "role_UNKNOWN",
        "authenticated",
        "status_missing",
        "flow_duration_seconds_missing",
        "ip_300s_count",
        "ip_300s_context_incomplete",
        "user_interarrival_missing",
    ]
    view = missing_context_view({"query_length": 12}, {"columns": columns})
    assert view == {
        "query_length": 12.0,
        "role_ADMIN": 0.0,
        "role_UNKNOWN": 1.0,
        "authenticated": 0.0,
        "status_missing": 1.0,
        "flow_duration_seconds_missing": 1.0,
        "ip_300s_count": 0.0,
        "ip_300s_context_incomplete": 1.0,
        "user_interarrival_missing": 1.0,
    }
    assert "timestamp" not in view


def test_binary_external_evaluation_never_tunes_threshold_or_invents_family():
    from idps_ai.training.generalization import binary_metrics

    r = binary_metrics(np.array([0, 0, 1, 1]), np.array([0.2, 0.8, 0.7, 0.9]), 0.75)
    assert r["confusion_matrix"] == [[1, 1], [1, 1]]
    assert r["fpr"] == 0.5 and r["recall"] == 0.5
    assert r["threshold"] == 0.75
    assert "families" not in r

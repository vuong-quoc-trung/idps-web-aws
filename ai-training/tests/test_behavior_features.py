import math

import pytest

from idps_ai.features.pipeline import FeatureExtractor, feature_columns


def test_behavior_dynamics_have_causal_hand_computed_values_and_versioned_width():
    extractor = FeatureExtractor(query_structure=True, behavior_dynamics=True)
    event = {
        "timestamp": 0.0,
        "client_key": "fixture-ip",
        "user_key": "fixture-user",
        "status_code": 401,
        "uri_path": "/api/auth/login",
        "http_method": "POST",
    }
    first = extractor.observe(event)
    extractor.observe(event | {"timestamp": 2.0})
    third = extractor.observe(
        event
        | {"timestamp": 6.0, "uri_path": "/api/classes", "http_method": "GET", "status_code": 200}
    )
    assert first["ip_interarrival_missing"] == 1
    assert third["ip_interarrival_log1p"] == pytest.approx(math.log1p(4))
    assert third["ip_interarrival_cv_60s"] == pytest.approx(1 / 3)
    assert third["ip_burst_10_to_60"] == 6
    assert third["ip_uri_transition"] == third["ip_method_transition"] == 1
    assert third["ip_auth_failure_acceleration"] == pytest.approx(2 / 10 - 2 / 60)
    earlier = dict(third)
    extractor.observe(event | {"timestamp": 9.0})
    assert third == earlier
    assert len(feature_columns(input_profile="safe_query_numeric_v2")) == 189
    assert (
        len(feature_columns(input_profile="safe_query_numeric_v2", behavior_dynamics=True)) == 207
    )

import pytest

from idps_ai.common import AI_ROOT, load_json
from idps_ai.features.pipeline import FeatureExtractor, fit_spec, transform


def test_hand_worked_golden_vectors_define_the_future_inference_port():
    fixture = load_json(AI_ROOT / "tests/fixtures/preprocessing_golden.json")
    extractor = FeatureExtractor()
    for event, expected in zip(fixture["events"], fixture["expected_subsets"]):
        actual = extractor.observe(event)
        for name, value in expected.items():
            assert actual[name] == pytest.approx(value)


def event(timestamp, status=200, path="/api/students", **updates):
    return {
        "timestamp": timestamp,
        "client_key": "ip-one",
        "user_key": "actor-one",
        "uri_path": path,
        "http_method": "GET",
        "status_code": status,
        "role": "STUDENT",
        "latency_ms": 10,
        "numeric_json": "{}",
        "flow_json": "{}",
        "suricata_alert_counts": [0, 0, 0],
        **updates,
    }


def test_windows_are_causal_and_count_the_current_observation_once():
    features = FeatureExtractor()
    first = features.observe(event(0))
    features.observe(event(5, 404, "/api/faculties"))
    third = features.observe(event(11, 401, "/api/auth/login"))
    assert first["ip_10s_count"] == 1
    assert third["ip_10s_count"] == 2
    assert third["ip_10s_error4_ratio"] == 1
    assert third["ip_60s_count"] == 3
    assert third["ip_60s_auth_failure_streak"] == 1
    features.observe(event(1000))
    assert third["ip_60s_count"] == 3
    with pytest.raises(ValueError, match="Late"):
        features.observe(event(900))


def test_scaler_fits_only_the_supplied_training_rows_and_freezes_column_order():
    spec = fit_spec(iter([{"a": 1.0, "b": 5.0}, {"a": 3.0, "b": 5.0}]), ["b", "a"])
    assert spec["columns"] == ["b", "a"]
    assert spec["mean"] == [5.0, 2.0]
    assert spec["std"] == [1.0, 1.0]
    assert transform(spec, {"a": 3.0, "b": 5.0}).tolist() == [0.0, 1.0]

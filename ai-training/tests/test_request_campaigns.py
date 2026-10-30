from idps_ai.data.request_campaigns import PAYLOADS, challenge_plan


def test_challenge_is_seeded_diverse_bounded_and_not_a_concurrent_calibration_split():
    first = challenge_plan(390017)
    assert first == challenge_plan(390017)
    assert first != challenge_plan(390018)
    assert {r["family"] for r in first} == set(PAYLOADS) | {
        "benign",
        "scanner_recon",
        "brute_force",
        "behavioral_anomaly",
    }
    assert all(r["target"].startswith("/api/") and len(r["target"]) < 2048 for r in first)
    assert first[0]["at_seconds"] == 0
    assert abs(first[-1]["at_seconds"] - 360) < 0.001
    assert sum(r["hard_negative"] for r in first) > 200


def test_eve_dual_projection_keeps_v5_semantics_and_never_writes_raw_query():
    import json

    from idps_ai.data.sensor_decode import redact_eve

    raw = {
        "event_type": "http",
        "http": {"url": "/api?term=1%27OR%201=1--&pwd=canary-secret", "http_method": "GET"},
    }
    old = redact_eve(json.loads(json.dumps(raw)), query_numeric=True, query_version=2)
    both = redact_eve(raw, query_numeric=True, query_version=2, request_structure=True)
    assert both["ai_query_numeric"] == old["ai_query_numeric"]
    assert both["ai_request_view"]["numbers"]["sql_line_comment_count"] == 1
    assert "canary" not in json.dumps(both)
    assert "term=" not in json.dumps(both)


def test_decoder_rejects_long_socket_path_before_creating_partial_artifacts(tmp_path):
    import pytest

    from idps_ai.data.sensor_decode import decode_pcap

    output = tmp_path / ("x" * 100)
    with pytest.raises(ValueError, match="socket path is too long"):
        decode_pcap(tmp_path / "absent.pcap", output, tmp_path / "runtime")
    assert not output.exists()

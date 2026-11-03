import json

import pytest
import yaml

from idps_ai.common import AI_ROOT


def test_full_v5_shadow_refuses_partial_or_pre_response_input_before_scoring():
    from idps_ai.inference import InferencePipeline

    pipeline = object.__new__(InferencePipeline)
    pipeline.spec = {"feature_version": "ai-features-5"}
    complete = {
        "request_key": "request-one",
        "sources": ["STUDENT_AUDIT", "NGINX", "SURICATA"],
        "correlation": "request_id",
        "status_code": 200,
        "latency_ms": 3.0,
        "request_bytes": 120.0,
        "response_bytes": 80.0,
        "numeric_json": json.dumps(
            {
                "uri_lexical_available": 1.0,
                "query_lexical_available": 1.0,
                "structure_available": 1.0,
            }
        ),
    }
    cases = [
        {**complete, "sources": ["STUDENT_AUDIT", "NGINX"]},
        {**complete, "correlation": "ambiguous_request_id"},
        {**complete, "status_code": None},
        {**complete, "latency_ms": None},
        {**complete, "numeric_json": "{}"},
        {**complete, "request_key": None},
    ]
    for row in cases:
        with pytest.raises(ValueError, match="inference"):
            pipeline.observe(row)
    pipeline._seen_request_keys = {"request-one"}
    with pytest.raises(ValueError, match="Duplicate fused request"):
        pipeline.observe(complete)  # Must reject before touching extractor or ONNX.


def test_shadow_replay_is_read_only_bounded_and_never_emits_payload_or_actions(prepared, tmp_path):
    from idps_ai.export.onnx import export_bundle
    from idps_ai.inference import shadow_replay
    from idps_ai.training.runner import train

    config = yaml.safe_load((AI_ROOT / "configs/scale_pilot_config.yaml").read_text())
    config["model"]["hidden_dim"] = 8
    train(prepared, tmp_path / "run", config, epochs=1, max_threads=1, max_duration_minutes=1)
    export_bundle(
        prepared,
        tmp_path / "run",
        tmp_path / "bundle",
        max_threads=1,
        evaluation_partition="val",
        independent_validation=True,
    )
    from idps_ai.common import load_json

    metrics = load_json(tmp_path / "bundle/evaluation.json")
    assert metrics["latency_ms"]["sample_partition"] == "val"
    assert metrics["final_test_metrics_computed"] is False
    report = shadow_replay(
        prepared, tmp_path / "bundle", tmp_path / "shadow", max_requests=5, max_threads=1
    )
    assert report["requests"] == 5
    assert report["mode"] == "offline_shadow_only"
    assert report["enforcement_actions"] == 0
    rows = [json.loads(s) for s in (tmp_path / "shadow/predictions.jsonl").read_text().splitlines()]
    assert len(rows) == 5
    assert all(
        set(r) <= {"event_key", "score", "above_threshold", "decision", "family_candidate"}
        for r in rows
    )
    assert all("query_string" not in r and "client_ip" not in r for r in rows)

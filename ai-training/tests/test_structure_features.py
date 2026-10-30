import json

import pytest

from idps_ai.data.query_numeric import project_query, validate_projection


def test_v2_projection_separates_numeric_structure_and_never_retains_encoded_secrets():
    url = "/api/faculties?q=1%2527%20OR%201%3D1%2F*test*%2F&%2574oken=CANARY_PASSWORD"
    projection = project_query(url, version=2)
    numbers = validate_projection(projection, version=2)
    assert numbers["structure_available"] == 1
    assert numbers["encoding_rounds"] == 2
    assert numbers["sql_comment_open_count"] == 1
    assert numbers["comparison_operator_count"] == 1
    assert "CANARY" not in json.dumps(projection)
    assert (
        project_query(url.replace("CANARY_PASSWORD", "OTHER_LONG_SECRET"), version=2) == projection
    )
    with pytest.raises(ValueError):
        validate_projection(projection, version=1)


def test_uri_encoding_is_observed_before_masking_while_credential_path_tail_is_removed():
    values = project_query("/api/..%252f..%252fetc%252fpasswd", version=2)["numbers"]
    assert values["encoding_rounds"] == 2 and values["path_parent_segment_count"] == 2
    a = project_query("/api/reset-password/CANARY_SHORT", version=2)
    b = project_query("/api/reset-password/CANARY_DIFFERENT_LONG_VALUE", version=2)
    assert a == b


def test_encoded_credential_path_separators_do_not_expose_secret_shape():
    for separator in ("/", "%2F", "%252F", "%5C", "%255C"):
        first = project_query("/api/reset-password" + separator + "CANARY_SHORT", version=2)
        second = project_query(
            "/api/reset-password" + separator + "DIFFERENT_LONG_VALUE", version=2
        )
        assert first == second
        assert first == project_query("/api", version=2)


def test_secret_only_query_is_unavailable_instead_of_looking_like_an_observed_empty_query():
    secret = project_query("/api/faculties?token=CANARY", version=2)["numbers"]
    empty = project_query("/api/faculties", version=2)["numbers"]
    assert secret["query_lexical_available"] == 0
    assert empty["query_lexical_available"] == 1
    assert secret["query_length"] == empty["query_length"] == 0


def test_expanded_gate_refuses_legacy_rows_without_structural_and_negative_holdouts(
    prepared, tmp_path
):
    from idps_ai.common import AI_ROOT
    from idps_ai.data.readiness import audit_readiness

    report = audit_readiness(
        prepared, tmp_path / "gate", "lab_capture", AI_ROOT / "configs/expanded_policy.yaml"
    )
    failed = {c["id"] for c in report["checks"] if not c["pass"]}
    assert {
        "structural_signal_variation",
        "numeric_projection_version",
        "train_hard_negative_holdout",
    }.issubset(failed)
    assert not report["offline_pilot_training_permitted"]


def test_expanded_readiness_reports_unprepared_data_instead_of_raising(prepared, tmp_path):
    from idps_ai.common import AI_ROOT
    from idps_ai.data.dataset import collect
    from idps_ai.data.readers import Input
    from idps_ai.data.readiness import audit_readiness

    raw = prepared.parent / "raw"
    collected = tmp_path / "collected"
    collect(
        [
            Input("student", raw / "student-audit.log"),
            Input("nginx", raw / "access.log"),
            Input("suricata", raw / "eve.json"),
        ],
        collected,
        (raw / "redaction.key").read_bytes(),
        raw / "labels.jsonl",
        input_profile="safe_query_numeric_v2",
    )
    report = audit_readiness(
        collected,
        tmp_path / "gate-collected",
        "lab_capture",
        AI_ROOT / "configs/expanded_policy.yaml",
    )
    assert report["status"] == "NOT_READY"
    assert any(c["id"] == "prepared_features" and not c["pass"] for c in report["checks"])


@pytest.mark.parametrize(
    "query,feature,expected",
    [
        ("q=%3Csvg%20onload%3Dalert%281%29%3E", "html_tag_open_count", 1),
        ("q=..%252f..%252fetc%252fpasswd", "path_parent_segment_count", 2),
        ("q=x%26%26id%3B%24%28whoami%29", "shell_substitution_count", 1),
        ("q=a%26%26id", "shell_and_count", 1),
    ],
)
def test_structure_counts_have_hand_worked_expected_values(query, feature, expected):
    assert project_query("/api/faculties?" + query, version=2)["numbers"][feature] == expected


def test_v41_collect_prepare_train_and_streaming_onnx_keep_one_feature_contract(tmp_path):
    import numpy as np
    import yaml

    from idps_ai.common import AI_ROOT, load_json
    from idps_ai.data.dataset import collect, iter_rows
    from idps_ai.data.query_numeric import project_file
    from idps_ai.data.readers import Input
    from idps_ai.data.split import prepare
    from idps_ai.data.synthetic import synthetic_s0
    from idps_ai.export.onnx import export_bundle
    from idps_ai.inference import InferencePipeline
    from idps_ai.training.runner import train

    raw = tmp_path / "raw"
    synthetic_s0(raw, campaigns=10, requests_per_campaign=16)
    records = [json.loads(s) for s in (raw / "eve.json").read_text().splitlines()]
    for r in records:
        h = r.get("http", {})
        if h.get("request_id"):
            h["response_headers"] = [{"name": "X-Request-Id", "value": h.pop("request_id")}]
    (raw / "eve.json").write_text("".join(json.dumps(r) + "\n" for r in records))
    project_file(str(raw / "eve.json"), str(tmp_path / "safe-eve.json"), version=2)
    collect(
        [
            Input("student", raw / "student-audit.log"),
            Input("nginx", raw / "access.log"),
            Input("suricata", tmp_path / "safe-eve.json"),
        ],
        tmp_path / "collected",
        (raw / "redaction.key").read_bytes(),
        raw / "labels.jsonl",
        input_profile="safe_query_numeric_v2",
    )
    m = prepare(tmp_path / "collected", tmp_path / "prepared")
    assert m["feature_count"] == 189 and m["normalizer_version"] == "ai-normalizer-4.1"
    spec = load_json(tmp_path / "prepared/feature_spec.json")
    assert spec["feature_version"] == "ai-features-4.1" and spec["query_projection"]["version"] == 2
    config = yaml.safe_load((AI_ROOT / "configs/gated_residual_config.yaml").read_text())
    config["model"]["hidden_dim"] = 16
    train(tmp_path / "prepared", tmp_path / "run", config, epochs=1, max_threads=1)
    bundle = export_bundle(
        tmp_path / "prepared",
        tmp_path / "run",
        tmp_path / "bundle",
        max_threads=1,
        evaluation_partition="val",
    )
    assert bundle["parity"]["all_rows_match"]
    expected = {r["event_key"]: r["x"] for r in iter_rows(tmp_path / "prepared/features.parquet")}
    for part in ("train", "val", "test"):
        stream = InferencePipeline(tmp_path / "bundle", max_threads=1)
        for r in iter_rows(tmp_path / "prepared/requests.parquet"):
            if r["split"] == part:
                result = stream.observe(r, include_features=True)
                if r["event_key"] in expected:
                    np.testing.assert_array_equal(
                        result["feature_vector"], expected[r["event_key"]]
                    )

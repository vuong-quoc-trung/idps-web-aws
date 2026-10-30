import json

import pytest

from idps_ai.data.readers import normalize_record
from idps_ai.data.sensor_decode import redact_eve


def eve(url):
    return {
        "timestamp": "2026-10-28T03:00:00Z",
        "event_type": "http",
        "src_ip": "127.0.0.10",
        "flow_id": 17,
        "http": {
            "url": url,
            "http_method": "GET",
            "status": 200,
            "request_headers": [{"name": "Cookie", "value": "CANARY_COOKIE"}],
            "response_headers": [{"name": "X-Request-Id", "value": "request-1"}],
        },
    }


def test_opt_in_eve_projection_keeps_numeric_signal_without_persisting_query_or_secrets():
    source = eve("/api/faculties?q=%3Cscript%3Efixture%3C%2Fscript%3E&password=CANARY_PASSWORD")
    safe = redact_eve(source, query_numeric=True)
    serialized = json.dumps(safe)
    assert "CANARY" not in serialized
    assert "fixture" not in serialized
    assert "%3C" not in serialized
    assert safe["http"]["url"] == "/api/faculties"
    normalized = normalize_record(
        "suricata", safe, b"k" * 32, "event-1", input_profile="safe_query_numeric_v1"
    )
    assert normalized["numeric"]["query_lexical_available"] == 1
    assert normalized["numeric"]["xss_tokens"] == 1
    assert normalized["numeric"]["query_length"] > 0


def test_numeric_bridge_counts_encoded_command_operators_after_secret_removal():
    from idps_ai.data.query_numeric import project_query

    value = project_query("/api/faculties?q=a%3Bwhoami%7C%24%28id%29&token=%3B%7C%24CANARY")
    assert value["numbers"]["semicolon"] == 1
    assert value["numbers"]["pipe"] == 1
    assert value["numbers"]["dollar"] == 1
    assert "CANARY" not in json.dumps(value)


def test_query_bridge_is_an_allowlist_and_does_not_retain_payload_or_arbitrary_headers():
    source = eve("/api/faculties?q=ordinary")
    source.update(payload="CANARY_BODY", packet="CANARY_PACKET", arbitrary="CANARY_EXTRA")
    source["alert"] = {"signature_id": 1000003, "signature": "CANARY_ALERT", "severity": 2}
    source["http"].update(hostname="CANARY_HOST", http_refer="CANARY_REFER")
    source["http"]["response_headers"][0]["extra"] = "CANARY_HEADER_EXTRA"
    safe = redact_eve(source, query_numeric=True)
    assert "CANARY" not in json.dumps(safe)
    assert safe["alert"] == {"signature_id": 1000003, "severity": 2}
    legacy = normalize_record(
        "suricata", safe, b"k" * 32, "event-1", input_profile="edge_masked_v1"
    )
    assert legacy["numeric"]["query_lexical_available"] == 0


def test_query_profile_fuses_real_request_signal_and_preserves_past_flow_availability(tmp_path):
    from idps_ai.data.dataset import collect, iter_rows
    from idps_ai.data.readers import Input

    flow = {
        "timestamp": "2026-10-28T03:01:05Z",
        "src_ip": "127.0.0.10",
        "event_type": "flow",
        "flow_id": 1,
        "flow": {
            "start": "2026-10-28T03:00:00Z",
            "end": "2026-10-28T03:00:01Z",
            "bytes_toserver": 123,
            "bytes_toclient": 321,
            "pkts_toserver": 3,
            "pkts_toclient": 4,
        },
    }
    rows = [flow]
    for second in (65, 66):
        value = eve("/api/faculties?q=%3Cscript%3Eprobe%3C/script%3E")
        value["timestamp"] = f"2026-10-28T03:01:{second - 60:02d}Z"
        value["http"]["response_headers"][0]["value"] = f"request-{second}"
        rows.append(redact_eve(value, query_numeric=True))
    source = tmp_path / "eve.json"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    collect(
        [Input("suricata", source)],
        tmp_path / "data",
        b"k" * 32,
        input_profile="safe_query_numeric_v1",
    )
    requests = list(iter_rows(tmp_path / "data/requests.parquet"))
    assert json.loads(requests[0]["flow_json"])["bytes_to_server"] is None
    assert json.loads(requests[1]["flow_json"])["bytes_to_server"] == 123
    assert json.loads(requests[1]["numeric_json"])["xss_tokens"] == 1


def test_public_projection_cli_uses_the_same_numeric_contract_and_private_immutable_output(
    tmp_path,
):
    from idps_ai.cli import main

    source = tmp_path / "raw-eve.json"
    source.write_text(json.dumps(eve("/api/faculties?q=UNION%20SELECT%201&token=CANARY")) + "\n")
    target = tmp_path / "ai-eve.json"
    assert main(["project-eve", "--input", str(source), "--output", str(target)]) == 0
    assert target.stat().st_mode & 0o777 == 0o600
    value = json.loads(target.read_text())
    assert "CANARY" not in target.read_text() and "UNION" not in target.read_text()
    row = normalize_record(
        "suricata", value, b"k" * 32, "one", input_profile="safe_query_numeric_v1"
    )
    assert row["numeric"]["sqli_keywords"] == 2
    with pytest.raises(ValueError):
        from idps_ai.data.query_numeric import validate_projection

        projection = value["ai_query_numeric"]
        projection["numbers"]["sqli_keywords"] = float("nan")
        validate_projection(projection)


def test_prepare_versions_the_enriched_contract_without_changing_canonical_schema(tmp_path):
    from idps_ai.data.dataset import collect
    from idps_ai.data.query_numeric import project_file
    from idps_ai.data.readers import Input
    from idps_ai.data.split import prepare
    from idps_ai.data.synthetic import synthetic_s0

    raw = tmp_path / "raw"
    synthetic_s0(raw, campaigns=10, requests_per_campaign=16)
    # Approved fixture adapter uses an explicit ID. The numeric bridge trusts
    # the edge response header, matching real Suricata output instead.
    records = [json.loads(line) for line in (raw / "eve.json").read_text().splitlines()]
    for record in records:
        http = record.get("http", {})
        if http.get("request_id"):
            http["response_headers"] = [{"name": "X-Request-Id", "value": http.pop("request_id")}]
    (raw / "eve.json").write_text("".join(json.dumps(r) + "\n" for r in records))
    project_file(str(raw / "eve.json"), str(tmp_path / "eve-safe.json"))
    inputs = [
        Input("student", raw / "student-audit.log"),
        Input("nginx", raw / "access.log"),
        Input("suricata", tmp_path / "eve-safe.json"),
    ]
    collect(
        inputs,
        tmp_path / "data",
        (raw / "redaction.key").read_bytes(),
        raw / "labels.jsonl",
        input_profile="safe_query_numeric_v1",
    )
    manifest = prepare(tmp_path / "data", tmp_path / "prepared")
    spec = json.loads((tmp_path / "prepared/feature_spec.json").read_text())
    assert manifest["schema_version"] == "1.0"
    assert manifest["normalizer_version"] == "ai-normalizer-4"
    assert spec["feature_version"] == "ai-features-4"
    assert spec["query_projection"]["version"] == 1
    assert "ai-normalizer-4" in spec["input_contract"]
    assert len(spec["columns"]) == 148

    # End-to-end v4 serving uses the fitted spec, not a legacy hardcoded version.
    import numpy as np
    import yaml

    from idps_ai.common import AI_ROOT
    from idps_ai.data.dataset import iter_rows
    from idps_ai.export.onnx import export_bundle
    from idps_ai.inference import InferencePipeline
    from idps_ai.training.runner import train

    config = yaml.safe_load((AI_ROOT / "configs/weighted_residual_config.yaml").read_text())
    train(tmp_path / "prepared", tmp_path / "run", config, epochs=1, max_threads=1)
    bundle = export_bundle(
        tmp_path / "prepared", tmp_path / "run", tmp_path / "bundle", evaluation_partition="val"
    )
    assert bundle["parity"]["all_rows_match"] is True
    expected = {r["event_key"]: r["x"] for r in iter_rows(tmp_path / "prepared/features.parquet")}
    for partition in ("train", "val", "test"):
        online = InferencePipeline(tmp_path / "bundle", max_threads=1)
        for row in iter_rows(tmp_path / "prepared/requests.parquet"):
            if row["split"] != partition:
                continue
            actual = online.observe(row, include_features=True)
            if row["event_key"] in expected:
                np.testing.assert_array_equal(actual["feature_vector"], expected[row["event_key"]])


def test_stronger_gate_rejects_old_query_blind_and_repeated_plan_corpus(prepared, tmp_path):
    from idps_ai.common import AI_ROOT
    from idps_ai.data.readiness import audit_readiness

    report = audit_readiness(
        prepared, tmp_path / "gate", "lab_capture", AI_ROOT / "configs/query_numeric_policy.yaml"
    )
    failed = {c["id"] for c in report["checks"] if not c["pass"]}
    assert {
        "independent_campaign_plans",
        "train_query_projection",
        "val_payload_diversity",
        "test_benign_methods",
    }.issubset(failed)
    assert report["offline_pilot_training_permitted"] is False


@pytest.mark.parametrize("content", [b'{"secret":"CANARY"', b"[]\n", b"X" * 65537 + b"\n"])
def test_bridge_rejects_partial_malformed_or_oversized_records_without_publishing(
    content, tmp_path
):
    from idps_ai.data.query_numeric import project_file

    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(content)
    with pytest.raises(ValueError) as error:
        project_file(str(source), str(target))
    assert "CANARY" not in str(error.value)
    assert not target.exists()

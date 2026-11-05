"""Contract checks for the frozen, read-only MVP entry point."""

import json
from contextlib import contextmanager

import pytest

from idps_ai import mvp_inference
from idps_ai.common import PipelineError
from idps_ai.mvp_inference import (
    FLOW_KEYS,
    NUMERIC_COLUMNS,
    STRUCTURE_KEYS,
    ResearchMVP,
    validate_fused,
    validate_http,
)


def fused_record():
    numeric = {name: 0.0 for name in (*NUMERIC_COLUMNS, *STRUCTURE_KEYS)}
    numeric.update(uri_lexical_available=1.0, query_lexical_available=1.0, structure_available=1.0)
    return {
        "timestamp": 100.0,
        "available_at": 100.0,
        "request_key": "opaque-key",
        "client_key": "opaque-client",
        "user_key": None,
        "sources": ["STUDENT_AUDIT", "NGINX", "SURICATA"],
        "correlation": "request_id",
        "http_method": "GET",
        "uri_path": "/api/health",
        "role": "UNKNOWN",
        "user_agent": None,
        "status_code": 200,
        "latency_ms": 1.0,
        "request_bytes": 42.0,
        "response_bytes": 12.0,
        "numeric_json": json.dumps(numeric),
        "flow_json": json.dumps(dict.fromkeys(FLOW_KEYS)),
        "suricata_alert_counts": [0, 0, 0],
    }


def test_fused_contract_rejects_missing_source_and_numeric_feature():
    row = fused_record()
    validate_fused(row)
    row["sources"] = ["STUDENT_AUDIT", "NGINX"]
    with pytest.raises(PipelineError, match="three-source|correlated"):
        validate_fused(row)
    row["sources"] = ["STUDENT_AUDIT", "NGINX", "SURICATA", "SURICATA"]
    with pytest.raises(PipelineError, match="correlated"):
        validate_fused(row)
    row = fused_record()
    numeric = json.loads(row["numeric_json"])
    numeric.pop(next(iter(NUMERIC_COLUMNS)))
    row["numeric_json"] = json.dumps(numeric)
    with pytest.raises(PipelineError, match="numeric bridge"):
        validate_fused(row)


def test_fused_contract_requires_response_and_causal_flow_shape():
    row = fused_record()
    row["status_code"] = None
    with pytest.raises(PipelineError, match="response fields"):
        validate_fused(row)
    row = fused_record()
    row["flow_json"] = "{}"
    with pytest.raises(PipelineError, match="flow bridge"):
        validate_fused(row)


def test_request_contract_rejects_oversized_body_without_echoing_it():
    value = {"method": "POST", "url": "/api/test", "headers": None, "body": "SECRET" * 2000}
    with pytest.raises(PipelineError, match="oversized") as error:
        validate_http(value)
    assert "SECRET" not in str(error.value)


def test_unsupported_schema_and_selected_model_input_rejected():
    predictor = ResearchMVP.__new__(ResearchMVP)
    predictor.model = "request-v2"
    with pytest.raises(PipelineError, match="schema_version"):
        predictor.predict({"record_id": "a", "schema_version": "research-mvp-2"})
    with pytest.raises(PipelineError, match="requires http_request"):
        predictor.predict(
            {"record_id": "a", "schema_version": "research-mvp-1", "fused_request": {}}
        )


def test_duplicate_id_cannot_leave_partial_output(tmp_path, monkeypatch):
    @contextmanager
    def envelope(*_):
        class Guard:
            thermal_limit_reached = False

            def check(self):
                return False

        yield Guard(), {}

    class Predictor:
        def __init__(self, *_):
            pass

        def predict(self, record):
            return {"record_id": record["record_id"]}

    monkeypatch.setattr(mvp_inference, "resource_envelope", envelope)
    monkeypatch.setattr(mvp_inference, "ResearchMVP", Predictor)
    source = tmp_path / "input.jsonl"
    source.write_text('{"record_id":"same"}\n{"record_id":"same"}\n')
    output = tmp_path / "output.jsonl"
    with pytest.raises(PipelineError, match="Duplicate record_id at line 2"):
        mvp_inference.infer_jsonl(source, output)
    assert not output.exists()
    assert list(tmp_path.glob(".mvp-*")) == []


def test_existing_output_is_never_replaced(tmp_path):
    source = tmp_path / "input.jsonl"
    source.write_text('{"record_id":"a"}\n')
    output = tmp_path / "output.jsonl"
    output.write_text("protected")
    with pytest.raises(PipelineError, match="output must be a new"):
        mvp_inference.infer_jsonl(source, output)
    assert output.read_text() == "protected"


def test_disappearing_input_cleans_temporary_output(tmp_path, monkeypatch):
    @contextmanager
    def envelope(*_):
        yield object(), {}

    class Predictor:
        def __init__(self, *_):
            pass

    source = tmp_path / "input.jsonl"
    source.write_text('{"record_id":"a"}\n')
    output = tmp_path / "output.jsonl"
    original_open = type(source).open

    def missing(path, *args, **kwargs):
        if path == source:
            raise FileNotFoundError("source removed after preflight")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(mvp_inference, "resource_envelope", envelope)
    monkeypatch.setattr(mvp_inference, "ResearchMVP", Predictor)
    monkeypatch.setattr(type(source), "open", missing)
    with pytest.raises(FileNotFoundError):
        mvp_inference.infer_jsonl(source, output)
    assert not output.exists()
    assert list(tmp_path.glob(".mvp-*")) == []

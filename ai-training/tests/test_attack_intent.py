"""Semantic and privacy invariants for the attack-intent research derivative."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from idps_ai.common import digest
from idps_ai.data.attack_intent import (
    VERSION,
    collision_groups,
    dataset_fingerprint,
    normalize_label,
    raw_key,
    read_receipt,
    runtime_request,
    validate_eligible_splits,
    validate_record,
    vector_hash,
    visibility_bounds,
)


def record(intent="ATTACK_INTENT", outcome="UNSAFE_REFLECTION"):
    return dict(
        sample_id="one",
        dataset_version=VERSION,
        environment="lab",
        request_provenance={},
        workflow_group="work",
        session_group="session",
        campaign_group="campaign",
        intent=intent,
        outcome=outcome,
        evidence_levels=["APPLICATION_ORACLE_VERIFIED", "REVIEW_PENDING"],
        label_source="internal",
        review_status="PENDING",
        feature_compatibility={},
        split="TRAIN",
        checksums={"runtime_view": "same"},
        missingness={},
        inclusion_exclusion_reasons=[],
        oracle_verified=True,
        independent_human_verified=False,
        prior_exposure="exposed",
        eligible_for_fit=True,
    )


def test_failed_attempt_does_not_become_benign():
    assert normalize_label("ATTACK_ATTEMPT", "VERIFIED_FAILED_ATTEMPT", True) == (
        "ATTACK_INTENT",
        "VERIFIED_FAILED_ATTEMPT",
    )
    assert normalize_label("ATTACK_ATTEMPT", "UNKNOWN", False) == (
        "ATTACK_INTENT",
        "UNKNOWN_OUTCOME",
    )
    assert normalize_label("UNKNOWN", "VERIFIED_EXPLOIT_SUCCESS", True) == (
        "UNKNOWN_INTENT",
        "UNKNOWN_OUTCOME",
    )
    assert normalize_label("ATTACK_ATTEMPT", "UNSAFE_REFLECTION", True)[1] == "UNSAFE_REFLECTION"


def test_schema_rejects_fabricated_review_or_success():
    r = record()
    validate_record(r)
    r["evidence_levels"].append("HUMAN_REVIEWED")
    with pytest.raises(ValueError):
        validate_record(r)
    r = record()
    r["oracle_verified"] = False
    with pytest.raises(ValueError):
        validate_record(r)
    r = record("UNKNOWN_INTENT", "UNKNOWN_OUTCOME")
    with pytest.raises(ValueError):
        validate_record(r)


def test_projection_matches_actual_worker_and_never_retains_body_or_sessions():
    spec = importlib.util.spec_from_file_location(
        "actual_shadow", Path(__file__).parents[2] / "scripts/ai-shadow-worker.py"
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    headers = {
        "User-Agent": "Agent with colon: detail",
        "Accept": "application/json",
        "Content-Type": "-",
    }
    request = {
        "method": "POST",
        "url": "/api/login?q=%27OR+1=1",
        "headers": "cookie: private-canary\r\nAuthorization: Bearer private-canary\r\n"
        + "\r\n".join(f"{k}: {v}" for k, v in headers.items()),
        "body": "password=private-canary",
    }
    expected = worker.model_record(
        dict(headers=headers, method=request["method"], url=request["url"], request_id="a" * 32)
    )["http_request"]
    assert runtime_request(request) == expected
    assert "private-canary" not in str(expected)
    assert expected["url"] == request["url"] and expected["body"] is None


def test_body_only_intent_can_be_indistinguishable_at_runtime():
    request = {
        "method": "POST",
        "url": "/api/message",
        "headers": "Accept: application/json",
        "body": "message=hello",
    }
    attack = {**request, "body": "message=<script>alert(1)</script>"}
    assert runtime_request(request) == runtime_request(attack)
    assert raw_key(request) != raw_key(attack)
    rows = [record(), record("BENIGN_INTENT", "BENIGN_SUCCESS")]
    assert collision_groups(rows, "runtime_view") == [[0, 1]]
    assert vector_hash(np.ones(588, np.float32)) == vector_hash(np.ones(588, np.float64))


def test_fingerprint_order_stable_but_labels_roles_and_lineage_are_bound():
    a = record()
    b = {**record(), "sample_id": "two"}
    x = dataset_fingerprint([a, b], {"train": "sha"}, "plan")
    assert x == dataset_fingerprint([b, a], {"train": "sha"}, "plan")
    for key, value in [
        ("split", "CALIBRATION"),
        ("session_group", "different"),
        ("outcome", "UNKNOWN_OUTCOME"),
    ]:
        assert x != dataset_fingerprint([{**a, key: value}, b], {"train": "sha"}, "plan")


def test_receipt_tampering_fails(tmp_path):
    import json

    from idps_ai.common import file_sha256

    (tmp_path / "request-body.bin").write_text("fixture")
    (tmp_path / "response-body.bin").write_text("ok")
    for name, value in [("request-headers.json", {}), ("response-headers.json", [])]:
        (tmp_path / name).write_text(json.dumps(value))
    r = dict(
        request_id="id",
        method="POST",
        path="/api/test",
        request_body_sha256=file_sha256(tmp_path / "request-body.bin"),
        response_sha256=file_sha256(tmp_path / "response-body.bin"),
        request_headers_sha256=digest({}),
        response_headers_sha256=digest([]),
    )
    (tmp_path / "receipt.json").write_text(json.dumps(r))
    read_receipt(tmp_path, request_id="id")
    (tmp_path / "request-body.bin").write_text("tampered")
    with pytest.raises(ValueError):
        read_receipt(tmp_path, request_id="id")


def test_cross_role_session_leak_is_rejected_even_without_duplicate_payload():
    a = record()
    b = {**record(), "sample_id": "two", "split": "CALIBRATION"}
    a["checksums"] = {k: "a" for k in ["raw", "template", "full_view", "runtime_view"]}
    b["checksums"] = {k: "b" for k in ["raw", "template", "full_view", "runtime_view"]}
    with pytest.raises(ValueError):
        validate_eligible_splits([a, b])
    b["session_group"] = "new-session"
    b["campaign_group"] = "new-campaign"
    validate_eligible_splits([a, b])
    b["checksums"]["runtime_view"] = "a"
    with pytest.raises(ValueError):
        validate_eligible_splits([a, b])


def test_visibility_bound_does_not_pretend_training_recovers_missing_information():
    a = record()
    b = record("BENIGN_INTENT", "BENIGN_SUCCESS")
    bound = visibility_bounds([a, b])
    assert bound["unavoidable_label_errors_on_identical_views"] == 1
    assert bound["optimistic_max_attack_flags_at_budget"] == 0
    assert bound["allowed_false_flags"] == 0

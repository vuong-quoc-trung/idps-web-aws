#!/usr/bin/env python3
"""Synthetic adversarial contract checks. No real records/holdouts are accessed."""
import copy
import hashlib
import json
import platform
from pathlib import Path

from validate_contract import validate, validate_family

HERE = Path(__file__).resolve().parent
EARLY = "2026-11-13T10:00:00Z"
NOW = "2026-11-13T10:00:01Z"
LATE = "2026-11-13T10:00:02Z"


def h(value):
    return hashlib.sha256(("SYNTHETIC_FIXTURE:" + value).encode()).hexdigest()


def fixture(mask="NSA"):
    identity = h("request")
    events = [{"event_key": h(s), "source": s, "producer_instance": h(s + "producer"),
        "boot_scope": h("boot"), "event_time": EARLY, "received_at": EARLY,
        "available_at": EARLY, "event_kind": "APPLICATION_REQUEST" if s == "A" else "HTTP_TRANSACTION",
        "parse_status": "VALID", "edge_request_key": identity,
        "sensor_instance": h("sensor") if s == "S" else None,
        "flow_id": "18446744073709551615" if s == "S" else None,
        "tx_id": 0 if s == "S" else None, "payload_sha256": h(s + "payload"),
        "relation": "CURRENT_REQUEST"} for s in mask]
    edges = [{"left_event": events[0]["event_key"], "right_event": e["event_key"],
        "basis": "EDGE_RESPONSE_ID_SENSOR_TRANSACTION" if "S" in (events[0]["source"], e["source"]) else "TRUSTED_EDGE_REQUEST_ID",
        "proof_sha256": h("edge-proof"), "consistency": "MATCH"} for e in events[1:]]
    feature = {"feature_id": "http.method", "state": "OBSERVED", "value": 1,
        "dependency_sources": [mask[0]], "event_refs": [h(mask[0])],
        "transform_sha256": h("method-map"), "input_profile": "synthetic-method-v1",
        "available_at": EARLY, "time_scope": "REQUEST_ONLY", "window_start": None,
        "window_end": None, "history_complete": None, "history_manifest_sha256": None}
    return {"schema_version": "idps-multisource-view-1.0.0", "record_id": h("record-" + mask),
        "record_kind": "REQUEST_VIEW", "namespace": {"deployment": h("deployment"), "capture": h("capture"), "key_domain": h("domain"), "environment": "LOCAL"},
        "identity": {"kind": "TRUSTED_EDGE_REQUEST", "key": identity, "assurance": "VERIFIED", "proof_refs": [h("trusted-proxy-proof")], "physical_request_verified": True},
        "revision": {"sequence": 0, "previous_record_sha256": None},
        "decision": {"phase": "POST_RESPONSE", "cutoff": NOW, "watermark": EARLY, "clock_uncertainty_ms": 1},
        "events": events,
        "source_observations": {s: {"presence": "PRESENT" if s in mask else "MISSING", "parse": "VALID" if s in mask else "UNKNOWN", "arrival": "ON_TIME" if s in mask else "UNKNOWN", "event_refs": [h(s)] if s in mask else [], "health": "UNKNOWN"} for s in "NSA"},
        "usable_source_mask": mask, "correlation": {"state": "VERIFIED" if len(mask) > 1 else "SINGLE_SOURCE", "edges": edges, "conflict": False},
        "content_origin": None, "features": [feature],
        "labels": [{"task": "ATTACK_INTENT", "target": 0, "family": None, "outcome": "BENIGN_WORKFLOW_VERIFIED", "basis": "SEMANTIC_ORACLE", "confidence_class": "SEMANTIC_SUPPORTED", "independent_review": "PENDING", "evidence_refs": [h("oracle-proof")], "assigned_at": LATE, "legacy_tier": "A"}],
        "lineage": {"original_role": "TRAIN", "exposure": "EXPOSED", "groups": [{"kind": "REQUEST", "key": identity, "key_domain": h("domain")}], "representation_sha256": h("representation"), "feature_view_sha256": h("view"), "canonical_sample_key": h("sample"), "parent_sample_key": None, "variant": "NATIVE", "protected": False},
        "admission": {"state": "REVERIFY", "permitted_tasks": [], "reasons": ["SYNTHETIC_NOT_DATA"]},
        "privacy": {"raw_payload_persisted": False, "identity_features_allowed": False, "projection_sha256": h("privacy")}}


def content_fixture():
    r = fixture("N")
    r.update(record_kind="CONTENT_VIEW", events=[], usable_source_mask="NONE",
        content_origin={"source_asset_id": "synthetic-publisher", "source_sha256": h("asset"), "source_coordinate": 0, "representation_sha256": h("representation")},
        correlation={"state": "NOT_APPLICABLE", "edges": [], "conflict": False})
    r["namespace"]["environment"] = "EXTERNAL_DATASET"
    r["identity"].update(kind="CONTENT_COORDINATE", physical_request_verified=False)
    r["decision"].update(phase="OFFLINE_CONTENT", cutoff=None, watermark=None, clock_uncertainty_ms=None)
    for s in r["source_observations"].values():
        s.update(presence="UNSUPPORTED", parse="NOT_APPLICABLE", arrival="NOT_APPLICABLE", event_refs=[])
    r["features"][0].update(dependency_sources=[], event_refs=[], available_at=None, time_scope="CONTENT_ONLY")
    r["labels"][0].update(task="PUBLISHER_ANOMALY", basis="PUBLISHER", confidence_class="PUBLISHER_ONLY", outcome="UNKNOWN", legacy_tier="SILVER")
    return r


def main():
    checks = []

    def check(name, record, expected=None):
        errors = validate(record)
        ok = expected in errors if expected else not errors
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "expected_rejection": expected, "actual_errors": errors})

    def reject(name, edit, code, base=None):
        r = copy.deepcopy(base if base is not None else fixture())
        edit(r)
        check(name, r, code)

    for mask in ["N", "S", "A", "NS", "NA", "SA", "NSA"]:
        check("native_mask_" + mask, fixture(mask))
    check("content_without_fake_N", content_fixture())
    r = fixture("N")
    r["features"][0].update(state="MISSING", value=None, event_refs=[], dependency_sources=[], available_at=None)
    check("missing_field_null", r)
    r = fixture("N")
    r["features"][0].update(feature_id="http.body_syntax46", state="EMPTY", value=[0.0] * 46)
    check("observed_empty_body_separate_from_missing", r)
    r = fixture("NS")
    r["events"][1]["available_at"] = LATE
    r["source_observations"]["S"]["arrival"] = "LATE"
    r["usable_source_mask"] = "N"
    check("late_source_retained_not_used", r)
    r = fixture("NS")
    r["events"][1]["parse_status"] = "PARSE_ERROR"
    r["source_observations"]["S"]["parse"] = "PARSE_ERROR"
    r["usable_source_mask"] = "N"
    check("parse_error_source_not_used", r)
    r = fixture()
    r.update(features=[], usable_source_mask="NONE")
    r["correlation"].update(state="AMBIGUOUS", conflict=True)
    check("ambiguous_quarantine_abstains", r)
    r = fixture("S")
    r["identity"].update(kind="SENSOR_TRANSACTION", key=h("sensor-tuple"))
    check("sensor_transaction_single_source", r)
    r = fixture("A")
    r["identity"].update(kind="SOURCE_EVENT", key=h("A"), physical_request_verified=False, assurance="UNVERIFIED", proof_refs=[])
    check("event_only_does_not_claim_physical_request", r)
    r = fixture()
    r["revision"].update(sequence=1, previous_record_sha256=h("previous"))
    check("late_revision_keeps_canonical_sample", r)
    r = fixture()
    r["features"] = []
    r["decision"]["clock_uncertainty_ms"] = None
    r["usable_source_mask"] = "NONE"
    check("unknown_clock_abstains", r)
    reject("late_source_mask", lambda r: r["events"][1].update(available_at=LATE), "SOURCE_MASK")
    reject("feature_after_cutoff", lambda r: r["features"][0].update(available_at=LATE), "FUTURE_FEATURE")
    reject("availability_before_receipt", lambda r: r["events"][0].update(received_at=NOW), "EVENT_BEFORE_RECEIPT")
    reject("feature_before_input", lambda r: r["events"][0].update(available_at=NOW), "FEATURE_BEFORE_INPUT")
    reject("duplicate_event", lambda r: r["events"].append(copy.deepcopy(r["events"][0])), "DUPLICATE_EVENT")
    reject("disconnected_join", lambda r: r["correlation"].update(edges=[]), "DISCONNECTED_CORRELATION")
    reject("wrong_request_join", lambda r: r["events"][1].update(edge_request_key=h("other")), "FALSE_CORRELATION")
    reject("sensor_without_tx", lambda r: r["events"][1].update(tx_id=None), "SENSOR_TX_MISSING")
    reject("IP_time_join_disallowed", lambda r: r["correlation"]["edges"][0].update(basis="IP_TIME"), "SCHEMA_INVALID")
    reject("ambiguous_fused_feature", lambda r: r["correlation"].update(state="AMBIGUOUS"), "UNCERTIFIED_FUSED_FEATURES")
    reject("field_from_unobserved_source", lambda r: r["features"][0].update(dependency_sources=["A"]), "FEATURE_SOURCE_MASK", fixture("N"))
    reject("missing_value_fabricated", lambda r: r["features"][0].update(state="MISSING", value=0), "UNOBSERVED_VALUE")
    reject("truncated_value_fabricated", lambda r: r["features"][0].update(state="TRUNCATED", value=0), "UNOBSERVED_VALUE")
    reject("NaN_value", lambda r: r["features"][0].update(value=float("nan")), "NONFINITE_VALUE")
    reject("encoder_width", lambda r: r["features"][0].update(feature_id="http.rich512", value=[0.0]), "FEATURE_WIDTH_OR_VALUE")
    reject("future_watermark", lambda r: r["decision"].update(watermark=LATE), "FUTURE_WATERMARK")
    reject("response_in_pre_response", lambda r: r["features"][0].update(feature_id="http.status_code", value=200), "RESPONSE_BEFORE_RESPONSE")
    reject("current_flow_total", lambda r: r["features"][0].update(feature_id="sensor.completed_flow5", dependency_sources=["S"], event_refs=[h("S")], value=[0]*5), "CURRENT_FLOW_LEAKAGE")
    reject("count_without_history", lambda r: r["features"][0].update(feature_id="context.request_count_10s", value=2), "CONTEXT_WITHOUT_WINDOW")
    reject("publisher_as_intent", lambda r: r["labels"][0].update(basis="PUBLISHER"), "WEAK_LABEL_AS_INTENT")
    reject("scenario_confidence_not_ground_truth", lambda r: r["labels"][0].update(basis="SCENARIO"), "WEAK_LABEL_AS_INTENT")
    reject("unlabeled_is_not_benign", lambda r: r["labels"][0].update(task="UNLABELED", basis="NONE", confidence_class="UNKNOWN"), "UNLABELED_TARGET")
    reject("claimed_review_not_verified", lambda r: r["labels"][0].update(basis="INDEPENDENT_REVIEW"), "REVIEW_UNVERIFIED")
    reject("test_role_unprotected", lambda r: r["lineage"].update(original_role="TEST"), "PROTECTED_ROLE")
    def protected_admission(r):
        r["lineage"].update(original_role="CALIBRATION", protected=True)
        r["admission"].update(state="ELIGIBLE_FOR_DECLARED_TASK", permitted_tasks=["ATTACK_INTENT"], reasons=[])
    reject("protected_role_fit", protected_admission, "PROTECTED_ADMISSION")
    reject("dropout_new_sample", lambda r: r["lineage"].update(variant="SOURCE_DROPOUT", parent_sample_key=h("other")), "DROPOUT_CAPACITY_INFLATION")
    reject("unmapped_HMAC_domain", lambda r: r["lineage"]["groups"][0].update(key_domain=h("other")), "LINEAGE_KEY_DOMAIN")
    reject("revision_without_previous", lambda r: r["revision"].update(sequence=1), "REVISION_PARENT")
    reject("raw_payload_injection", lambda r: r.update(raw_body="payload"), "SCHEMA_INVALID")
    reject("content_fakes_N", lambda r: r.update(usable_source_mask="N"), "SOURCE_MASK", content_fixture())
    a, b = fixture(), fixture("N")
    b["lineage"].update(variant="SOURCE_DROPOUT", parent_sample_key=h("sample"), original_role="TEST", protected=True)
    errors = validate_family([a, b])
    checks.append({"name": "variant_split_leakage", "status": "PASS" if "VARIANT_SPLIT_LEAKAGE" in errors else "FAIL", "expected_rejection": "VARIANT_SPLIT_LEAKAGE", "actual_errors": errors})
    result = {"schema_version": "t02-contract-checks-1", "scope": "Synthetic fixtures only; no runtime certification, evidence resolution or dataset admission", "python": platform.python_version(), "checks": checks, "passed": sum(x["status"] == "PASS" for x in checks), "failed": sum(x["status"] != "PASS" for x in checks)}
    (HERE / "contract-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "failed": result["failed"], "failures": [x for x in checks if x["status"] == "FAIL"]}))
    return int(result["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())

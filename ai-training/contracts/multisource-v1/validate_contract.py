#!/usr/bin/env python3
"""Reference validation for T02 specifications/fixtures, not a runtime adapter.

No datasets, applications, model modules or evidence payloads are loaded.
Digest references require a separate trust/provenance audit before admission.
"""
import datetime as dt
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "data-contract.schema.json").read_text())
CATALOG = json.loads((HERE / "feature-provenance.json").read_text())
FEATURES = {x["id"]: x for x in CATALOG["features"]}
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
PROTECTED = {"CALIBRATION", "DEVELOPMENT", "TEST", "SEALED"}
REQUEST_KINDS = {"HTTP_TRANSACTION", "APPLICATION_REQUEST"}


def time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    return True


def validate(record):
    """Return stable error codes; success checks consistency, not truth of proofs."""
    errors = []

    def require(ok, code):
        if not ok:
            errors.append(code)

    if not finite(record):
        return ["NONFINITE_VALUE"]
    if list(VALIDATOR.iter_errors(record)):
        return ["SCHEMA_INVALID"]
    r = record
    content = r["record_kind"] == "CONTENT_VIEW"
    cutoff = time(r["decision"]["cutoff"])
    watermark = time(r["decision"]["watermark"])
    events = {e["event_key"]: e for e in r["events"]}
    require(len(events) == len(r["events"]), "DUPLICATE_EVENT")
    current = {k: e for k, e in events.items() if e["relation"] == "CURRENT_REQUEST" and e["event_kind"] in REQUEST_KINDS}
    require(all(time(e["received_at"]) <= time(e["available_at"]) for e in events.values()), "EVENT_BEFORE_RECEIPT")
    require(not watermark or cutoff is not None and watermark <= cutoff, "FUTURE_WATERMARK")
    corr = r["correlation"]
    untrusted_fusion = corr["state"] in {"AMBIGUOUS", "UNVERIFIED"} or corr["conflict"]
    uncertified_clock = not content and r["decision"]["clock_uncertainty_ms"] is None
    usable = set()
    for source, state in r["source_observations"].items():
        expected_refs = {k for k, e in events.items() if e["source"] == source}
        require(set(state["event_refs"]) == expected_refs and len(state["event_refs"]) == len(expected_refs), "SOURCE_REFERENCES")
        if not expected_refs:
            require(state["presence"] != "PRESENT" and state["parse"] in {"UNKNOWN", "NOT_APPLICABLE"} and state["arrival"] in {"UNKNOWN", "NOT_APPLICABLE"}, "ABSENT_SOURCE_STATE")
            continue
        require(state["presence"] == "PRESENT", "PRESENT_SOURCE_STATE")
        parses = {events[k]["parse_status"] for k in expected_refs}
        require(state["parse"] == (next(iter(parses)) if len(parses) == 1 else "MIXED"), "SOURCE_PARSE_STATE")
        arrivals = {"ON_TIME" if cutoff and time(events[k]["available_at"]) <= cutoff else "LATE" for k in expected_refs}
        require(state["arrival"] == (next(iter(arrivals)) if len(arrivals) == 1 else "MIXED"), "SOURCE_ARRIVAL_STATE")
        if any(e["source"] == source and e["parse_status"] == "VALID" and cutoff and time(e["available_at"]) <= cutoff for e in current.values()):
            usable.add(source)
    if untrusted_fusion or uncertified_clock:
        usable = set()
        require(not r["features"], "UNCERTIFIED_FUSED_FEATURES")
    expected_mask = "".join(s for s in "NSA" if s in usable) or "NONE"
    require(r["usable_source_mask"] == expected_mask, "SOURCE_MASK")

    identity = r["identity"]
    require(identity["assurance"] != "VERIFIED" or bool(identity["proof_refs"]), "IDENTITY_PROOF_MISSING")
    if identity["physical_request_verified"]:
        require(identity["assurance"] == "VERIFIED" and identity["kind"] in {"TRUSTED_EDGE_REQUEST", "SENSOR_TRANSACTION"}, "PHYSICAL_IDENTITY")
        require(all(all(e[k] is not None for k in ("sensor_instance", "flow_id", "tx_id")) for e in current.values() if e["source"] == "S"), "SENSOR_TX_MISSING")
    if identity["kind"] == "TRUSTED_EDGE_REQUEST":
        require(bool(current) and all(e["edge_request_key"] == identity["key"] for e in current.values()), "EDGE_ID_MISMATCH")
    if identity["kind"] == "SENSOR_TRANSACTION":
        tuples = {(e["sensor_instance"], e["boot_scope"], e["flow_id"], e["tx_id"]) for e in current.values()}
        require(bool(current) and all(e["source"] == "S" for e in current.values()) and len(tuples) == 1 and all(v is not None for v in next(iter(tuples), (None,))), "SENSOR_IDENTITY")
    if identity["kind"] == "SOURCE_EVENT":
        require(len(current) == 1 and identity["key"] in current and not identity["physical_request_verified"], "SOURCE_EVENT_IDENTITY")

    graph = {k: set() for k in current}
    for edge in corr["edges"]:
        a, b = edge["left_event"], edge["right_event"]
        if a not in current or b not in current or a == b:
            errors.append("CORRELATION_REFERENCES")
            continue
        left, right = current[a], current[b]
        require(left["edge_request_key"] is not None and left["edge_request_key"] == right["edge_request_key"], "FALSE_CORRELATION")
        if "S" in {left["source"], right["source"]}:
            require(edge["basis"] == "EDGE_RESPONSE_ID_SENSOR_TRANSACTION", "SENSOR_EDGE_BASIS")
            for e in (left, right):
                if e["source"] == "S":
                    require(all(e[k] is not None for k in ("sensor_instance", "flow_id", "tx_id")), "SENSOR_TX_MISSING")
        require(edge["consistency"] != "CONFLICT" or corr["conflict"], "HIDDEN_CORRELATION_CONFLICT")
        if edge["consistency"] != "CONFLICT":
            graph[a].add(b)
            graph[b].add(a)
    if len({e["source"] for e in current.values()}) > 1 and not untrusted_fusion:
        require(corr["state"] == "VERIFIED" and identity["assurance"] == "VERIFIED", "MULTISOURCE_NOT_VERIFIED")
        seen, pending = set(), [next(iter(current))]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(graph[node] - seen)
        require(seen == set(current), "DISCONNECTED_CORRELATION")
    elif not content and not untrusted_fusion:
        require(corr["state"] == "SINGLE_SOURCE", "SINGLE_SOURCE_STATE")

    if content:
        require(not events and r["content_origin"] is not None and identity["kind"] == "CONTENT_COORDINATE" and not identity["physical_request_verified"], "CONTENT_HAS_NATIVE_IDENTITY")
        require(r["decision"]["phase"] == "OFFLINE_CONTENT" and cutoff is None and watermark is None and corr["state"] == "NOT_APPLICABLE" and not corr["edges"], "CONTENT_DECISION")
    else:
        require(cutoff is not None and r["decision"]["phase"] != "OFFLINE_CONTENT" and r["content_origin"] is None and identity["kind"] != "CONTENT_COORDINATE", "REQUEST_DECISION")
    rev = r["revision"]
    require((rev["sequence"] == 0) == (rev["previous_record_sha256"] is None), "REVISION_PARENT")

    require(len({f["feature_id"] for f in r["features"]}) == len(r["features"]), "DUPLICATE_FEATURE")
    for f in r["features"]:
        spec = FEATURES[f["feature_id"]]
        refs = set(f["event_refs"])
        require(refs <= events.keys() and len(refs) == len(f["event_refs"]), "FEATURE_REFERENCES")
        deps = set(f["dependency_sources"])
        require(len(deps) == len(f["dependency_sources"]) and deps <= set(spec["allowed_native_sources"]), "FEATURE_SOURCE_UNSUPPORTED")
        observed = f["state"] in {"OBSERVED", "EMPTY"}
        if not observed:
            require(f["value"] is None, "UNOBSERVED_VALUE")
            continue
        v = f["value"]
        require(v is not None and (not isinstance(v, list) if spec["width"] == 1 else isinstance(v, list) and len(v) == spec["width"]), "FEATURE_WIDTH_OR_VALUE")
        if f["feature_id"] in CATALOG["enum_codes"]:
            require(type(v) is int and v in CATALOG["enum_codes"][f["feature_id"]].values(), "FEATURE_ENUM")
        elif f["feature_id"] == "audit.authenticated":
            require(type(v) is bool, "FEATURE_BOOL")
        else:
            require(not isinstance(v, bool), "FEATURE_NUMBER")
        if f["state"] == "EMPTY":
            require(f["feature_id"] == "http.body_syntax46", "EMPTY_SEMANTICS")
        if content:
            require(f["feature_id"].startswith("http.") and f["time_scope"] == "CONTENT_ONLY" and not deps and not refs and f["available_at"] is None, "CONTENT_PROVENANCE")
            continue
        require(bool(deps) and deps <= usable and refs <= events.keys() and {events[k]["source"] for k in refs if k in events} <= deps, "FEATURE_SOURCE_MASK")
        available = time(f["available_at"])
        require(available is not None and cutoff is not None and available <= cutoff, "FUTURE_FEATURE")
        require(all(events[k]["parse_status"] == "VALID" and available and time(events[k]["available_at"]) <= available for k in refs if k in events), "FEATURE_BEFORE_INPUT")
        windowed = f["time_scope"] in {"PRIOR_COMPLETED_FLOW", "PRIOR_REQUEST_WINDOW"}
        if windowed:
            start, end = time(f["window_start"]), time(f["window_end"])
            require(start is not None and end is not None and cutoff is not None and start <= end < cutoff and f["history_manifest_sha256"] is not None and f["history_complete"] is not None, "INVALID_HISTORY")
            require(all(events[k]["relation"] == "PRIOR_CONTEXT" for k in refs if k in events), "CURRENT_AS_PRIOR_CONTEXT")
        else:
            require(bool(refs) and refs <= current.keys() and deps == {events[k]["source"] for k in refs if k in events}, "REQUEST_FEATURE_PROVENANCE")
            require(f["window_start"] is None and f["window_end"] is None and f["history_manifest_sha256"] is None and f["history_complete"] is None, "SPURIOUS_HISTORY")
        if f["feature_id"] in {"http.status_code", "http.latency_ms", "http.response_bytes"}:
            require(f["time_scope"] == "POST_RESPONSE" and r["decision"]["phase"] == "POST_RESPONSE", "RESPONSE_BEFORE_RESPONSE")
        if f["feature_id"] == "sensor.completed_flow5":
            require(f["time_scope"] == "PRIOR_COMPLETED_FLOW", "CURRENT_FLOW_LEAKAGE")
        if f["feature_id"].startswith("context."):
            require(f["time_scope"] == "PRIOR_REQUEST_WINDOW", "CONTEXT_WITHOUT_WINDOW")
        require(f["time_scope"] != "CONTENT_ONLY", "REQUEST_AS_CONTENT")

    supported = set()
    require(len({x["task"] for x in r["labels"]}) == len(r["labels"]), "DUPLICATE_LABEL_TASK")
    for label in r["labels"]:
        task, basis, target = label["task"], label["basis"], label["target"]
        if task == "UNLABELED":
            require(target is None and basis == "NONE" and label["confidence_class"] == "UNKNOWN" and label["family"] is None and label["outcome"] == "UNKNOWN", "UNLABELED_TARGET")
            continue
        if target is None:
            require(label["family"] is None, "UNKNOWN_TARGET_FAMILY")
            continue
        require(type(target) is int and bool(label["evidence_refs"]), "LABEL_EVIDENCE")
        if task == "ATTACK_INTENT":
            require(basis in {"SEMANTIC_ORACLE", "INDEPENDENT_REVIEW"} and label["confidence_class"] == "SEMANTIC_SUPPORTED", "WEAK_LABEL_AS_INTENT")
            require(basis != "INDEPENDENT_REVIEW" or label["independent_review"] == "VERIFIED", "REVIEW_UNVERIFIED")
        elif task == "PUBLISHER_ANOMALY":
            require(basis == "PUBLISHER" and label["confidence_class"] == "PUBLISHER_ONLY" and label["family"] is None and label["outcome"] == "UNKNOWN", "PUBLISHER_LABEL_SCOPE")
        else:
            require(basis in {"RULE", "TEACHER", "SCENARIO"} and label["confidence_class"] == "WEAK_PROXY" and label["family"] is None and label["outcome"] == "UNKNOWN", "PROXY_LABEL_SCOPE")
        require(target != 0 or label["family"] is None, "BENIGN_ATTACK_FAMILY")
        supported.add(task)
    lin, adm = r["lineage"], r["admission"]
    require(lin["original_role"] not in PROTECTED or lin["protected"], "PROTECTED_ROLE")
    require(all(g["key_domain"] == r["namespace"]["key_domain"] for g in lin["groups"]), "LINEAGE_KEY_DOMAIN")
    if lin["variant"] == "SOURCE_DROPOUT":
        require(not content and lin["parent_sample_key"] == lin["canonical_sample_key"], "DROPOUT_CAPACITY_INFLATION")
    else:
        require(lin["parent_sample_key"] is None, "NATIVE_HAS_PARENT")
    if adm["state"] == "ELIGIBLE_FOR_DECLARED_TASK":
        require(lin["original_role"] == "TRAIN" and not lin["protected"] and not adm["reasons"], "PROTECTED_ADMISSION")
        require(bool(adm["permitted_tasks"]) and set(adm["permitted_tasks"]) <= supported, "UNSUPPORTED_TASK_ADMISSION")
        if not content:
            require(identity["physical_request_verified"] and bool(usable) and not untrusted_fusion and not uncertified_clock, "UNVERIFIED_REQUEST_ADMISSION")
    else:
        require(not adm["permitted_tasks"], "INACTIVE_ADMISSION_TASKS")
    return sorted(set(errors))


def validate_family(records):
    """Small synthetic family check; not a global dataset overlap/admission scan."""
    errors = [e for r in records for e in validate(r)]
    by_key = {}
    for r in records:
        lin = r["lineage"]
        key = (r["namespace"]["key_domain"], lin["canonical_sample_key"])
        signature = (lin["original_role"], lin["protected"], lin["exposure"])
        if key in by_key and by_key[key] != signature:
            errors.append("VARIANT_SPLIT_LEAKAGE")
        by_key[key] = signature
    return sorted(set(errors))

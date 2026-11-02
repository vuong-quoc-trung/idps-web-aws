"""Unsigned, development-only observation of eight requests in the owned lab.

This path never approves semantic labels or enters the formal admission gate.
The separately signed gt-pilot-v1 profile remains unchanged.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.evidence_campaign import (
    _body_sha,
    _cases,
    _source_lines,
    _verify_sources,
    load_three_source_review_evidence,
    verify_capture,
)
from idps_ai.data.lab_capture import LabClient
from idps_ai.data.lab_runtime import verify_lab_cleanup
from idps_ai.data.pcap_http_evidence import _headers, _http_streams
from idps_ai.data.protocol_ground_truth import _execution_code_sha256, _target_code_identity, _utc
from idps_ai.data.snapshot import new_destination

PROFILE = "dev-oracle-observation-v1"
SOURCE = REPO_ROOT / "ai-training/src/idps_ai/data/dev_oracle_pilot.py"
CAMPAIGN_ID = "dev-oracle-00-00000385"
SOURCE_IP = "127.0.0.41"


def _code_sha256():
    return _execution_code_sha256() | {
        "ai-training/src/idps_ai/data/dev_oracle_pilot.py": file_sha256(SOURCE)
    }


def create_development_plan(output):
    """Seal exact bounded requests and execution code, without human approval claims."""
    cases = []
    for case in _cases(0, 901, "gt-pilot-v1"):
        cases.append(
            {
                "case_id": case["case_id"],
                "scenario": case["scenario"],
                "planned_intent": case["intent"],
                "attack_family": case["family"],
                "http_method": case["method"],
                "review_target": case["target"],
                "target_sha256": hashlib.sha256(case["target"].encode()).hexdigest(),
                "review_body": case.get("body"),
                "body_kind": case.get("body_kind"),
                "body_sha256": _body_sha(case),
            }
        )
    plan = {
        "format_version": 1,
        "case_profile": PROFILE,
        "purpose": "authorized_ai_owned_loopback_development_observation",
        "target": "127.0.0.1:18881",
        "collector_source_sha256": file_sha256(SOURCE),
        "execution_code_sha256": _code_sha256(),
        "target_code_identity": _target_code_identity(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaigns": [
            {
                "campaign_id": CAMPAIGN_ID,
                "seed": 901,
                "source_ip": SOURCE_IP,
                "partition": "development_review_only",
                "cases": cases,
            }
        ],
        "future_holdout": {
            "status": "RESERVED_NOT_GENERATED_OR_CAPTURED",
            "allow_for_tuning": False,
        },
        "label_policy": "No independent reviewer or signature. All intent labels UNKNOWN; factual request, response, three-source, and DB observations only. Formal admission 0.",
        "independent_review": False,
        "formal_training_permitted": False,
    }
    plan["plan_sha256"] = digest(plan)
    output = new_destination(output)
    output.mkdir(mode=0o700)
    atomic_json(output / "plan.json", plan)
    return plan


def verify_development_plan(plan_path, collector_source=SOURCE):
    plan_path = Path(plan_path)
    collector_source = Path(collector_source).resolve()
    plan = load_json(plan_path)
    checksum = plan.pop("plan_sha256", None)
    expected = _cases(0, 901, "gt-pilot-v1")
    if (
        checksum != digest(plan)
        or plan.get("case_profile") != PROFILE
        or plan.get("purpose") != "authorized_ai_owned_loopback_development_observation"
        or plan.get("target") != "127.0.0.1:18881"
        or collector_source != SOURCE.resolve()
        or plan.get("collector_source_sha256") != file_sha256(SOURCE)
        or plan.get("execution_code_sha256") != _code_sha256()
        or plan.get("target_code_identity") != _target_code_identity()
        or plan.get("independent_review") is not False
        or plan.get("formal_training_permitted") is not False
        or plan.get("future_holdout", {}).get("status") != "RESERVED_NOT_GENERATED_OR_CAPTURED"
        or len(plan.get("campaigns", [])) != 1
    ):
        raise PipelineError("Development observation plan or execution source changed")
    campaign = plan["campaigns"][0]
    if (
        campaign.get("campaign_id") != CAMPAIGN_ID
        or campaign.get("seed") != 901
        or campaign.get("source_ip") != SOURCE_IP
        or campaign.get("partition") != "development_review_only"
        or len(campaign.get("cases", [])) != len(expected) == 8
    ):
        raise PipelineError("Development observation scope changed")
    for recorded, case in zip(campaign["cases"], expected):
        if (
            recorded.get("case_id") != case["case_id"]
            or recorded.get("scenario") != case["scenario"]
            or recorded.get("planned_intent") != case["intent"]
            or recorded.get("attack_family") != case["family"]
            or recorded.get("http_method") != case["method"]
            or recorded.get("review_target") != case["target"]
            or recorded.get("target_sha256") != hashlib.sha256(case["target"].encode()).hexdigest()
            or recorded.get("review_body") != case.get("body")
            or recorded.get("body_kind") != case.get("body_kind")
            or recorded.get("body_sha256") != _body_sha(case)
        ):
            raise PipelineError("Development observed case differs from sealed plan")
    return plan, checksum


def collect_development_observation(plan_dir, lab_dir, output, collector_source):
    """Send only the sealed eight cases; retain all semantic labels as unknown."""
    plan_path = Path(plan_dir) / "plan.json"
    plan, plan_sha = verify_development_plan(plan_path, collector_source)
    lab = Path(lab_dir).resolve()
    marker = load_json(lab / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable" or marker.get("edge_port") != 18881:
        raise PipelineError("Development observation requires the owned loopback lab")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    preflight = {
        "status": "UNSIGNED_DEVELOPMENT_OBSERVATION_ONLY",
        "plan_sha256": plan_sha,
        "execution_code_sha256": plan["execution_code_sha256"],
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "independent_review": False,
        "formal_training_permitted": False,
    }
    atomic_json(output / "preflight.json", preflight)
    password = load_json(lab / "accounts-private.json")["password"]
    client = LabClient(18881, SOURCE_IP)
    observed = {}
    responses = []
    for case in _cases(0, 901, "gt-pilot-v1"):
        request_body = case.get("body")
        if case.get("body_kind") == "private_fixture_password":
            request_body = urlencode({"username": "ai_lab_00", "password": password})
        record, body = client.request(case["method"], case["target"], request_body)
        if case["case_id"] == "fixture_login" and record["status_code"] != 204:
            raise PipelineError(
                "Owned fixture login failed; partial development capture quarantined"
            )
        if case["case_id"] in ("csrf", "csrf_refresh"):
            try:
                csrf = json.loads(body)
                if not isinstance(csrf.get("token"), str) or not isinstance(
                    csrf.get("headerName"), str
                ):
                    raise ValueError
                client.csrf = csrf
            except (ValueError, AttributeError):
                raise PipelineError("Owned lab CSRF response invalid") from None
        if record["request_id"] in observed:
            raise PipelineError("Edge repeated a physical request ID")
        recorded = plan["campaigns"][0]["cases"][len(observed)]
        observed[record["request_id"]] = {
            "request_id": record["request_id"],
            "timestamp_utc": record["timestamp"],
            "campaign_id": CAMPAIGN_ID,
            "case_id": case["case_id"],
            "planned_intent": case["intent"],
            "planned_family": case["family"],
            "intent_label_from_plan": int(case["intent"] == "attack"),
            "http_method": case["method"],
            "status_code": record["status_code"],
            "target_sha256": recorded["target_sha256"],
            "plan_sha256": plan_sha,
            "exploit_outcome": "unknown",
            "_target": case["target"],
        }
        responses.append(
            {
                "request_id": record["request_id"],
                "case_id": case["case_id"],
                "status_code": record["status_code"],
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_bytes": len(body),
                "intent": "unknown",
                "exploit_outcome": "unknown",
            }
        )
        time.sleep(0.05)
    evidence = _verify_sources(lab, observed)
    ledger = output / "pending-evidence.jsonl"
    with ledger.open("x") as stream:
        for row in evidence:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    ledger.chmod(0o600)
    response_path = output / "response-evidence.jsonl"
    with response_path.open("x") as stream:
        for row in responses:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    response_path.chmod(0o600)
    report = {
        "format_version": 1,
        "status": "DEVELOPMENT_OBSERVATION_CAPTURED_NO_GROUND_TRUTH_LABELS",
        "plan_sha256": plan_sha,
        "plan_file_sha256": file_sha256(plan_path),
        "owned_lab_marker_sha256": file_sha256(lab / "owned-lab.json"),
        "preflight_sha256": file_sha256(output / "preflight.json"),
        "pending_evidence_sha256": file_sha256(ledger),
        "response_evidence_sha256": file_sha256(response_path),
        "observed_distinct_request_ids": len(evidence),
        "captured_nginx_and_student": len(evidence),
        "executed_development_campaigns": 1,
        "new_independently_reviewed_benign": 0,
        "new_independently_reviewed_attack": 0,
        "new_training_admission": 0,
        "formal_training_permitted": False,
        "independent_review": False,
    }
    atomic_json(output / "report.json", report)
    return report


def _verify_post_bytes(pcap, expected_rows, fixture_password):
    """Compare POST bytes in private PCAP in memory; never persist credentials."""
    expected = {row["request_id"]: row for row in expected_rows if row["http_method"] == "POST"}
    if len(expected) != 2:
        raise PipelineError("Development pilot needs exactly two observed POST bodies")
    cases = {case["case_id"]: case for case in _cases(0, 901, "gt-pilot-v1")}
    streams = _http_streams(pcap)
    matched = set()
    for direction, request_stream in streams.items():
        source_ip, source_port, dest_ip, dest_port = direction
        if dest_port != 18881 or source_ip != SOURCE_IP:
            continue
        reverse = (dest_ip, dest_port, source_ip, source_port)
        if reverse not in streams:
            raise PipelineError("Development POST lacks a packet-captured response")
        request_line, request_headers, body = _headers(request_stream)
        response_line, response_headers, _ = _headers(streams[reverse])
        ids = response_headers.get("x-request-id", [])
        if len(ids) != 1 or ids[0] not in expected:
            continue
        rid = ids[0]
        if rid in matched:
            raise PipelineError("Development POST response request ID repeated")
        row = expected[rid]
        case = cases[row["case_id"]]
        if (
            request_line != f"POST {case['target']} HTTP/1.1"
            or response_line.split(" ")[1] != str(row["status_code"])
            or request_headers.get("transfer-encoding")
            or len(request_headers.get("content-length", [])) != 1
        ):
            raise PipelineError("Development POST packet disagrees with captured request")
        try:
            length = int(request_headers["content-length"][0])
        except ValueError:
            raise PipelineError("Development POST content length is invalid") from None
        if length != len(body) or length > 512 * 1024:
            raise PipelineError("Development POST body is partial or oversized")
        if row["case_id"] == "fixture_login":
            wanted = urlencode({"username": "ai_lab_00", "password": fixture_password}).encode()
        elif row["case_id"] == "faculty_create":
            wanted = json.dumps(case["body"]).encode()
        else:
            raise PipelineError("Unrecognized development POST case")
        if body != wanted:
            raise PipelineError("Development POST body does not match sealed scenario")
        matched.add(rid)
    if matched != set(expected):
        raise PipelineError("Development POST body missing from private PCAP")
    return len(matched)


def verify_development_observation(plan_dir, run_dir, output):
    """Recheck physical evidence and DB state; approve no semantic intent labels."""
    run_dir = Path(run_dir).resolve()
    plan_dir = Path(plan_dir).resolve()
    plan, plan_sha = verify_development_plan(plan_dir / "plan.json")
    lab, capture, correlated = (run_dir / name for name in ("lab", "capture", "correlated"))
    verified = verify_capture(plan_dir, lab, capture, SOURCE)
    if verified["request_ids"] != 8:
        raise PipelineError("Development pilot did not send exactly eight requests")
    three_source = load_three_source_review_evidence(correlated, capture, 8)
    report = load_json(capture / "report.json")
    preflight_path = capture / "preflight.json"
    preflight = load_json(preflight_path)
    if (
        report.get("status") != "DEVELOPMENT_OBSERVATION_CAPTURED_NO_GROUND_TRUTH_LABELS"
        or report.get("preflight_sha256") != file_sha256(preflight_path)
        or report.get("independent_review") is not False
        or preflight.get("status") != "UNSIGNED_DEVELOPMENT_OBSERVATION_ONLY"
        or preflight.get("plan_sha256") != plan_sha
        or preflight.get("execution_code_sha256") != plan["execution_code_sha256"]
        or preflight.get("independent_review") is not False
    ):
        raise PipelineError("Unsigned development preflight or capture report changed")
    with (capture / "pending-evidence.jsonl").open() as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != 8 or len({row["request_id"] for row in rows}) != 8:
        raise PipelineError("Development capture has missing or duplicate requests")
    if any(_utc(row["timestamp_utc"]) <= _utc(preflight["verified_at_utc"]) for row in rows):
        raise PipelineError("Development request predates sealed preflight")
    response_path = capture / "response-evidence.jsonl"
    if report.get("response_evidence_sha256") != file_sha256(response_path):
        raise PipelineError("Development response ledger checksum changed")
    with response_path.open() as stream:
        responses = [json.loads(line) for line in stream]
    response_by_id = {row.get("request_id"): row for row in responses}
    if len(responses) != 8 or len(response_by_id) != 8:
        raise PipelineError("Development response ledger does not cover eight requests")
    for row in rows:
        response = response_by_id.get(row["request_id"])
        if (
            response is None
            or response.get("case_id") != row["case_id"]
            or response.get("status_code") != row["status_code"]
            or response.get("intent") != "unknown"
            or response.get("exploit_outcome") != "unknown"
            or not isinstance(response.get("body_bytes"), int)
            or not 0 <= response["body_bytes"] <= 512 * 1024
            or not isinstance(response.get("body_sha256"), str)
            or len(response["body_sha256"]) != 64
            or row["request_id"] not in three_source
        ):
            raise PipelineError("Response or three-source observation is incomplete")
    post_count = _verify_post_bytes(
        lab / "traffic.pcap", rows, load_json(lab / "accounts-private.json")["password"]
    )
    before_path, after_path = (
        run_dir / name for name in ("application-oracle-before.json", "application-oracle.json")
    )
    before, after = load_json(before_path), load_json(after_path)
    created = [row for row in rows if row["case_id"] == "faculty_create"]
    if len(created) != 1:
        raise PipelineError("Development DB oracle needs one protected mutation")
    create = created[0]
    student = _source_lines(lab / "student-audit.log", {create["request_id"]})
    if (
        len(student[create["request_id"]]) != 1
        or student[create["request_id"]][0][0].get("role") != "STAFF"
        or before.get("kind") != "ai_owned_dev_db_pre_capture_observation"
        or before.get("plan_sha256") != plan_sha
        or before.get("before_count") != 0
        or before.get("marker") != "GTPILOT01"
        or _utc(before.get("observed_at_utc")) >= _utc(create["timestamp_utc"])
        or after.get("kind") != "ai_owned_dev_db_state_transition"
        or after.get("capture_report_sha256") != file_sha256(capture / "report.json")
        or after.get("before_file_sha256") != file_sha256(before_path)
        or after.get("request_id") != create["request_id"]
        or after.get("marker") != "GTPILOT01"
        or after.get("after_count") != 1
        or after.get("observed_http_status_code") != 201
        or create["status_code"] != 201
        or _utc(after.get("observed_at_utc")) <= _utc(create["timestamp_utc"])
        or after.get("exploit_outcome") != "unknown"
    ):
        raise PipelineError("Development DB state transition is not objectively bound")
    cleanup = verify_lab_cleanup(lab)
    cleanup_path = run_dir / "cleanup-verification.json"
    if load_json(cleanup_path) != cleanup:
        raise PipelineError("Development disposable DB cleanup evidence changed")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    result = {
        "format_version": 1,
        "status": "EIGHT_REAL_REQUESTS_OBSERVED_DEVELOPMENT_ONLY_NO_INTENT_GROUND_TRUTH",
        "plan_sha256": plan_sha,
        "plan_file_sha256": file_sha256(plan_dir / "plan.json"),
        "capture_report_sha256": file_sha256(capture / "report.json"),
        "three_source_report_sha256": file_sha256(correlated / "report.json"),
        "response_evidence_sha256": file_sha256(response_path),
        "before_oracle_sha256": file_sha256(before_path),
        "after_oracle_sha256": file_sha256(after_path),
        "cleanup_verification_sha256": file_sha256(cleanup_path),
        "physical_requests_verified": 8,
        "three_source_correlated_requests": 8,
        "response_status_correlated_requests": 8,
        "post_bodies_verified_in_private_pcap": post_count,
        "protected_staff_mutation_db_transition_verified": 1,
        "machine_verified_attack_intent": 0,
        "machine_verified_benign_intent": 0,
        "intent_unknown": 8,
        "attack_exploit_outcome_verified": 0,
        "formal_training_admission": 0,
        "independent_review": False,
        "formal_training_permitted": False,
        "limits": "Three-source and DB facts are collector/lab observations. No independent semantic reviewer, signed protocol, attack outcome oracle, or independent evaluation environment. Runner intent remains untrusted.",
    }
    result["report_sha256"] = digest(result)
    atomic_json(output / "report.json", result)
    return result

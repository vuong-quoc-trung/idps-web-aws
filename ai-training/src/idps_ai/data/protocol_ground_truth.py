"""Prospective, signed scenario protocol matching; never formal admission.

The reviewer controls a private signing key outside this process. A valid
signature proves key possession, not the person's independence or the quality
of the protocol. Trust in the public key remains an operator decision.
"""

import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from idps_ai.common import (
    REPO_ROOT,
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.data.evidence_campaign import _body_sha, _cases, verify_blind_queue
from idps_ai.data.snapshot import new_destination

SLUG = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
EXECUTION_FILES = (
    "ai-training/scripts/evidence-lab-campaign.py",
    "ai-training/src/idps_ai/common.py",
    "ai-training/src/idps_ai/data/evidence_campaign.py",
    "ai-training/src/idps_ai/data/lab_capture.py",
    "ai-training/src/idps_ai/data/lab_runtime.py",
    "ai-training/src/idps_ai/data/protocol_ground_truth.py",
    "ai-training/src/idps_ai/data/sensor_decode.py",
    "ai-training/src/idps_ai/data/sensor_lab.py",
    "ai-training/src/idps_ai/data/snapshot.py",
    "ai-training/src/idps_ai/training/resources.py",
)


def _execution_code_sha256():
    return {name: file_sha256(REPO_ROOT / name) for name in EXECUTION_FILES}


def _target_code_identity():
    student_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD:student-web/backend"],
        cwd=REPO_ROOT,
        text=True,
        timeout=10,
    ).strip()
    return {
        "student_backend_git_tree": student_tree,
        "nginx_template_sha256": file_sha256(REPO_ROOT / "security-web/nginx/pbl4-proxy.conf"),
    }


def _utc(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise PipelineError("Protocol/approval timestamp must be timezone-aware") from None


def _pilot_plan(plan_path, *, require_current_collector=False):
    plan = load_json(plan_path)
    plan_sha = plan.pop("plan_sha256", None)
    if (
        plan_sha != digest(plan)
        or plan.get("case_profile") != "gt-pilot-v1"
        or plan.get("purpose") != "authorized_ai_owned_loopback_http_evidence"
        or plan.get("target") != "127.0.0.1:18881"
        or plan.get("future_holdout", {}).get("status") != "RESERVED_NOT_GENERATED_OR_CAPTURED"
        or len(plan.get("campaigns", [])) != 1
    ):
        raise PipelineError("Pre-capture protocol checksum is invalid")
    campaign = plan["campaigns"][0]
    if (
        campaign.get("partition") != "development_review_only"
        or campaign.get("source_ip") != "127.0.0.40"
        or type(campaign.get("seed")) is not int
        or campaign.get("campaign_id") != f"evidence-lab-00-{campaign.get('seed', -1):08x}"
    ):
        raise PipelineError("Pilot campaign scope differs from authorized loopback lab")
    actual_cases = campaign.get("cases", [])
    if len(actual_cases) != 8 or len({case.get("case_id") for case in actual_cases}) != 8:
        raise PipelineError("Approved protocol case list differs from bounded pilot")
    for actual in actual_cases:
        if (
            not isinstance(actual.get("review_target"), str)
            or not actual["review_target"].startswith("/api/")
            or actual.get("target_sha256")
            != hashlib.sha256(actual["review_target"].encode()).hexdigest()
            or actual.get("http_method") not in ("GET", "POST")
            or actual.get("planned_intent") not in ("benign", "attack")
            or (actual.get("planned_intent") == "attack")
            != (actual.get("attack_family") != "benign")
        ):
            raise PipelineError("Readable pilot protocol has inconsistent case evidence")
    if require_current_collector:
        source_path = REPO_ROOT / "ai-training/src/idps_ai/data/evidence_campaign.py"
        if plan.get("collector_source_sha256") != file_sha256(source_path):
            raise PipelineError("GT pilot collector code changed after plan creation")
        expected_cases = _cases(0, campaign["seed"], "gt-pilot-v1")
        for expected, actual in zip(expected_cases, actual_cases):
            if (
                actual.get("case_id") != expected["case_id"]
                or actual.get("scenario") != expected["scenario"]
                or actual.get("http_method") != expected["method"]
                or actual.get("planned_intent") != expected["intent"]
                or actual.get("attack_family") != expected["family"]
                or actual.get("review_target") != expected["target"]
                or actual.get("review_body") != expected.get("body")
                or actual.get("body_kind") != expected.get("body_kind")
                or actual.get("body_sha256") != _body_sha(expected)
            ):
                raise PipelineError("Readable pilot protocol differs from dispatched request")
    return plan, plan_sha


def verify_signed_protocol(
    plan_path, approval_path, trusted_public_key, *, require_current_collector=False
):
    """Require an external reviewer signature over the exact pre-capture plan."""
    plan_path, approval_path, trusted_public_key = map(
        Path, (plan_path, approval_path, trusted_public_key)
    )
    if not trusted_public_key.is_file() or trusted_public_key.is_symlink():
        raise PipelineError("A separately provisioned reviewer public key is required")
    plan, plan_sha = _pilot_plan(plan_path, require_current_collector=require_current_collector)
    approval = load_json(approval_path)
    signature_text = approval.pop("signature_base64", None)
    if (
        approval.get("format_version") != 1
        or approval.get("scope") != "authorized_ai_owned_lab_development_only"
        or approval.get("approved") is not True
        or approval.get("plan_sha256") != plan_sha
        or approval.get("plan_file_sha256") != file_sha256(plan_path)
        or approval.get("reviewer_public_key_sha256") != file_sha256(trusted_public_key)
        or approval.get("execution_code_sha256") != _execution_code_sha256()
        or approval.get("target_code_identity") != _target_code_identity()
        or not SLUG.fullmatch(str(approval.get("reviewer_id", "")))
        or not SLUG.fullmatch(str(approval.get("collector_id", "")))
        or approval["reviewer_id"] == approval["collector_id"]
        or approval["collector_id"] != "ai-lab-collector"
        or _utc(approval.get("approved_at_utc")) <= _utc(plan.get("created_at_utc"))
        or _utc(approval.get("approved_at_utc")) > datetime.now(timezone.utc)
    ):
        raise PipelineError("Independent pre-capture protocol approval is missing or mismatched")
    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (TypeError, ValueError, binascii.Error):
        raise PipelineError("Protocol approval signature is invalid") from None
    if len(signature) != 64:
        raise PipelineError("Protocol approval requires an Ed25519 signature")
    with tempfile.TemporaryDirectory(prefix="idps-gt-verify-") as temporary:
        message = Path(temporary) / "approval.json"
        signed = Path(temporary) / "approval.sig"
        message.write_bytes(canonical_bytes(approval))
        signed.write_bytes(signature)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(trusted_public_key.resolve()),
                "-rawin",
                "-in",
                str(message),
                "-sigfile",
                str(signed),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
    if result.returncode != 0:
        raise PipelineError("Reviewer signature does not verify against the trusted public key")
    return {
        "plan_sha256": plan_sha,
        "plan_file_sha256": file_sha256(plan_path),
        "approval_file_sha256": file_sha256(approval_path),
        "reviewer_public_key_sha256": file_sha256(trusted_public_key),
        "reviewer_id": approval["reviewer_id"],
        "collector_id": approval["collector_id"],
        "approved_at_utc": approval["approved_at_utc"],
        "trust_limit": "A signature proves possession of the separately supplied key; the operator must verify reviewer independence and protocol semantics.",
    }


def sign_protocol_in_private_terminal(
    plan_path, reviewer_id, private_key_path, trusted_public_key, output
):
    """Only the independent key holder may approve the readable pilot protocol."""
    if not sys.stdin.isatty() or not SLUG.fullmatch(reviewer_id):
        raise PipelineError("A real reviewer must sign from an interactive private terminal")
    plan_path, private_key_path, trusted_public_key = map(
        Path, (plan_path, private_key_path, trusted_public_key)
    )
    plan, plan_sha = _pilot_plan(plan_path, require_current_collector=True)
    if not trusted_public_key.is_file() or not private_key_path.is_file():
        raise PipelineError("Reviewer keypair is missing")
    print("Review every case in this private, readable plan before signing:")
    print(
        json.dumps(
            {
                "purpose": plan["purpose"],
                "target": plan["target"],
                "campaign_id": plan["campaigns"][0]["campaign_id"],
                "partition": plan["campaigns"][0]["partition"],
                "source_ip": plan["campaigns"][0]["source_ip"],
                "future_holdout": plan["future_holdout"]["status"],
            },
            sort_keys=True,
        )
    )
    for case in plan["campaigns"][0]["cases"]:
        print(
            json.dumps(
                {
                    "case_id": case["case_id"],
                    "intent": case["planned_intent"],
                    "family": case["attack_family"],
                    "method": case["http_method"],
                    "target": case["review_target"],
                    "body": case["review_body"],
                },
                sort_keys=True,
            )
        )
    print("Plan SHA256:", plan_sha)
    print("Execution source SHA256:", json.dumps(_execution_code_sha256(), sort_keys=True))
    print("Target code identity:", json.dumps(_target_code_identity(), sort_keys=True))
    if (
        input("Type I_APPROVE_EXACT_GT_PILOT_PLAN to sign: ").strip()
        != "I_APPROVE_EXACT_GT_PILOT_PLAN"
    ):
        raise PipelineError("Independent protocol approval not provided")
    approval = {
        "format_version": 1,
        "scope": "authorized_ai_owned_lab_development_only",
        "approved": True,
        "plan_sha256": plan_sha,
        "plan_file_sha256": file_sha256(plan_path),
        "reviewer_public_key_sha256": file_sha256(trusted_public_key),
        "execution_code_sha256": _execution_code_sha256(),
        "target_code_identity": _target_code_identity(),
        "reviewer_id": reviewer_id,
        "collector_id": "ai-lab-collector",
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output = new_destination(output)
    with tempfile.TemporaryDirectory(prefix="idps-gt-sign-", dir=output.parent) as temporary:
        message = Path(temporary) / "approval.json"
        signed = Path(temporary) / "approval.sig"
        message.write_bytes(canonical_bytes(approval))
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key_path.resolve()),
                "-rawin",
                "-in",
                str(message),
                "-out",
                str(signed),
            ],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise PipelineError("Reviewer signing key could not sign the protocol")
        approval["signature_base64"] = base64.b64encode(signed.read_bytes()).decode()
        candidate = Path(temporary) / "signed-approval.json"
        atomic_json(candidate, approval)
        verify_signed_protocol(
            plan_path, candidate, trusted_public_key, require_current_collector=True
        )
        atomic_json(output, approval)
        output.chmod(0o600)
    return {
        "status": "SIGNED_EXACT_PLAN_BY_EXTERNAL_KEY_HOLDER",
        "plan_sha256": plan_sha,
        "approval_file_sha256": file_sha256(output),
        "reviewer_id": reviewer_id,
        "trust_limit": "The operator must establish that the signing key holder is genuinely independent of the collector.",
    }


def verify_application_oracle(oracle_path, capture_report, create_request):
    """Validate a collector DB-state observation, never attack intent/outcome."""
    oracle_path = Path(oracle_path)
    oracle = load_json(oracle_path)
    before_path = oracle_path.parent / "application-oracle-before.json"
    before = load_json(before_path)
    capture = load_json(capture_report)
    if (
        oracle.get("format_version") != 1
        or oracle.get("kind") != "application_db_state_transition"
        or oracle.get("observer") != "ai_owned_lab_collector_read_only_query"
        or oracle.get("capture_report_sha256") != file_sha256(capture_report)
        or oracle.get("request_id") != create_request["request_id"]
        or oracle.get("marker") != "GTPILOT01"
        or oracle.get("before_file_sha256") != file_sha256(before_path)
        or oracle.get("before_count") != 0
        or oracle.get("after_count") != 1
        or oracle.get("observed_http_status_code") != 201
        or create_request.get("status_code") != 201
        or oracle.get("result") != "expected_benign_create_persisted"
        or oracle.get("attack_exploit_outcome") != "unknown"
        or _utc(oracle.get("observed_at_utc")) <= _utc(create_request["timestamp_utc"])
        or before.get("format_version") != 1
        or before.get("kind") != "ai_owned_lab_db_pre_capture_observation"
        or before.get("plan_sha256") != capture.get("plan_sha256")
        or before.get("approval_file_sha256")
        != (capture.get("pre_capture_approval") or {}).get("approval_file_sha256")
        or before.get("marker") != "GTPILOT01"
        or before.get("before_count") != 0
        or _utc(before.get("observed_at_utc")) >= _utc(create_request["timestamp_utc"])
    ):
        raise PipelineError("Application DB observation is incomplete or inconsistent")
    return {
        "request_id": create_request["request_id"],
        "oracle_file_sha256": file_sha256(oracle_path),
        "application_outcome": "collector_observed_benign_create_persisted",
        "attack_exploit_outcome": "unknown",
        "trust_limit": "Collector recorded DB query output; later file checks do not independently authenticate the database state.",
    }


def stage_protocol_matches(
    plan_dir,
    lab_dir,
    capture_dir,
    review_dir,
    collector_source,
    three_source_dir,
    approval_path,
    trusted_public_key,
    output,
    application_oracle_path=None,
):
    """Bind approved intent to actual GET captures, but leave formal gate unchanged."""
    plan_path = Path(plan_dir) / "plan.json"
    approval = verify_signed_protocol(plan_path, approval_path, trusted_public_key)
    checked = verify_blind_queue(
        plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir
    )
    plan = load_json(plan_path)
    cases = {
        (campaign["campaign_id"], item["case_id"]): item
        for campaign in plan["campaigns"]
        for item in campaign["cases"]
    }
    with (Path(capture_dir) / "pending-evidence.jsonl").open() as stream:
        observed = [json.loads(line) for line in stream]
    observed_cases = [(row.get("campaign_id"), row.get("case_id")) for row in observed]
    request_ids = [row.get("request_id") for row in observed]
    if (
        len(observed) != len(cases)
        or set(observed_cases) != set(cases)
        or len(set(observed_cases)) != len(observed_cases)
        or len(set(request_ids)) != len(request_ids)
    ):
        raise PipelineError("Approved protocol needs exactly one physical request per case")
    capture_report = load_json(Path(capture_dir) / "report.json")
    if capture_report.get("pre_capture_approval") != approval:
        raise PipelineError("Capture did not pin the signed protocol before dispatch")
    preflight_path = Path(capture_dir) / "preflight-approval.json"
    preflight = load_json(preflight_path)
    if (
        capture_report.get("pre_capture_approval_preflight_sha256") != file_sha256(preflight_path)
        or preflight.get("status") != "SIGNED_PROTOCOL_VERIFIED_BEFORE_REQUEST_DISPATCH"
        or preflight.get("approval_file_sha256") != approval["approval_file_sha256"]
    ):
        raise PipelineError("Signed protocol was not pinned before capture")
    if len(observed) != checked["requests"]:
        raise PipelineError("Approved protocol does not cover all captured requests")
    oracle = None
    if application_oracle_path is not None:
        created = [row for row in observed if row.get("case_id") == "faculty_create"]
        if len(created) != 1:
            raise PipelineError("Application oracle needs exactly one create request")
        oracle = verify_application_oracle(
            application_oracle_path, Path(capture_dir) / "report.json", created[0]
        )
    approval_time = _utc(approval["approved_at_utc"])
    preflight_time = _utc(preflight.get("verified_at_utc"))
    if preflight_time <= approval_time:
        raise PipelineError("Protocol preflight timestamp predates approval")
    for row in observed:
        case = cases.get((row.get("campaign_id"), row.get("case_id")))
        if (
            case is None
            or row.get("plan_sha256") != approval["plan_sha256"]
            or row.get("target_sha256") != case["target_sha256"]
            or row.get("http_method") != case["http_method"]
            or _utc(row.get("timestamp_utc")) <= approval_time
            or _utc(row.get("timestamp_utc")) <= preflight_time
        ):
            raise PipelineError("Observed request differs from approved pre-capture scenario")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    counts = Counter()
    capture_report_sha = file_sha256(Path(capture_dir) / "report.json")
    with (output / "protocol-matches.jsonl").open("x") as stream:
        for row in observed:
            case = cases.get((row.get("campaign_id"), row.get("case_id")))
            # The current capture does not bind POST body bytes to the signed
            # plan, including the login password. Never promote those intents.
            machine_verified = row["http_method"] in ("GET", "HEAD", "OPTIONS") and bool(
                three_source_dir
            )
            intent = case["planned_intent"] if machine_verified else "unknown"
            family = case["attack_family"] if machine_verified else None
            counts["requests"] += 1
            counts["machine_verified_benign"] += machine_verified and intent == "benign"
            counts["machine_verified_attack"] += machine_verified and intent == "attack"
            counts["unknown"] += not machine_verified
            application_outcome = (
                oracle["application_outcome"]
                if oracle and row["request_id"] == oracle["request_id"]
                else "unknown"
            )
            counts["application_state_observed_by_collector"] += application_outcome != "unknown"
            stream.write(
                json.dumps(
                    {
                        "request_id": row["request_id"],
                        "campaign_id": row["campaign_id"],
                        "case_id": row["case_id"],
                        "capture_report_sha256": capture_report_sha,
                        "protocol_approval_sha256": approval["approval_file_sha256"],
                        "intent_status": "MACHINE_VERIFIED_PROTOCOL_MATCH"
                        if machine_verified
                        else "UNKNOWN",
                        "intent": intent,
                        "attack_family": family,
                        "exploit_outcome": "unknown",
                        "application_outcome": application_outcome,
                        "formal_training_eligible": False,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    ledger = output / "protocol-matches.jsonl"
    ledger.chmod(0o600)
    report = {
        "format_version": 1,
        "status": "PROTOCOL_MATCH_STAGING_NOT_FORMAL_ADMISSION",
        "approval": approval,
        "capture_report_sha256": capture_report_sha,
        "review_queue_sha256": file_sha256(Path(review_dir) / "blind-review.jsonl"),
        "matches_sha256": file_sha256(ledger),
        "application_oracle_file_sha256": oracle["oracle_file_sha256"] if oracle else None,
        "counts": dict(counts),
        "formal_admission": 0,
        "limits": "Requires a genuinely independent reviewer key and pre-capture approval. GET intent is protocol-bound staging only. DB state is observed by the collector and not independently authenticated after cleanup. POST intent and attack exploit outcome remain unknown. Existing evidence-v2/human gate remains authoritative.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    return report

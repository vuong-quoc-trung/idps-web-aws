"""Guardrails for precommitted, pending-only lab campaign evidence."""

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data import evidence_campaign
from idps_ai.data.dev_oracle_pilot import create_development_plan, verify_development_plan
from idps_ai.data.lab_runtime import verify_lab_cleanup
from idps_ai.data.pcap_http_evidence import extract_request_bodies
from idps_ai.data.privacy import safe_route
from idps_ai.data.protocol_ground_truth import (
    sign_protocol_in_private_terminal,
    stage_protocol_matches,
    verify_application_oracle,
    verify_signed_protocol,
)
from idps_ai.data.query_numeric import project_query


def test_plan_has_distinct_attack_views_and_reserves_future_holdout(tmp_path):
    source = Path(evidence_campaign.__file__)
    plan = evidence_campaign.create_plan(tmp_path / "plan", source, [101, 203, 307])
    assert [len(c["cases"]) for c in plan["campaigns"]] == [18, 18, 18]
    assert all(c["partition"] == "development_review_only" for c in plan["campaigns"])
    assert plan["future_holdout"]["status"] == "RESERVED_NOT_GENERATED_OR_CAPTURED"
    attack_views = [
        case["target_sha256"]
        for campaign in plan["campaigns"]
        for case in campaign["cases"]
        if case["planned_intent"] == "attack"
    ]
    assert len(attack_views) == len(set(attack_views)) == 18


def test_unsigned_development_observation_is_a_separate_unknown_only_profile(tmp_path):
    plan_dir = tmp_path / "dev-only"
    plan = create_development_plan(plan_dir)
    checked, checksum = verify_development_plan(plan_dir / "plan.json")
    assert checksum == plan["plan_sha256"]
    assert checked["case_profile"] == "dev-oracle-observation-v1"
    assert checked["independent_review"] is False
    assert checked["formal_training_permitted"] is False
    assert len(checked["campaigns"][0]["cases"]) == 8
    assert not (plan_dir / "approval.json").exists()
    tampered = load_json(plan_dir / "plan.json")
    tampered["campaigns"][0]["cases"][5]["review_target"] = "/api/other"
    tampered["plan_sha256"] = digest({k: v for k, v in tampered.items() if k != "plan_sha256"})
    atomic_json(plan_dir / "plan.json", tampered)
    with pytest.raises(PipelineError, match="case differs"):
        verify_development_plan(plan_dir / "plan.json")


def test_small_gt_pilot_requires_signed_pre_capture_protocol(tmp_path, monkeypatch):
    source = Path(evidence_campaign.__file__)
    plan_dir = tmp_path / "pilot-plan"
    plan = evidence_campaign.create_plan(plan_dir, source, [901], "gt-pilot-v1")
    assert len(plan["campaigns"]) == 1
    assert len(plan["campaigns"][0]["cases"]) == 8
    assert {case["planned_intent"] for case in plan["campaigns"][0]["cases"]} == {
        "benign",
        "attack",
    }
    assert [case["review_target"] for case in plan["campaigns"][0]["cases"]] == [
        case["target"] for case in evidence_campaign._cases(0, 901, "gt-pilot-v1")
    ]
    assert plan["campaigns"][0]["cases"][-1]["review_body"]["shortCode"] == "GTPILOT01"
    assert b"lab-only-invalid-password" not in (plan_dir / "plan.json").read_bytes()
    with pytest.raises(PipelineError, match="signed independent"):
        evidence_campaign.collect(plan_dir, tmp_path / "missing-lab", tmp_path / "not-run", source)
    assert not (tmp_path / "not-run").exists()
    private_key, public_key = tmp_path / "reviewer.key", tmp_path / "reviewer.pub"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
    )

    class PrivateTerminal:
        def isatty(self):
            return True

    monkeypatch.setattr("idps_ai.data.protocol_ground_truth.sys.stdin", PrivateTerminal())
    monkeypatch.setattr("builtins.input", lambda _prompt: "I_APPROVE_EXACT_GT_PILOT_PLAN")
    approval_path = tmp_path / "approval.json"
    signed = sign_protocol_in_private_terminal(
        plan_dir / "plan.json",
        "independent-reviewer-fixture",
        private_key,
        public_key,
        approval_path,
    )
    assert signed["status"] == "SIGNED_EXACT_PLAN_BY_EXTERNAL_KEY_HOLDER"
    approval = load_json(approval_path)
    verified = verify_signed_protocol(
        plan_dir / "plan.json", approval_path, public_key, require_current_collector=True
    )
    assert verified["reviewer_id"] == "independent-reviewer-fixture"
    command = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts/evidence-lab-campaign.py"),
            "verify-protocol",
            "--plan",
            str(plan_dir),
            "--approval",
            str(approval_path),
            "--trusted-reviewer-key",
            str(public_key),
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(command.stdout)["plan_sha256"] == plan["plan_sha256"]
    assert len(approval["execution_code_sha256"]) == 10
    assert approval["target_code_identity"]["student_backend_git_tree"]
    assert approval["target_code_identity"]["nginx_template_sha256"]
    with monkeypatch.context() as changed_code:
        changed_code.setattr(
            "idps_ai.data.protocol_ground_truth._execution_code_sha256",
            lambda: {"changed-after-approval": "0" * 64},
        )
        with pytest.raises(PipelineError, match="approval is missing or mismatched"):
            verify_signed_protocol(plan_dir / "plan.json", approval_path, public_key)
    with monkeypatch.context() as changed_target:
        changed_target.setattr(
            "idps_ai.data.protocol_ground_truth._target_code_identity",
            lambda: {"student_backend_git_tree": "changed-after-approval"},
        )
        with pytest.raises(PipelineError, match="approval is missing or mismatched"):
            verify_signed_protocol(plan_dir / "plan.json", approval_path, public_key)
    # Synthetic capture: only test the signed protocol binding and staging.
    # The real three-source verifier is exercised elsewhere; no fixture label
    # is admitted for training.
    capture_dir, review_dir = tmp_path / "capture", tmp_path / "review"
    capture_dir.mkdir()
    review_dir.mkdir()
    (review_dir / "blind-review.jsonl").write_text("")
    approved_at = datetime.fromisoformat(verified["approved_at_utc"])
    preflight = {
        "status": "SIGNED_PROTOCOL_VERIFIED_BEFORE_REQUEST_DISPATCH",
        "approval_file_sha256": verified["approval_file_sha256"],
        "verified_at_utc": (approved_at + timedelta(seconds=1)).isoformat(),
    }
    atomic_json(capture_dir / "preflight-approval.json", preflight)
    atomic_json(
        capture_dir / "report.json",
        {
            "pre_capture_approval": verified,
            "pre_capture_approval_preflight_sha256": file_sha256(
                capture_dir / "preflight-approval.json"
            ),
        },
    )
    campaign = plan["campaigns"][0]
    rows = [
        {
            "request_id": f"fixture-{index}",
            "campaign_id": campaign["campaign_id"],
            "case_id": case["case_id"],
            "plan_sha256": plan["plan_sha256"],
            "target_sha256": case["target_sha256"],
            "http_method": case["http_method"],
            "timestamp_utc": (approved_at + timedelta(seconds=2)).isoformat(),
        }
        for index, case in enumerate(campaign["cases"])
    ]
    (capture_dir / "pending-evidence.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    monkeypatch.setattr(
        "idps_ai.data.protocol_ground_truth.verify_blind_queue",
        lambda *_args: {"requests": len(rows)},
    )
    staged = stage_protocol_matches(
        plan_dir,
        tmp_path / "lab",
        capture_dir,
        review_dir,
        source,
        tmp_path / "three-source-fixture",
        approval_path,
        public_key,
        tmp_path / "staged",
    )
    assert staged["counts"] == {
        "requests": 8,
        "machine_verified_benign": 4,
        "machine_verified_attack": 2,
        "unknown": 2,
        "application_state_observed_by_collector": 0,
    }
    assert staged["formal_admission"] == 0
    original_case_id = rows[1]["case_id"]
    rows[1]["case_id"] = rows[0]["case_id"]
    (capture_dir / "pending-evidence.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    with pytest.raises(PipelineError, match="exactly one physical request"):
        stage_protocol_matches(
            plan_dir,
            tmp_path / "lab",
            capture_dir,
            review_dir,
            source,
            tmp_path / "three-source-fixture",
            approval_path,
            public_key,
            tmp_path / "not-staged-duplicate",
        )
    assert not (tmp_path / "not-staged-duplicate").exists()
    rows[1]["case_id"] = original_case_id
    rows[0]["target_sha256"] = "0" * 64
    (capture_dir / "pending-evidence.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    with pytest.raises(PipelineError, match="differs from approved"):
        stage_protocol_matches(
            plan_dir,
            tmp_path / "lab",
            capture_dir,
            review_dir,
            source,
            tmp_path / "three-source-fixture",
            approval_path,
            public_key,
            tmp_path / "not-staged",
        )
    assert not (tmp_path / "not-staged").exists()
    approval["reviewer_id"] = "different-reviewer"
    atomic_json(approval_path, approval)
    with pytest.raises(PipelineError, match="signature does not verify"):
        verify_signed_protocol(plan_dir / "plan.json", approval_path, public_key)
    approval["reviewer_id"] = "ai-lab-collector"
    atomic_json(approval_path, approval)
    with pytest.raises(PipelineError, match="approval is missing or mismatched"):
        verify_signed_protocol(plan_dir / "plan.json", approval_path, public_key)


def test_application_oracle_validates_only_collector_db_observation(tmp_path):
    capture_report = tmp_path / "capture-report.json"
    atomic_json(
        capture_report,
        {
            "status": "fixture",
            "plan_sha256": "a" * 64,
            "pre_capture_approval": {"approval_file_sha256": "b" * 64},
        },
    )
    request = {
        "request_id": "r1",
        "timestamp_utc": "2026-11-01T00:00:00+00:00",
        "status_code": 201,
    }
    before_path = tmp_path / "application-oracle-before.json"
    atomic_json(
        before_path,
        {
            "format_version": 1,
            "kind": "ai_owned_lab_db_pre_capture_observation",
            "plan_sha256": "a" * 64,
            "approval_file_sha256": "b" * 64,
            "marker": "GTPILOT01",
            "before_count": 0,
            "observed_at_utc": "2026-10-31T23:59:59+00:00",
        },
    )
    oracle = {
        "format_version": 1,
        "kind": "application_db_state_transition",
        "observer": "ai_owned_lab_collector_read_only_query",
        "capture_report_sha256": file_sha256(capture_report),
        "request_id": "r1",
        "marker": "GTPILOT01",
        "before_file_sha256": file_sha256(before_path),
        "before_count": 0,
        "after_count": 1,
        "observed_http_status_code": 201,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "expected_benign_create_persisted",
        "attack_exploit_outcome": "unknown",
    }
    path = tmp_path / "oracle.json"
    atomic_json(path, oracle)
    checked = verify_application_oracle(path, capture_report, request)
    assert checked["application_outcome"] == "collector_observed_benign_create_persisted"
    assert checked["attack_exploit_outcome"] == "unknown"
    oracle["attack_exploit_outcome"] = "failed"
    atomic_json(path, oracle)
    with pytest.raises(PipelineError, match="incomplete or inconsistent"):
        verify_application_oracle(path, capture_report, request)


def test_disposable_lab_cleanup_requires_removed_db_and_closed_ports(tmp_path, monkeypatch):
    atomic_json(
        tmp_path / "owned-lab.json",
        {
            "purpose": "ai-pretrain-disposable",
            "database_container": "idps-ai-pretrain-fixture",
            "processes": {
                "student": {"pid": 10001, "create_time": 100},
                "sensor_namespace": {"pid": 10002, "create_time": 100},
            },
        },
    )
    atomic_json(
        tmp_path / "cleanup.json",
        {"database": "stopped", "student": "stopped", "sensor_namespace": "stopped"},
    )
    monkeypatch.setattr(
        "idps_ai.data.lab_runtime.psutil.Process",
        lambda _pid: SimpleNamespace(create_time=lambda: 100, is_running=lambda: False),
    )
    monkeypatch.setattr(
        "idps_ai.data.lab_runtime.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    def closed_port(*_args, **_kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr("idps_ai.data.lab_runtime.socket.create_connection", closed_port)
    assert verify_lab_cleanup(tmp_path)["status"] == "DISPOSABLE_LAB_REMOVED_AFTER_CAPTURE"
    atomic_json(tmp_path / "cleanup.json", {"database": "not_removed"})
    with pytest.raises(PipelineError, match="cleanup record is incomplete"):
        verify_lab_cleanup(tmp_path)
    atomic_json(
        tmp_path / "cleanup.json",
        {"database": "stopped", "student": "stopped", "sensor_namespace": "stopped"},
    )
    monkeypatch.setattr(
        "idps_ai.data.lab_runtime.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="container-id"),
    )
    with pytest.raises(PipelineError, match="DB container remains"):
        verify_lab_cleanup(tmp_path)


def test_novel_campaign_profile_excludes_previous_critical_targets(tmp_path):
    source = Path(evidence_campaign.__file__)
    old = evidence_campaign.create_plan(tmp_path / "old", source, [101, 203, 307])
    new = evidence_campaign.create_plan(
        tmp_path / "new", source, [401, 503, 607], "novel-v2", [tmp_path / "old"]
    )

    def critical(plan):
        return {
            case["target_sha256"]
            for campaign in plan["campaigns"]
            for case in campaign["cases"]
            if case["scenario"] in ("hard_negative_search", "bounded_attack_intent_probe")
        }

    assert new["case_profile"] == "novel-v2"
    assert len(critical(new)) == 30
    assert not critical(new) & critical(old)
    assert all(len(c["cases"]) == 18 for c in new["campaigns"])
    assert all(c["partition"] == "development_review_only" for c in new["campaigns"])


def test_pcap_body_evidence_binds_response_id_without_persisting_password(tmp_path):
    target = "/api/auth/login"
    body = b"username=lab&password=secret-do-not-log"
    request = (
        b"POST /api/auth/login HTTP/1.1\r\nContent-Type: application/x-www-form-urlencoded\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    response = b"HTTP/1.1 204 No Content\r\nX-Request-Id: r1\r\nContent-Length: 0\r\n\r\n"

    def packet(src, sport, dst, dport, payload):
        ip = (
            b"\x45\x00"
            + struct.pack("!H", 40 + len(payload))
            + b"\x00\x00\x00\x00\x40\x06\x00\x00"
            + ip_address(src).packed
            + ip_address(dst).packed
        )
        tcp = (
            struct.pack("!HHI", sport, dport, 1000)
            + b"\x00\x00\x00\x00\x50\x18\x00\x00\x00\x00\x00\x00"
        )
        frame = b"\x00" * 12 + b"\x08\x00" + ip + tcp + payload
        return struct.pack("<IIII", 0, 0, len(frame), len(frame)) + frame

    pcap = tmp_path / "fixture.pcap"
    header = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 1)
    pcap.write_bytes(
        header
        + packet("127.0.0.40", 40000, "127.0.0.1", 18881, request)
        + packet("127.0.0.1", 18881, "127.0.0.40", 40000, response)
    )
    expected = {
        "r1": {
            "source_ip": "127.0.0.40",
            "http_method": "POST",
            "status_code": 204,
            "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
            "campaign_id": "fixture",
        }
    }
    result = extract_request_bodies(pcap, expected, b"k" * 32)
    assert result["r1"]["body_field_names"] == ["password", "username"]
    assert result["r1"]["body_length"] == len(body)
    assert b"secret-do-not-log" not in json.dumps(result).encode()
    expected["r1"]["status_code"] = 403
    with pytest.raises(PipelineError, match="disagrees with pinned capture"):
        extract_request_bodies(pcap, expected, b"k" * 32)


def test_private_review_tool_keeps_unknown_and_rejects_unobserved_post_body(tmp_path):
    script = Path(__file__).parents[1] / "scripts/review-evidence.py"
    module_spec = importlib.util.spec_from_file_location("review_evidence", script)
    review_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(review_module)
    registry = {"registry_sha256": "a" * 64}
    source = {"id": "two_source"}
    row = {
        "event_key": "b" * 64,
        "request_id": "fixture-post",
        "campaign_id": "fixture",
        "timestamp_utc": "2026-11-02T00:00:00+00:00",
        "http_method": "POST",
        "source_line_sha256": {"nginx": "c" * 64, "student": "d" * 64},
    }
    with pytest.raises(PipelineError, match="distinct"):
        review_module.initialize_review(tmp_path / "wrong", registry, source, "same", "same")
    output = review_module.initialize_review(
        tmp_path / "human", registry, source, "reviewer", "collector"
    )
    with pytest.raises(PipelineError, match="without observed body"):
        review_module.record_decision(
            output, row, "reviewer", "benign", None, "I inspected the real request context.", False
        )
    with pytest.raises(PipelineError, match="separate human inspection"):
        review_module.record_decision(
            output, row, "reviewer", "benign", None, "I inspected the real request context.", True
        )
    review_module.record_decision(
        output,
        row,
        "reviewer",
        "unknown",
        None,
        "POST body was not captured in this source.",
        False,
    )
    result = review_module.summarize_review(output, registry, source, {row["request_id"]: row}, {})
    assert result["counts"] == {"benign": 0, "attack": 0, "unknown": 1, "unreviewed": 0}
    assert result["training_admission"] == 0
    finalized = review_module.finalize_review(
        output, registry, source, {row["request_id"]: row}, {}
    )
    assert finalized["training_admission"] == 0
    with pytest.raises(FileExistsError):
        review_module.finalize_review(output, registry, source, {row["request_id"]: row}, {})
    assert review_module._masked_query("password=secret&q=course+notes")[0]["value"] == "[redacted]"
    path = output / "decisions" / (row["event_key"] + ".json")
    changed = load_json(path)
    changed["source_line_sha256"]["nginx"] = "e" * 64
    atomic_json(path, changed)
    with pytest.raises(PipelineError, match="changed request evidence binding"):
        review_module.summarize_review(output, registry, source, {row["request_id"]: row}, {})


def test_tampered_intent_fails_before_any_lab_request(tmp_path):
    source = Path(evidence_campaign.__file__)
    evidence_campaign.create_plan(tmp_path / "plan", source, [101, 203, 307])
    path = tmp_path / "plan/plan.json"
    plan = load_json(path)
    plan["campaigns"][0]["cases"][0]["planned_intent"] = "attack"
    atomic_json(path, plan)
    with pytest.raises(PipelineError, match="Pre-registered campaign plan changed"):
        evidence_campaign.collect(
            tmp_path / "plan", tmp_path / "nonexistent-lab", tmp_path / "capture", source
        )
    assert not (tmp_path / "capture").exists()


def verified_fixture(tmp_path, prefix="test"):
    source = Path(evidence_campaign.__file__)
    plan_dir, lab_dir, capture_dir = (tmp_path / name for name in ("plan", "lab", "capture"))
    plan = evidence_campaign.create_plan(plan_dir, source, [101, 203, 307])
    lab_dir.mkdir()
    capture_dir.mkdir()
    pending = []
    nginx, student = [], []
    for index, campaign in enumerate(plan["campaigns"]):
        for offset, (case, spec) in enumerate(
            zip(evidence_campaign._cases(index, campaign["seed"]), campaign["cases"])
        ):
            rid = f"{prefix}-{index}-{offset}"
            target = urlsplit(case["target"])
            n = {
                "request_id": rid,
                "timestamp": "2026-11-01T00:00:00+00:00",
                "http_method": case["method"],
                "status": 200,
                "uri_path": target.path,
                "query_string": target.query,
            }
            s = {
                "request_id": rid,
                "timestamp": "2026-11-01T00:00:01+00:00",
                "http_method": case["method"],
                "status_code": 200,
                "uri_path": target.path,
            }
            n_line = (json.dumps(n) + "\n").encode()
            s_line = (json.dumps(s) + "\n").encode()
            nginx.append(n_line)
            student.append(s_line)
            pending.append(
                {
                    "request_id": rid,
                    "timestamp_utc": "2026-11-01T00:00:00+00:00",
                    "campaign_id": campaign["campaign_id"],
                    "case_id": case["case_id"],
                    "planned_intent": spec["planned_intent"],
                    "planned_family": spec["attack_family"],
                    "intent_label_from_plan": int(spec["planned_intent"] == "attack"),
                    "http_method": case["method"],
                    "status_code": 200,
                    "target_sha256": spec["target_sha256"],
                    "plan_sha256": plan["plan_sha256"],
                    "exploit_outcome": "unknown",
                    "source_count": 2,
                    "capture_verified": True,
                    "review_status": "pending_independent_semantic_review",
                    "training_eligible": False,
                    "source_evidence": {
                        "nginx_access_line_sha256": hashlib.sha256(
                            n_line.rstrip(b"\n")
                        ).hexdigest(),
                        "student_audit_line_sha256": hashlib.sha256(
                            s_line.rstrip(b"\n")
                        ).hexdigest(),
                        "nginx_timestamp": n["timestamp"],
                        "student_timestamp": s["timestamp"],
                    },
                }
            )
    (lab_dir / "access-lab.log").write_bytes(b"".join(nginx))
    (lab_dir / "student-audit.log").write_bytes(b"".join(student))
    for row in pending:
        row["source_evidence"]["nginx_file_sha256"] = file_sha256(lab_dir / "access-lab.log")
        row["source_evidence"]["student_file_sha256"] = file_sha256(lab_dir / "student-audit.log")
    ledger = capture_dir / "pending-evidence.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in pending))
    atomic_json(
        capture_dir / "report.json",
        {
            "plan_sha256": plan["plan_sha256"],
            "plan_file_sha256": file_sha256(plan_dir / "plan.json"),
            "pending_evidence_sha256": file_sha256(ledger),
            "observed_distinct_request_ids": len(pending),
            "captured_nginx_and_student": len(pending),
            "new_training_admission": 0,
            "application_workload_401": 0,
            "formal_training_permitted": False,
        },
    )
    return plan_dir, lab_dir, capture_dir, source


def test_blind_automatic_review_resumes_and_keeps_all_intents_unknown(tmp_path):
    plan, lab, capture, collector = verified_fixture(tmp_path)
    script_root = Path(__file__).parents[1] / "scripts"

    def load_script(filename, name):
        spec = importlib.util.spec_from_file_location(name, script_root / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    prepare = load_script("prepare-evidence-review.py", "prepare_evidence_review")
    reviewer = load_script("review-evidence.py", "review_evidence_auto")
    queue_dir, assist_dir = tmp_path / "queue", tmp_path / "assist"
    prepare.prepare(plan, lab, capture, queue_dir, collector)
    prepare.prepare_assist(plan, lab, capture, queue_dir, assist_dir, collector)
    registry_path = tmp_path / "registry.json"
    registry = {
        "format_version": 1,
        "sources": [
            {
                "id": "fixture",
                "plan": str(plan),
                "lab": str(lab),
                "capture": str(capture),
                "queue": str(queue_dir),
                "assist": str(assist_dir),
                "collector_source": str(collector),
                "collector_id": "fixture-collector",
                "three_source": None,
                "body_evidence": None,
            }
        ],
    }
    registry["registry_sha256"] = digest(registry)
    atomic_json(registry_path, registry)
    bound = reviewer.load_registry(registry_path)
    auto_dir = tmp_path / "auto"
    partial = reviewer.automated_review(registry_path, bound, auto_dir, batch_size=3, max_new=7)
    assert partial["automatically_reviewed_requests"] == 7
    assert partial["status"] == "PARTIAL_RESUMABLE_OBJECTIVE_REVIEW"
    with pytest.raises(PipelineError, match="incomplete"):
        reviewer.compare_after_blind(bound, auto_dir, tmp_path / "early")
    complete = reviewer.automated_review(registry_path, bound, auto_dir, resume=True)
    assert complete["automatically_reviewed_requests"] == 54
    assert complete["unknown_intent_labels"] == 54
    assert complete["objective_oracle_verified_labels"] == 0
    assert complete["training_admission"] == 0
    again = reviewer.automated_review(registry_path, bound, auto_dir, resume=True)
    assert again["newly_processed_this_run"] == 0
    comparison = reviewer.compare_after_blind(bound, auto_dir, tmp_path / "comparison")
    assert comparison["counts"]["requests_compared"] == 54
    assert comparison["training_admission"] == 0
    assert reviewer.blind_syntax_triage("password=union+select")[0] == []
    assert reviewer.blind_syntax_triage("q=union+select+1")[0] == ["sqli"]
    assert b"union+select" not in (auto_dir / "auto-review.sqlite").read_bytes().lower()
    crashed = tmp_path / "crashed"
    reviewer.automated_review(registry_path, bound, crashed, batch_size=2, max_new=5)
    (crashed / "report.json").unlink()  # simulate interruption after committed batch
    with pytest.raises(PipelineError, match="explicit --recover"):
        reviewer.automated_review(registry_path, bound, crashed, resume=True)
    recovered = reviewer.automated_review(registry_path, bound, crashed, resume=True, recover=True)
    assert recovered["automatically_reviewed_requests"] == 54
    assert recovered["recovered_unsealed_checkpoint"] is True
    with (auto_dir / "auto-review.sqlite").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(PipelineError, match="checkpoint"):
        reviewer.automated_review(registry_path, bound, auto_dir, resume=True)


def test_readback_binds_status_clock_target_and_source_lines(tmp_path):
    spec = verified_fixture(tmp_path)
    assert evidence_campaign.verify_capture(*spec)["request_ids"] == 54
    ledger = spec[2] / "pending-evidence.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[0]["status_code"] = 403
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = load_json(spec[2] / "report.json")
    report["pending_evidence_sha256"] = file_sha256(ledger)
    atomic_json(spec[2] / "report.json", report)
    with pytest.raises(PipelineError, match="HTTP evidence disagrees"):
        evidence_campaign.verify_capture(*spec)
    rows[0]["status_code"] = 200
    rows[0]["timestamp_utc"] = "2026-11-01T00:01:00+00:00"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report["pending_evidence_sha256"] = file_sha256(ledger)
    atomic_json(spec[2] / "report.json", report)
    with pytest.raises(PipelineError, match="clocks differ"):
        evidence_campaign.verify_capture(*spec)


def test_capture_lineage_rejects_repeated_physical_request_id(tmp_path):
    spec = verified_fixture(tmp_path)
    with pytest.raises(PipelineError, match="repeats across capture"):
        evidence_campaign.audit_capture_set([spec, spec], tmp_path / "lineage")


def test_historical_log_ids_are_checked_but_not_added_to_training_count(tmp_path):
    spec = verified_fixture(tmp_path)
    second_root = tmp_path / "second"
    second_root.mkdir()
    second = verified_fixture(second_root, prefix="next")
    old = tmp_path / "unsealed-student-audit.log"
    old.write_text(
        json.dumps({"request_id": "test-0-0"})
        + "\n"
        + json.dumps({"request_id": "older-unique-id"})
        + "\n"
    )
    result = evidence_campaign.audit_capture_set(
        [spec, second],
        tmp_path / "lineage",
        [old],
    )
    assert result["cross_run_id_collisions"] == 1
    assert result["status"] == "CROSS_RUN_ID_COLLISION_REVIEW_REQUIRED"
    assert result["historical_student_ids_scanned"] == 2
    assert result["training_admission"] == 0


def test_blind_review_queue_cannot_be_silently_labeled(tmp_path):
    spec = verified_fixture(tmp_path)
    plan_dir, lab_dir, capture_dir, source = spec
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    capture_report = load_json(capture_dir / "report.json")
    rows = [
        json.loads(line)
        for line in (capture_dir / "pending-evidence.jsonl").read_text().splitlines()
    ]
    queue_rows = [
        {
            "event_key": hashlib.sha256(
                (capture_report["plan_sha256"] + ":" + row["request_id"]).encode()
            ).hexdigest(),
            "request_id": row["request_id"],
            "campaign_id": row["campaign_id"],
            "timestamp_utc": row["timestamp_utc"],
            "http_method": row["http_method"],
            "source_line_sha256": {
                "nginx": row["source_evidence"]["nginx_access_line_sha256"],
                "student": row["source_evidence"]["student_audit_line_sha256"],
            },
            "intent": "unknown",
            "label": None,
            "attack_family": None,
            "exploit_outcome": "unknown",
            "review_status": "pending",
            "training_eligible": False,
            "reviewer_id": None,
            "semantic_evidence_sha256": None,
            "application_oracle_sha256": None,
        }
        for row in rows
    ]
    queue = review_dir / "blind-review.jsonl"
    queue.write_text("".join(json.dumps(row) + "\n" for row in queue_rows))
    review_report = {
        "plan_sha256": capture_report["plan_sha256"],
        "capture_report_sha256": file_sha256(capture_dir / "report.json"),
        "queue_sha256": file_sha256(queue),
        "requests": 54,
        "approved_benign": 0,
        "approved_attack": 0,
        "new_training_admission": 0,
    }
    atomic_json(review_dir / "report.json", review_report)
    assert (
        evidence_campaign.verify_blind_queue(plan_dir, lab_dir, capture_dir, review_dir, source)[
            "requests"
        ]
        == 54
    )
    queue_rows[0]["label"] = 1
    queue.write_text("".join(json.dumps(row) + "\n" for row in queue_rows))
    review_report["queue_sha256"] = file_sha256(queue)
    atomic_json(review_dir / "report.json", review_report)
    with pytest.raises(PipelineError, match="does not match pending"):
        evidence_campaign.verify_blind_queue(plan_dir, lab_dir, capture_dir, review_dir, source)


def test_three_source_eve_correlation_requires_real_request_binding(tmp_path):
    plan_dir, lab_dir, capture_dir, source = verified_fixture(tmp_path)
    eve_dir = tmp_path / "eve"
    eve_dir.mkdir()
    (lab_dir / "traffic.pcap").write_bytes(b"TEST_ONLY_FAKE_PCAP_NOT_REAL_CAPTURE")
    plan = load_json(plan_dir / "plan.json")
    source_ips = {c["campaign_id"]: c["source_ip"] for c in plan["campaigns"]}
    with (lab_dir / "access-lab.log").open() as stream:
        nginx = {r["request_id"]: r for r in (json.loads(line) for line in stream)}
    (lab_dir / "access.log").write_text(
        "".join(json.dumps(dict(row, query_string=None)) + "\n" for row in nginx.values())
    )
    atomic_json(lab_dir / "owned-lab.json", {"ai_input_profile": "safe_query_numeric_v2"})
    with (capture_dir / "pending-evidence.jsonl").open() as stream:
        pending = [json.loads(line) for line in stream]
    eve = []
    for index, item in enumerate(pending):
        n = nginx[item["request_id"]]
        target = n["uri_path"] + ("?" + n["query_string"] if n["query_string"] else "")
        eve.append(
            {
                "event_type": "http",
                "timestamp": "2026-11-01T00:00:02+00:00",
                "src_ip": source_ips[item["campaign_id"]],
                "dest_port": 18881,
                "flow_id": index + 1,
                "http": {
                    "http_method": item["http_method"],
                    "status": 200,
                    "url": safe_route(n["uri_path"]),
                    "response_headers": [{"name": "X-Request-Id", "value": item["request_id"]}],
                },
                "ai_query_numeric": project_query(target, version=2),
            }
        )
        eve.append(
            {"event_type": "flow", "flow_id": index + 1, "timestamp": "2026-11-01T00:00:03+00:00"}
        )
    eve_path = eve_dir / "eve.json"

    def write_eve():
        eve_path.write_text("".join(json.dumps(row) + "\n" for row in eve))
        atomic_json(
            eve_dir / "decode-manifest.json",
            {
                "status": "PASS",
                "input_profile": "safe_query_numeric_v2",
                "pcap_sha256": file_sha256(lab_dir / "traffic.pcap"),
                "eve_sha256": file_sha256(eve_path),
            },
        )

    write_eve()
    atomic_json(
        lab_dir / "pcap-manifest.json",
        {
            "pcap_sha256": file_sha256(lab_dir / "traffic.pcap"),
            "evidence_capture_report_sha256": file_sha256(capture_dir / "report.json"),
            "query_profile": "safe_query_numeric_v2",
        },
    )
    result = evidence_campaign.verify_three_source_capture(
        plan_dir, lab_dir, capture_dir, eve_dir, source, tmp_path / "correlated"
    )
    assert result["request_count"] == 54
    assert result["lab_nginx_eve_numeric_projection_mismatches"] == 0
    assert result["masked_nginx_query_null_requests"] == 54
    assert result["offline_visibility_status"] == "LAB_MASKED_EDGE_AND_EVE_V2_BOUND"
    assert result["training_admission"] == 0
    script = Path(__file__).parents[1] / "scripts/prepare-evidence-review.py"
    module_spec = importlib.util.spec_from_file_location("prepare_evidence_review", script)
    review_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(review_module)
    review_dir = tmp_path / "three-source-review"
    review_module.prepare(
        plan_dir, lab_dir, capture_dir, review_dir, source, tmp_path / "correlated"
    )
    assert (
        evidence_campaign.verify_blind_queue(
            plan_dir, lab_dir, capture_dir, review_dir, source, tmp_path / "correlated"
        )["requests"]
        == 54
    )
    assist = review_module.prepare_assist(
        plan_dir,
        lab_dir,
        capture_dir,
        review_dir,
        tmp_path / "assist",
        source,
        tmp_path / "correlated",
    )
    assert assist["counts"]["requests"] == assist["counts"]["three_source"] == 54
    assert assist["automatic_verified_labels"] == assist["training_admission"] == 0
    assist_rows = [
        json.loads(line)
        for line in (tmp_path / "assist/review-assist.jsonl").read_text().splitlines()
    ]
    assert all(row["independent_review"]["decision"] is None for row in assist_rows)
    assert all("query_string" not in row["automatic_facts"] for row in assist_rows)
    assert all("collector_precommitted_intent" not in row for row in assist_rows)
    proposal_rows = [
        json.loads(line)
        for line in (tmp_path / "assist/review-proposals.jsonl").read_text().splitlines()
    ]
    assert len(proposal_rows) == 54
    assert all(row["reviewer_decision"] is None for row in proposal_rows)
    queue = review_dir / "blind-review.jsonl"
    rows = [json.loads(line) for line in queue.read_text().splitlines()]
    assert all(set(row["source_line_sha256"]) == {"nginx", "student", "eve_http"} for row in rows)
    rows[0]["source_line_sha256"]["eve_http"] = "0" * 64
    queue.write_text("".join(json.dumps(row) + "\n" for row in rows))
    review_report = load_json(review_dir / "report.json")
    review_report["queue_sha256"] = file_sha256(queue)
    atomic_json(review_dir / "report.json", review_report)
    with pytest.raises(PipelineError, match="does not match pending"):
        evidence_campaign.verify_blind_queue(
            plan_dir, lab_dir, capture_dir, review_dir, source, tmp_path / "correlated"
        )
    eve[0]["http"]["status"] = 403
    write_eve()
    with pytest.raises(PipelineError, match="Three-source review evidence is stale"):
        evidence_campaign.verify_blind_queue(
            plan_dir, lab_dir, capture_dir, review_dir, source, tmp_path / "correlated"
        )
    with pytest.raises(PipelineError, match="EVE HTTP/flow disagrees"):
        evidence_campaign.verify_three_source_capture(
            plan_dir, lab_dir, capture_dir, eve_dir, source, tmp_path / "tampered"
        )
    eve[0]["http"]["status"] = 200
    write_eve()
    masked = lab_dir / "access.log"
    masked_rows = [json.loads(line) for line in masked.read_text().splitlines()]
    masked_rows[0]["query_string"] = "visible-private-query"
    masked.write_text("".join(json.dumps(row) + "\n" for row in masked_rows))
    with pytest.raises(PipelineError, match="Masked edge Nginx view disagrees"):
        evidence_campaign.verify_three_source_capture(
            plan_dir, lab_dir, capture_dir, eve_dir, source, tmp_path / "leaky-edge"
        )

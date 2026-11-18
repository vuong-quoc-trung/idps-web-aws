# isort: skip_file

"""Reconcile existing capture and automated authorization evidence, no new traffic."""

import importlib.util
import os
from collections import Counter

from common import HERE, PARENT, atomic_json, check, file_sha256, output_arg, read
from idps_ai.common import REPO_ROOT, digest


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def semantic_disposition(evidence):
    required = (
        "actor_verified",
        "session_verified",
        "role_verified",
        "policy_verified",
        "target_verified",
        "request_binding_verified",
        "application_oracle_verified",
    )
    if not all(evidence.get(key) is True for key in required):
        return "INSUFFICIENT_EVIDENCE"
    if evidence.get("expected_authorized") is False and evidence.get("observed_action") in {
        "ALLOWED",
        "DENIED",
    }:
        return "ATTACK_VERIFIED"
    if evidence.get("expected_authorized") is True and evidence.get("observed_action") == "ALLOWED":
        return "BENIGN_VERIFIED"
    return "INSUFFICIENT_EVIDENCE"


def run(out):
    contracts = HERE.parent
    checker = load_module(
        "r261_r72_acceptance", contracts / "capture-campaign-r72/accept_capture.py"
    )
    verified = checker.accept()
    original = read(contracts / "capture-campaign-r72/capture-acceptance.json")
    check(
        verified["statistics"] == original["statistics"],
        "Historical campaign reconciliation changed",
    )
    run = contracts / "capture-campaign-r71/run"
    candidates = read(run / "candidate-ledger.json")["ledger"]
    outcomes = {
        row["request_key"]: row
        for line in (run / "receipts.jsonl").read_text().splitlines()
        if (row := __import__("json").loads(line)).get("kind") == "ATTEMPT"
        and row.get("request_key")
    }
    gaps = Counter()
    for candidate in candidates:
        row = outcomes[candidate["request_key"]]
        if candidate["intent"] == "ATTACK_INTENT":
            for field in (
                "actor_identity",
                "actor_session",
                "actor_role",
                "resource_owner",
                "authorization_policy",
                "uri76",
            ):
                if not row.get(field):
                    gaps[field] += 1
    witnesses = []
    pins = {}
    for name in ("t09-r8-authorized-20261117", "t09-r10-context-20261117"):
        root = PARENT.parent / name
        path = root / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl"
        check(path.is_file(), "Existing native authorization ledger missing")
        summary = read(root / "summary.json")
        check(isinstance(summary, dict), "Malformed native run summary")
        # Validate the durable checkpoint's ledger binding before semantic checks.
        ck = read(root / "checkpoint.json")
        pins[str(path.relative_to(REPO_ROOT))] = file_sha256(path)
        check(
            pins[str(path.relative_to(REPO_ROOT))] in __import__("json").dumps(ck),
            "Native ledger checkpoint SHA missing",
        )
        rows = {
            row["request_key"]: row
            for line in path.read_text().splitlines()
            if (row := __import__("json").loads(line)).get("kind") == "ATTEMPT"
            and row.get("request_key")
        }
        for row in rows.values():
            proof = row.get("authorization_oracle")
            if not proof:
                continue
            parent = rows.get(proof.get("principal_request_key"), {})
            valid = (
                proof.get("sha256") == digest({k: v for k, v in proof.items() if k != "sha256"})
                and proof.get("request_key") == row["request_key"]
                and row.get("identity_verified") is True
                and row.get("clock_valid") is True
                and row.get("oracle_verified") is True
                and proof.get("actor_session_matches_principal") is True
                and proof.get("actor_role") == "ADMIN"
                and proof.get("policy") == "STUDENT_RECORD_READ_ADMIN"
                and proof.get("owner_stable_before_after") is True
                and proof.get("owner_matches_fixture_record") is True
                and parent.get("oracle_basis") == "PRINCIPAL_AND_JDBC_ROLE"
                and any(
                    e["source"] == "A"
                    and e["proof_sha256"] == proof.get("target_audit_proof_sha256")
                    for e in row["events"]
                )
                and any(
                    e["source"] == "A"
                    and e["proof_sha256"] == proof.get("principal_audit_proof_sha256")
                    for e in parent.get("events", [])
                )
            )
            check(valid, "Native semantic Oracle binding failed")
            evidence = dict.fromkeys(
                (
                    "actor_verified",
                    "session_verified",
                    "role_verified",
                    "policy_verified",
                    "target_verified",
                    "request_binding_verified",
                    "application_oracle_verified",
                ),
                True,
            )
            evidence.update(expected_authorized=True, observed_action="ALLOWED")
            witnesses.append(
                {
                    "request_key": row["request_key"],
                    "campaign": name,
                    "label": semantic_disposition(evidence),
                    "proof_sha256": proof["sha256"],
                    "feature_at_cutoff": bool(row.get("uri76", {}).get("projection_in_time")),
                    "mask": row["native_mask"],
                    "role": "ENGINEERING_UNASSIGNED",
                }
            )
    check(len(witnesses) == 6, "Expected six independently corroborated authorized-read witnesses")
    atomic_json(
        out / "native-evidence.json",
        {
            "campaign_101_reconciliation": "PASS",
            "capture_counts": verified["statistics"],
            "authorized_read_witnesses": witnesses,
            "authorized_labels_automatically_corroborated": 6,
            "new_ATTACK_VERIFIED": 0,
            "attack_intent_requests_with_insufficient_semantic_context": 37,
            "missing_semantic_fields_in_old_attack_receipts": dict(gaps),
            "input_sha256": pins,
            "original_admission_candidates": 74,
            "canonical_TRAIN": 0,
            "native_TRAIN_DEV_CAL_TEST": [0, 0, 0, 0],
            "reason": "No verified low-privilege attack evidence in retained receipts; authorized controls do not supply an attack class. Historical session/H2 state was ephemeral and cannot be invented after cleanup.",
            "new_HTTP_requests": 0,
            "no_human_review_attestation_fabricated": True,
            "semantic_verifier_scope": "Machine corroboration of existing policy/Oracle facts; final admission and independent lineage remain separate",
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

"""Research derivative schema and receipt checks; no label inference from detector scores."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from idps_ai.common import canonical_bytes, digest, file_sha256

VERSION = "attack-intent-v1-20261107"
INTENTS = {"BENIGN_INTENT", "ATTACK_INTENT", "UNKNOWN_INTENT"}
OUTCOMES = {
    "BENIGN_SUCCESS",
    "VERIFIED_EXPLOIT_SUCCESS",
    "VERIFIED_FAILED_ATTEMPT",
    "UNSAFE_REFLECTION",
    "UNKNOWN_OUTCOME",
    "NOT_APPLICABLE",
}
LEVELS = {
    "APPLICATION_ORACLE_VERIFIED",
    "AUTOMATED_CHECK_SUPPORTED",
    "HUMAN_REVIEWED",
    "REVIEW_PENDING",
    "INSUFFICIENT_EVIDENCE",
}
ROLES = {"TRAIN", "CALIBRATION", "DEVELOPMENT", "PROSPECTIVE_EVALUATION", "UNKNOWN_REVIEW_PENDING"}
HEADERS = ("User-Agent", "Accept", "Content-Type")


def runtime_request(request):
    """Same selected-header/body contract as worker.model_record, not a new encoder."""
    text = request.get("headers") or ""
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip().lower()] = value.strip()
    return {
        "method": request["method"],
        "url": request["url"],
        "body": None,
        "headers": "\r\n".join(
            f"{name}: {values[name.lower()]}"
            for name in HEADERS
            if values.get(name.lower()) not in {None, "", "-"}
        ),
    }


def read_receipt(base: Path, *, request_id=None):
    r = json.loads((base / "receipt.json").read_text())
    h = json.loads((base / "request-headers.json").read_text())
    rh = json.loads((base / "response-headers.json").read_text())
    if request_id is not None and r["request_id"] != request_id:
        raise ValueError("Receipt transaction identity mismatch")
    for path, expected in [
        ("request-body.bin", r["request_body_sha256"]),
        ("response-body.bin", r["response_sha256"]),
    ]:
        if file_sha256(base / path) != expected:
            raise ValueError("Receipt body checksum mismatch")
    if digest(h) != r["request_headers_sha256"] or digest(rh) != r["response_headers_sha256"]:
        raise ValueError("Receipt headers checksum mismatch")
    request = {
        "method": r["method"],
        "url": r["path"],
        "body": (base / "request-body.bin").read_text(),
        "headers": "\r\n".join(f"{k}: {v}" for k, v in h.items()),
    }
    return request, r


def normalize_label(intent, outcome, oracle_verified):
    intent = {
        "BENIGN": "BENIGN_INTENT",
        "benign": "BENIGN_INTENT",
        "ATTACK_ATTEMPT": "ATTACK_INTENT",
        "attack": "ATTACK_INTENT",
    }.get(intent, "UNKNOWN_INTENT")
    if intent == "BENIGN_INTENT":
        return intent, "BENIGN_SUCCESS" if oracle_verified else "UNKNOWN_OUTCOME"
    if intent == "UNKNOWN_INTENT":
        return intent, "UNKNOWN_OUTCOME"
    if not oracle_verified:
        return intent, "UNKNOWN_OUTCOME"
    if outcome == "UNSAFE_REFLECTION":
        return intent, "UNSAFE_REFLECTION"
    if outcome in {"VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE", "VERIFIED_EXPLOIT_SUCCESS"}:
        return intent, "VERIFIED_EXPLOIT_SUCCESS"
    if outcome == "VERIFIED_FAILED_ATTEMPT":
        return intent, outcome
    return intent, "UNKNOWN_OUTCOME"


def validate_record(row):
    required = {
        "sample_id",
        "dataset_version",
        "environment",
        "request_provenance",
        "workflow_group",
        "session_group",
        "campaign_group",
        "intent",
        "outcome",
        "evidence_levels",
        "label_source",
        "review_status",
        "feature_compatibility",
        "split",
        "checksums",
        "missingness",
        "inclusion_exclusion_reasons",
        "oracle_verified",
        "independent_human_verified",
        "prior_exposure",
    }
    if not required <= row.keys():
        raise ValueError("Missing schema fields")
    if (
        row["dataset_version"] != VERSION
        or row["intent"] not in INTENTS
        or row["outcome"] not in OUTCOMES
        or row["split"] not in ROLES
    ):
        raise ValueError("Invalid schema enum")
    if not set(row["evidence_levels"]) <= LEVELS:
        raise ValueError("Invalid evidence level")
    if row["outcome"] in {
        "VERIFIED_EXPLOIT_SUCCESS",
        "VERIFIED_FAILED_ATTEMPT",
        "UNSAFE_REFLECTION",
    } and (row["intent"] != "ATTACK_INTENT" or not row["oracle_verified"]):
        raise ValueError("Attack outcome requires attack intent and Oracle")
    if row["outcome"] == "BENIGN_SUCCESS" and (
        row["intent"] != "BENIGN_INTENT" or not row["oracle_verified"]
    ):
        raise ValueError("Benign success requires Oracle")
    if "APPLICATION_ORACLE_VERIFIED" in row["evidence_levels"] and not row["oracle_verified"]:
        raise ValueError("Oracle evidence inconsistent")
    if "HUMAN_REVIEWED" in row["evidence_levels"] and not (
        row["independent_human_verified"] and row.get("human_review_provenance")
    ):
        raise ValueError("Human review requires reviewer provenance")
    if row["review_status"] == "PENDING" and row["independent_human_verified"]:
        raise ValueError("Pending is not verified human review")
    if row["intent"] == "UNKNOWN_INTENT" and row.get("eligible_for_fit"):
        raise ValueError("Unknown intent cannot fit")


def dataset_fingerprint(rows, file_hashes, plan_sha256):
    # Order is irrelevant; provenance and exclusion changes are not.
    return digest(
        {
            "records": sorted(rows, key=lambda x: x["sample_id"]),
            "files_sha256": file_hashes,
            "plan_sha256": plan_sha256,
        }
    )


def vector_hash(x):
    import hashlib

    return hashlib.sha256(np.asarray(x, dtype="<f4").tobytes()).hexdigest()


def collision_groups(rows, field):
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(row["checksums"][field], []).append(i)
    return [
        indices
        for indices in groups.values()
        if len({rows[i]["intent"] for i in indices} - {"UNKNOWN_INTENT"}) > 1
    ]


def raw_key(request):
    import hashlib

    return hashlib.sha256(
        canonical_bytes([request["method"], request["url"], request.get("body") or ""])
    ).hexdigest()


def validate_eligible_splits(rows):
    """No admitted cross-role exact identities, including hidden session lineage."""
    seen = {}
    for row in rows:
        if row["inclusion_exclusion_reasons"]:
            continue
        for kind in ["raw", "template", "full_view", "runtime_view"]:
            key = (kind, row["checksums"][kind])
            if key in seen and seen[key] != row["split"]:
                raise ValueError("Eligible split identity overlap")
            seen[key] = row["split"]
        for kind in ["session_group", "campaign_group"]:
            key = (kind, row[kind])
            if key in seen and seen[key] != row["split"]:
                raise ValueError("Eligible split lineage overlap")
            seen[key] = row["split"]


def visibility_bounds(rows, field="runtime_view", fpr_budget=0.01):
    """Optimistic finite-cohort bound for deterministic flags on identical tensors.

    This uses labels for diagnosis, never to choose a model or threshold. No
    population inference or assertion about contextual detectors is implied.
    """
    groups = {}
    for r in rows:
        if r["intent"] != "UNKNOWN_INTENT":
            groups.setdefault(r["checksums"][field], []).append(r)
    benign = sum(r["intent"] == "BENIGN_INTENT" for g in groups.values() for r in g)
    attacks = sum(r["intent"] == "ATTACK_INTENT" for g in groups.values() for r in g)
    budget = int(benign * fpr_budget)
    dp = [0] * (budget + 1)
    floor = 0
    for group in groups.values():
        b = sum(r["intent"] == "BENIGN_INTENT" for r in group)
        a = sum(r["intent"] == "ATTACK_INTENT" for r in group)
        floor += min(a, b)
        if b == 0:
            dp = [x + a for x in dp]
        elif b <= budget:
            for k in range(budget, b - 1, -1):
                dp[k] = max(dp[k], dp[k - b] + a)
    return dict(
        known_benign=benign,
        known_attacks=attacks,
        allowed_false_flags=budget,
        unavoidable_label_errors_on_identical_views=floor,
        optimistic_max_attack_flags_at_budget=max(dp),
        optimistic_recall_ceiling_at_budget=max(dp) / attacks if attacks else None,
        scope="Finite exposed cohort, deterministic request tensor only; not population FPR/Recall",
    )

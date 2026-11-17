"""Optional read-only join with the existing Local Rust advisory database."""

import json
import os
import re
import subprocess

from store import RI_MODEL, RID


def configured(state):
    path = state / "hybrid-readonly.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256:
        raise ValueError("Invalid PostgreSQL service config")
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or set(data) != {"pg_service"}
        or not isinstance(data["pg_service"], str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", data["pg_service"])
    ):
        raise ValueError("Expected a named read-only PostgreSQL service")
    return data["pg_service"]


def fetch(service, ids):
    if not service or not ids:
        return {}, "UNCONFIGURED" if not service else "IDLE"
    if len(ids) > 16 or not all(RID.fullmatch(rid) for rid in ids):
        raise ValueError("Unsafe PostgreSQL join batch")
    # A named service lets libpq use a private credential file. The query
    # reads metadata only and requests a read-only, short-lived transaction.
    allowlist = ",".join(f"'{rid}'" for rid in ids)
    query = f"""
        SELECT json_build_object('id',h.request_id,'action',h.decision->>'policy_action',
          'risk',h.decision->'rule_risk_component','rule_sources',h.decision->'rule_sources',
          'model',h.decision->'ai'->>'model_id','signal',h.decision->'ai'->>'signal',
          'score',h.decision->'ai'->'score','ri_event_id',a.event_id,
          'automatic_block',h.decision->'automatic_block','fingerprint',h.evidence_fingerprint,
          'correlation_proof_sha256',c.result->>'proof_sha256','sources',c.result->'sources',
          'late_event',c.result->'late_event')
        FROM hybrid_incidents h LEFT JOIN ai_shadow_results a USING (request_id)
        LEFT JOIN request_correlations c USING (request_id)
        WHERE h.request_id IN ({allowlist})
    """
    try:
        result = subprocess.run(
            ["psql", "-X", "-qAtw", "-v", "ON_ERROR_STOP=1", "-c", query],
            env=os.environ
            | {
                "PGSERVICE": service,
                "PGCONNECT_TIMEOUT": "2",
                "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=800",
            },
            capture_output=True,
            check=True,
            timeout=2.5,
        )
        if len(result.stdout) > 32768:
            return {}, "BUDGET_EXCEEDED"
        return {
            row["id"]: row
            for line in result.stdout.splitlines()
            if (row := json.loads(line))["id"] in ids
        }, "AVAILABLE"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return {}, "UNAVAILABLE"


def attach(row, context, status):
    row["policy_context_status"] = status
    if context is None:
        return
    ri = row["ri_v2"]
    action = context["action"]
    if (
        action not in {"LOG_ONLY", "ALERT", "REVIEW", "PROPOSE_BLOCK"}
        or context["automatic_block"] is not False
    ):
        row["policy_context_status"] = "UNVERIFIED"
        return
    score = context["score"]
    if context["signal"] in {"ABOVE_THRESHOLD_UNCALIBRATED", "BELOW_THRESHOLD_UNCALIBRATED"}:
        if not (
            ri["status"] == "SCORED"
            and context["model"] == RI_MODEL
            and context["ri_event_id"] == ri["event_id"]
            and type(score) in (int, float)
            and abs(score - ri["score"]) <= 1e-12
        ):
            row["policy_context_status"] = "RI_BINDING_MISMATCH"
            return
    elif context["signal"] != "AI_UNAVAILABLE":
        row["policy_context_status"] = "UNVERIFIED"
        return
    row["rule"] = {"request_rule_risk": context["risk"], "sources": context["rule_sources"]}
    row["hybrid"] = {
        "action": action,
        "model": context["model"],
        "signal": context["signal"],
        "fingerprint": context["fingerprint"],
        "automatic_block": False,
    }
    row["correlation"] = {
        "scope": "POST_OBSERVATION_ONLY",
        "structural_sources": context["sources"],
        "late_event": context["late_event"],
        "proof_sha256": context["correlation_proof_sha256"],
    }

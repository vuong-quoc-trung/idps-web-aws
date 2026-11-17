"""Bounded, resumable quality evidence for a single Local campaign."""

import fcntl
import json
from collections import Counter

from idps_ai.common import atomic_json, digest

MAX_ROWS = 32
MAX_ROW_BYTES = 12_288
VERSION = "idps-local-shadow-evidence-v1"
SOURCE_CUTOFF = 999_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def append(path, run_id, limit, row):
    """Atomically commit one trusted request and cursor, idempotent on retry."""
    require(
        0 < limit <= MAX_ROWS and len(json.dumps(row, allow_nan=False).encode()) <= MAX_ROW_BYTES,
        "Evidence budget exceeded",
    )
    with path.with_suffix(".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = {
            "version": VERSION,
            "run_id": run_id,
            "limit": limit,
            "rows": [],
            "cursor": 0,
            "rows_sha256": digest([]),
        }
        if path.exists():
            require(
                path.stat().st_size <= limit * (MAX_ROW_BYTES + 16) + 1024,
                "Checkpoint budget exceeded",
            )
            state = read(path)
        rows = state["rows"]
        require(
            state["version"] == VERSION
            and state["run_id"] == run_id
            and state["limit"] == limit
            and state["cursor"] == len(rows) <= limit
            and state["rows_sha256"] == digest(rows)
            and all(r["attempt"] == i for i, r in enumerate(rows, 1))
            and len({r["request_id"] for r in rows}) == len(rows)
            and len({r["request_key"] for r in rows}) == len(rows),
            "Evidence checkpoint integrity mismatch",
        )
        for previous in rows:
            if any(previous[k] == row[k] for k in ("attempt", "request_id", "request_key")):
                require(previous == row, "Conflicting duplicate evidence")
                return False
        require(row["attempt"] == len(rows) + 1 <= limit, "Receipt cursor gap or bound exceeded")
        rows.append(row)
        atomic_json(path, state | {"cursor": len(rows), "rows_sha256": digest(rows)})
    return True


def observed_sources(events):
    return {
        e["source"]: {
            "proof_sha256": e["proof_sha256"],
            "receipt_offset_ns": e["receipt_offset_ns"],
            "available_offset_ns": e["available_offset_ns"],
            "producer_offset_bounds_ns": e["producer_offset_bounds_ns"],
            "usable_at_cutoff": e["available_offset_ns"] <= SOURCE_CUTOFF,
        }
        for e in events
    }


def labels(intake):
    # The intake owns custodian decisions. An application Oracle by itself
    # confirms an outcome and supplies no independent review or partition.
    return {
        row["request_key"]: {
            "kind": "REVIEWED_NATIVE",
            "class": row["label"],
            "review_manifest_sha256": row["manifest_sha256"],
        }
        for row in intake["requests"]
        if row["label"] in {"BENIGN_VERIFIED", "ATTACK_VERIFIED"}
        and row["disposition"] == "REVIEW_FOR_LINEAGE"
    }


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    at = (len(values) - 1) * q
    left = int(at)
    return ordered[left] + (at - left) * (ordered[min(left + 1, len(ordered) - 1)] - ordered[left])


def summarize(rows):
    arms = {}
    for arm in ("ri_v2", "r20"):
        scores = [r[arm]["score"] for r in rows if r[arm]["status"] == "SCORED"]
        latency = [r[arm]["latency_ms"] for r in rows if r[arm]["status"] == "SCORED"]
        arms[arm] = {
            "states": dict(Counter(r[arm]["status"] for r in rows)),
            "reasons": dict(Counter(r[arm]["reason"] for r in rows if r[arm].get("reason"))),
            "score_min_p50_max": [percentile(scores, q) for q in (0, 0.5, 1)],
            "score_histogram": [sum(min(9, int(s * 10)) == i for s in scores) for i in range(10)],
            "inference_ms_p50_p95": [percentile(latency, q) for q in (0.5, 0.95)],
        }
    mask = Counter(r["source_mask_at_cutoff"] for r in rows)
    paired = [r for r in rows if all(r[a]["status"] == "SCORED" for a in arms)]
    return {
        "requests": len(rows),
        "models": arms,
        "source_masks": dict(mask),
        "requests_missing_at_least_one_source_at_cutoff": len(rows) - mask["NSA"],
        "distinct_uri76_at_cutoff": len(
            {r["uri76"]["sha256"] for r in rows if r["uri76"] is not None}
        ),
        "paired_scores": len(paired),
        "draft_threshold_disagreements": sum(
            r["r20"]["above_threshold"] != r["ri_v2"]["above_threshold"] for r in paired
        ),
        "oracle_verified": sum(r["oracle"]["verified"] for r in rows),
        "reviewed_native_labels": sum(r["label"]["kind"] == "REVIEWED_NATIVE" for r in rows),
        "independent_cohort_eligible": 0,
        "quality_metrics": "BLOCKED_PENDING_INDEPENDENT_TWO_CLASS_REVIEW_AND_LINEAGE",
    }

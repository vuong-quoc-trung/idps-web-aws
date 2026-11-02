#!/usr/bin/env python3
"""Private blind terminal review of pinned AI lab HTTP evidence.

This tool collects a human attestation. It cannot authenticate a person's
independence or approve training admission by itself.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, unquote

from idps_ai.common import (
    PipelineError,
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.data.evidence_campaign import FAMILIES, _source_lines, verify_blind_queue
from idps_ai.data.http_curation import require_development_source
from idps_ai.data.pcap_http_evidence import verify_body_evidence
from idps_ai.data.privacy import PII, SENSITIVE, safe_route
from idps_ai.data.snapshot import new_destination
from idps_ai.training.resources import resource_envelope

SLUG = re.compile(r"[A-Za-z0-9_.:-]{1,160}")


def _read_jsonl(path):
    rows = {}
    with Path(path).open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Oversized or partial private review record")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid private review record") from None
            rid = row.get("request_id")
            if not isinstance(rid, str) or rid in rows:
                raise PipelineError("Duplicate or missing review request ID")
            rows[rid] = row
    return rows


def load_registry(path):
    path = Path(path)
    registry = load_json(path)
    sha = registry.pop("registry_sha256", None)
    if sha != digest(registry) or registry.get("format_version") != 1:
        raise PipelineError("Review registry integrity failed")
    sources = registry.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 4096:
        raise PipelineError("Review registry requires 1–4096 independently pinned capture shards")
    ids = [s.get("id") for s in sources]
    if (
        len(set(ids)) != len(ids)
        or any(not SLUG.fullmatch(str(i)) for i in ids)
        or any(not SLUG.fullmatch(str(s.get("collector_id", ""))) for s in sources)
    ):
        raise PipelineError("Review registry source IDs are invalid")
    registry["registry_sha256"] = sha
    return registry


def load_source(registry, source_id, *, blind=False):
    source = next((s for s in registry["sources"] if s["id"] == source_id), None)
    if source is None:
        raise PipelineError("Unknown review source ID")
    paths = {
        k: Path(source[k])
        for k in ("plan", "lab", "capture", "queue", "assist", "collector_source")
    }
    three_source = Path(source["three_source"]) if source.get("three_source") else None
    body = Path(source["body_evidence"]) if source.get("body_evidence") else None
    for path in (
        *paths.values(),
        *([three_source] if three_source else []),
        *([body] if body else []),
    ):
        require_development_source(path)
    check = verify_blind_queue(
        paths["plan"],
        paths["lab"],
        paths["capture"],
        paths["queue"],
        paths["collector_source"],
        three_source,
    )
    assist_report = load_json(paths["assist"] / "report.json")
    facts_path = paths["assist"] / "review-assist.jsonl"
    proposals_path = paths["assist"] / "review-proposals.jsonl"
    if (
        assist_report.get("status") != "AUTOMATED_EVIDENCE_CHECKED_SEMANTIC_REVIEW_PENDING"
        or assist_report.get("counts", {}).get("requests") != check["requests"]
        or assist_report.get("blind_queue_sha256")
        != file_sha256(paths["queue"] / "blind-review.jsonl")
        or assist_report.get("assist_sha256") != file_sha256(facts_path)
        or assist_report.get("proposal_sha256") != file_sha256(proposals_path)
    ):
        raise PipelineError("Blind facts or proposal provenance changed")
    if body:
        verify_body_evidence(
            paths["plan"],
            paths["lab"],
            paths["capture"],
            paths["queue"],
            paths["collector_source"],
            three_source,
            body,
        )
    queue = _read_jsonl(paths["queue"] / "blind-review.jsonl")
    facts = _read_jsonl(facts_path)
    # A blind automated reviewer hashes this file but never parses collector
    # labels or syntax suggestions before forming its own proposal.
    proposals = {} if blind else _read_jsonl(proposals_path)
    bodies = _read_jsonl(body / "post-body-evidence.jsonl") if body else {}
    if (
        set(queue) != set(facts)
        or (not blind and set(queue) != set(proposals))
        or (body and set(queue) != set(bodies))
    ):
        raise PipelineError("Review artifacts do not cover the same request IDs")
    for rid, row in queue.items():
        if facts[rid].get("event_key") != row["event_key"] or (
            not blind and proposals[rid].get("event_key") != row["event_key"]
        ):
            raise PipelineError("Blind facts/proposals changed request binding")
    return source, paths, queue, facts, proposals, bodies


def _masked_query(value):
    try:
        pairs = parse_qsl(value or "", keep_blank_values=True, max_num_fields=32)
    except ValueError:
        raise PipelineError("Private query has too many fields for reviewer display") from None
    return [
        {
            "key": key if len(key) <= 40 and not PII.search(key) else "[redacted]",
            "value": "[redacted]" if SENSITIVE.search(key) else PII.sub("[redacted]", val[:256]),
        }
        for key, val in pairs
    ]


def show_case(paths, queue, facts, bodies, request_id, show_query=False):
    if request_id not in queue:
        raise PipelineError("Request ID is outside the pinned blind queue")
    row = queue[request_id]
    n = _source_lines(paths["lab"] / "access-lab.log", {request_id})[request_id]
    if len(n) != 1 or n[0][1] != row["source_line_sha256"]["nginx"]:
        raise PipelineError("Private Nginx request changed before reviewer view")
    nginx = n[0][0]
    body = bodies.get(request_id)
    return {
        "request_id": request_id,
        "campaign_id": row["campaign_id"],
        "timestamp_utc": row["timestamp_utc"],
        "method": row["http_method"],
        "route": safe_route(nginx.get("uri_path")),
        "query": _masked_query(nginx.get("query_string"))
        if show_query
        else "[hidden; use --show-query locally]",
        "status_code": nginx.get("status"),
        "source_hashes": row["source_line_sha256"],
        "flow_record_hashes": row.get("flow_record_sha256"),
        "post_body": (
            {
                "observed_in_pcap": True,
                "bytes": body["body_length"],
                "field_names": body["body_field_names"],
                "hmac_sha256": body["body_hmac_sha256"],
            }
            if body and row["http_method"] == "POST"
            else {"observed_in_pcap": False}
            if row["http_method"] == "POST"
            else None
        ),
        "automatic_facts": facts[request_id]["automatic_facts"],
        "exploit_outcome": "unknown; application oracle absent",
        "label": None,
    }


def _decision_path(review_dir, event_key):
    return Path(review_dir) / "decisions" / (event_key + ".json")


def initialize_review(output, registry, source, reviewer_id, collector_id):
    if (
        not SLUG.fullmatch(reviewer_id)
        or not SLUG.fullmatch(collector_id)
        or reviewer_id == collector_id
    ):
        raise PipelineError("Independent reviewer and collector IDs must be distinct slugs")
    output = Path(output)
    marker = output / "session.json"
    if output.exists():
        saved = load_json(marker)
        checksum = saved.pop("session_sha256", None)
        if (
            checksum != digest(saved)
            or saved.get("registry_sha256") != registry["registry_sha256"]
            or saved.get("source_id") != source["id"]
            or saved.get("reviewer_id") != reviewer_id
            or saved.get("collector_id") != collector_id
        ):
            raise PipelineError("Existing review session belongs to another binding")
        return output
    output = new_destination(output)
    output.mkdir(mode=0o700)
    (output / "decisions").mkdir(mode=0o700)
    session = {
        "format_version": 1,
        "registry_sha256": registry["registry_sha256"],
        "source_id": source["id"],
        "reviewer_id": reviewer_id,
        "collector_id": collector_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "independence": "self-attested by human; software cannot authenticate identity or semantic truth",
    }
    session["session_sha256"] = digest(session)
    atomic_json(marker, session)
    marker.chmod(0o600)
    return output


def record_decision(
    review_dir,
    row,
    reviewer_id,
    intent,
    family,
    reason,
    body_available,
    body_semantics_inspected=False,
):
    if intent not in ("benign", "attack", "unknown"):
        raise PipelineError("Reviewer must choose benign, attack or unknown")
    if intent == "attack" and family not in FAMILIES:
        raise PipelineError("Attack decision needs a supported family")
    if intent != "attack" and family is not None:
        raise PipelineError("Benign/unknown cannot carry an attack family")
    reason = PII.sub("[redacted]", reason.strip())
    if len(reason) < 20 or len(reason) > 1000:
        raise PipelineError("Independent review needs a 20–1000 character rationale")
    if row["http_method"] == "POST" and intent != "unknown" and not body_available:
        raise PipelineError("POST cannot receive a semantic label without observed body evidence")
    if row["http_method"] == "POST" and intent != "unknown" and not body_semantics_inspected:
        raise PipelineError(
            "POST semantic label requires separate human inspection of captured body"
        )
    item = {
        "format_version": 1,
        "event_key": row["event_key"],
        "request_id": row["request_id"],
        "campaign_id": row["campaign_id"],
        "timestamp_utc": row["timestamp_utc"],
        "source_line_sha256": row["source_line_sha256"],
        "reviewer_id": reviewer_id,
        "review_kind": "independent_human_attestation",
        "intent": intent,
        "attack_family": family if intent == "attack" else "benign" if intent == "benign" else None,
        "review_status": "approved" if intent != "unknown" else "pending",
        "exploit_outcome": "unknown",
        "reason": reason,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "body_evidence_available": body_available,
        "body_semantics_inspected_by_reviewer": bool(body_semantics_inspected),
        "training_eligible": False,
        "admission_note": "Human assertion requires later dataset/provenance/evidence-v2 audit and independent environment gates.",
    }
    path = _decision_path(review_dir, row["event_key"])
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(item, sort_keys=True).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def summarize_review(review_dir, registry, source, queue, bodies):
    review_dir = Path(review_dir)
    if not review_dir.exists():
        return {
            "status": "NO_INDEPENDENT_HUMAN_REVIEW_STARTED",
            "source_id": source["id"],
            "capture_requests": len(queue),
            "counts": {"benign": 0, "attack": 0, "unknown": 0, "unreviewed": len(queue)},
            "training_admission": 0,
        }
    session = load_json(review_dir / "session.json")
    checksum = session.pop("session_sha256", None)
    if (
        checksum != digest(session)
        or session.get("registry_sha256") != registry["registry_sha256"]
        or session.get("source_id") != source["id"]
        or not SLUG.fullmatch(str(session.get("reviewer_id", "")))
        or not SLUG.fullmatch(str(session.get("collector_id", "")))
        or session.get("reviewer_id") == session.get("collector_id")
    ):
        raise PipelineError("Review session integrity or independence attestation failed")
    counts = {"benign": 0, "attack": 0, "unknown": 0, "unreviewed": 0}
    for rid, row in queue.items():
        path = _decision_path(review_dir, row["event_key"])
        if not path.exists():
            counts["unreviewed"] += 1
            continue
        item = load_json(path)
        if (
            item.get("event_key") != row["event_key"]
            or item.get("request_id") != rid
            or item.get("campaign_id") != row["campaign_id"]
            or item.get("timestamp_utc") != row["timestamp_utc"]
            or item.get("source_line_sha256") != row["source_line_sha256"]
            or item.get("reviewer_id") != session["reviewer_id"]
            or item.get("review_kind") != "independent_human_attestation"
            or item.get("exploit_outcome") != "unknown"
            or item.get("training_eligible") is not False
            or item.get("body_evidence_available") != (rid in bodies)
        ):
            raise PipelineError("Human review decision changed request evidence binding")
        intent = item.get("intent")
        family = item.get("attack_family")
        if (
            intent not in ("benign", "attack", "unknown")
            or (intent == "attack" and family not in FAMILIES)
            or (intent == "benign" and family != "benign")
            or (intent == "unknown" and family is not None)
            or item.get("review_status") != ("pending" if intent == "unknown" else "approved")
        ):
            raise PipelineError("Human review intent/family is invalid")
        if row["http_method"] == "POST" and intent != "unknown" and rid not in bodies:
            raise PipelineError("POST label lacks captured body evidence")
        if (
            row["http_method"] == "POST"
            and intent != "unknown"
            and item.get("body_semantics_inspected_by_reviewer") is not True
        ):
            raise PipelineError("POST label lacks human inspection of captured body")
        if not isinstance(item.get("reason"), str) or not 20 <= len(item["reason"]) <= 1000:
            raise PipelineError("Human review rationale is missing")
        counts[intent] += 1
    extra = set((review_dir / "decisions").glob("*.json")) - {
        _decision_path(review_dir, row["event_key"]) for row in queue.values()
    }
    if extra:
        raise PipelineError("Review session contains decisions outside the pinned queue")
    return {
        "format_version": 1,
        "status": "INDEPENDENT_HUMAN_ATTESTATIONS_PENDING_DATASET_ADMISSION"
        if counts["unreviewed"] == 0
        else "HUMAN_REVIEW_INCOMPLETE",
        "source_id": source["id"],
        "reviewer_id": session["reviewer_id"],
        "counts": counts,
        "capture_requests": len(queue),
        "training_admission": 0,
        "limits": "Human ID is self-attested, not authenticated by software. Decisions need independent semantic validation and binding to an actual prepared dataset, provenance and evidence-v2 gate before admission.",
    }


def finalize_review(review_dir, registry, source, queue, bodies):
    """Pin human decision files without claiming their semantic truth or admission."""
    summary = summarize_review(review_dir, registry, source, queue, bodies)
    if summary["counts"]["unreviewed"]:
        raise PipelineError("Complete every request as benign, attack or unknown before finalizing")
    review_dir = Path(review_dir)
    path = review_dir / "review-summary.json"
    summary["registry_sha256"] = registry["registry_sha256"]
    summary["session_file_sha256"] = file_sha256(review_dir / "session.json")
    summary["decision_file_sha256"] = {
        row["event_key"]: file_sha256(_decision_path(review_dir, row["event_key"]))
        for row in queue.values()
    }
    summary["summary_sha256"] = digest(summary)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(summary) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return summary


BLIND_PATTERNS = {
    "sqli": (
        re.compile(r"\bunion\s+(?:all\s+)?select\b", re.I),
        re.compile(r"(?:'|\")\s*(?:or|and)\s+\d+\s*=\s*\d+", re.I),
        re.compile(r"\b(?:sleep|benchmark)\s*\(", re.I),
    ),
    "xss": (
        re.compile(r"<\s*script\b", re.I),
        re.compile(r"\bon(?:error|load)\s*=", re.I),
        re.compile(r"javascript\s*:", re.I),
    ),
    "path_traversal": (re.compile(r"(?:\.\./|\.\.\\|/etc/passwd|/\.env\b|/\.git\b)", re.I),),
    "cmd_injection": (
        re.compile(r"(?:;|&&|\|\||\$\(|`)\s*(?:id|whoami|cat|uname|curl|wget)\b", re.I),
    ),
}


def blind_syntax_triage(query):
    """Bounded private triage. A payload string is never a verified intent label."""
    if not isinstance(query, str) or len(query) > 8192:
        return [], "query_missing_or_oversized"
    try:
        pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=64)
    except ValueError:
        return [], "query_parse_ambiguous"
    candidates = []
    for key, value in pairs:
        if SENSITIVE.search(unquote(key)):
            continue
        text = value[:4096]
        for _ in range(2):
            text = unquote(text, errors="replace")[:4096]
        candidates.append(PII.sub("[redacted]", text))
    view = " ".join(candidates)
    families = [
        family
        for family, patterns in BLIND_PATTERNS.items()
        if any(pattern.search(view) for pattern in patterns)
    ]
    return families, "multiple_cues" if len(
        families
    ) > 1 else "single_cue" if families else "no_cue"


def blind_automated_record(source_id, row, fact, body, nginx, nginx_sha):
    """No runner proposal, status-to-label mapping, or model score enters this record."""
    if (
        nginx_sha != row["source_line_sha256"]["nginx"]
        or fact["event_key"] != row["event_key"]
        or nginx.get("request_id") != row["request_id"]
    ):
        raise PipelineError("Blind automated review source binding changed")
    cues, cue_state = blind_syntax_triage(nginx.get("query_string"))
    method = row["http_method"]
    body_observed = bool(body and body.get("body_observed_in_pcap")) if method == "POST" else None
    target = str(nginx.get("uri_path") or "/")
    if nginx.get("query_string"):
        target += "?" + nginx["query_string"]
    return {
        "format_version": 1,
        "event_key": row["event_key"],
        "request_id": row["request_id"],
        "campaign_id": row["campaign_id"],
        "source_id": source_id,
        "timestamp_utc": row["timestamp_utc"],
        "http_method": method,
        "safe_route": safe_route(nginx.get("uri_path")),
        "source_line_sha256": row["source_line_sha256"],
        "flow_record_sha256": row.get("flow_record_sha256"),
        "target_view_sha256": hashlib.sha256(target.encode()).hexdigest(),
        "objective_capture_integrity": "verified",
        "post_body_observed_in_pcap": body_observed,
        "query_visible_in_private_nginx": bool(nginx.get("query_string")),
        "syntax_triage": {
            "candidate_families": cues,
            "state": cue_state,
            "basis": "independent bounded lexical scan of observed private query; unverified hint only",
        },
        "attack_intent": "unknown",
        "exploit_outcome": "unknown",
        "oracle_verified_label": None,
        "ai_proposed_label": None,
        "independent_human_label": None,
        "review_state": "UNKNOWN",
        "training_eligible": False,
        "review_priority": "high"
        if cue_state == "multiple_cues" or (method == "POST" and not body_observed)
        else "medium"
        if cues
        else "normal",
    }


def automated_review(
    registry_path,
    registry,
    output,
    *,
    batch_size=128,
    max_new=None,
    resume=False,
    recover=False,
):
    """Batch/resume private objective review; no semantic promotion or admission."""
    if (
        not 1 <= batch_size <= 10000
        or (max_new is not None and max_new < 1)
        or (recover and not resume)
    ):
        raise PipelineError("Invalid bounded automatic review batch size")
    output = Path(output)
    registry_file_sha = file_sha256(registry_path)
    method_sha = file_sha256(__file__)
    meta = {
        "format_version": 1,
        "registry_sha256": registry["registry_sha256"],
        "registry_file_sha256": registry_file_sha,
        "method_file_sha256": method_sha,
        "source_count": len(registry["sources"]),
    }
    recovering_unsealed = False
    if resume:
        old_meta = load_json(output / "meta.json")
        db_path = output / "auto-review.sqlite"
        if old_meta != meta or not db_path.is_file():
            raise PipelineError("Auto review checkpoint, code or registry changed")
        report_path = output / "report.json"
        if report_path.is_file():
            old_report = load_json(report_path)
            report_sha = old_report.pop("report_sha256", None)
            if report_sha != digest(old_report):
                raise PipelineError("Auto review checkpoint, code or registry changed")
            db_matches = old_report.get("sqlite_sha256") == file_sha256(db_path)
            if not db_matches and (
                not recover
                or old_report.get("status") == "COMPLETE_OBJECTIVE_REVIEW_LABELS_UNKNOWN"
            ):
                raise PipelineError("Auto review checkpoint, code or registry changed")
            recovering_unsealed = not db_matches
        elif recover:
            recovering_unsealed = True
        else:
            raise PipelineError("Auto review checkpoint missing; use explicit --recover")
    else:
        output = new_destination(output)
        output.mkdir(mode=0o700)
        atomic_json(output / "meta.json", meta)
        (output / "meta.json").chmod(0o600)
    db_path = output / "auto-review.sqlite"
    if db_path.is_symlink():
        raise PipelineError("Auto review SQLite symlink is forbidden")
    db = sqlite3.connect(db_path)
    db_path.chmod(0o600)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS decisions (event_key TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, source_id TEXT NOT NULL, record_json TEXT NOT NULL, target_sha TEXT NOT NULL, cue_state TEXT NOT NULL)"
    )
    new_count = expected = matched = 0
    try:
        for source_info in registry["sources"]:
            source, paths, queue, facts, _, bodies = load_source(
                registry, source_info["id"], blind=True
            )
            expected += len(queue)
            nginx = _source_lines(paths["lab"] / "access-lab.log", set(queue))
            for rid, row in queue.items():
                if rid not in nginx or len(nginx[rid]) != 1:
                    raise PipelineError("Blind Nginx request missing or ambiguous")
                n, line_sha = nginx[rid][0]
                record = blind_automated_record(
                    source["id"], row, facts[rid], bodies.get(rid), n, line_sha
                )
                encoded = canonical_bytes(record).decode()
                prior = db.execute(
                    "SELECT record_json FROM decisions WHERE event_key=?", (row["event_key"],)
                ).fetchone()
                if prior:
                    if prior[0] != encoded:
                        raise PipelineError("Auto review resumed against changed request evidence")
                    matched += 1
                    continue
                if max_new is not None and new_count >= max_new:
                    continue
                try:
                    db.execute(
                        "INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                        (
                            row["event_key"],
                            rid,
                            source["id"],
                            encoded,
                            record["target_view_sha256"],
                            record["syntax_triage"]["state"],
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise PipelineError(
                        "Duplicate request identity across capture shards"
                    ) from None
                new_count += 1
                matched += 1
                if new_count % batch_size == 0:
                    db.commit()
        db.commit()
        processed = db.execute("SELECT count(*) FROM decisions").fetchone()[0]
        if processed > expected or processed != matched:
            raise PipelineError("Auto review has records outside the pinned queues")
        by_source = dict(db.execute("SELECT source_id,count(*) FROM decisions GROUP BY source_id"))
        by_cue = dict(db.execute("SELECT cue_state,count(*) FROM decisions GROUP BY cue_state"))
        distinct_target_views = db.execute(
            "SELECT count(DISTINCT target_sha) FROM decisions"
        ).fetchone()[0]
        repeated_target_view_requests = db.execute(
            "SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM decisions GROUP BY target_sha HAVING n>1)"
        ).fetchone()[0]
        cross_campaign_reused_views = db.execute(
            "SELECT count(*) FROM (SELECT target_sha FROM decisions GROUP BY target_sha HAVING count(DISTINCT json_extract(record_json,'$.campaign_id'))>1)"
        ).fetchone()[0]
        post_body_unobserved = db.execute(
            "SELECT count(*) FROM decisions WHERE json_extract(record_json,'$.http_method')='POST' AND json_extract(record_json,'$.post_body_observed_in_pcap')=0"
        ).fetchone()[0]
        post_body_observed = db.execute(
            "SELECT count(*) FROM decisions WHERE json_extract(record_json,'$.http_method')='POST' AND json_extract(record_json,'$.post_body_observed_in_pcap')=1"
        ).fetchone()[0]
        private_query_visible = db.execute(
            "SELECT count(*) FROM decisions WHERE json_extract(record_json,'$.query_visible_in_private_nginx')=1"
        ).fetchone()[0]
    finally:
        db.close()
    report = {
        "format_version": 1,
        "status": "COMPLETE_OBJECTIVE_REVIEW_LABELS_UNKNOWN"
        if processed == expected
        else "PARTIAL_RESUMABLE_OBJECTIVE_REVIEW",
        "registry_sha256": registry["registry_sha256"],
        "method_file_sha256": method_sha,
        "sqlite_sha256": file_sha256(db_path),
        "expected_requests": expected,
        "automatically_reviewed_requests": processed,
        "newly_processed_this_run": new_count,
        "recovered_unsealed_checkpoint": recovering_unsealed,
        "by_source": by_source,
        "syntax_triage": by_cue,
        "distinct_observed_target_views": distinct_target_views,
        "repeated_target_view_requests": repeated_target_view_requests,
        "cross_campaign_reused_target_views": cross_campaign_reused_views,
        "post_bodies_observed_in_pcap": post_body_observed,
        "post_bodies_unobserved": post_body_unobserved,
        "private_nginx_query_visible": private_query_visible,
        "verified_physical_request_ids_in_this_registry": processed,
        "objective_oracle_verified_labels": 0,
        "ai_proposed_labels": 0,
        "independently_reviewed_labels": 0,
        "unknown_intent_labels": processed,
        "training_admission": 0,
        "provenance_limit": "Dedup is request-ID scoped to this registry; repeated target views are not new behavior. Historical sealed data untouched.",
        "proposal_limit": "Syntax triage is a deterministic hint, not an AI model label, oracle, human attestation or ground truth. All intent/outcome labels remain unknown.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


def compare_after_blind(registry, auto_dir, output):
    """Unblind only after the independent automatic pass is frozen on disk."""
    auto_dir = Path(auto_dir)
    blind_report = load_json(auto_dir / "report.json")
    checksum = blind_report.pop("report_sha256", None)
    if (
        checksum != digest(blind_report)
        or blind_report.get("status") != "COMPLETE_OBJECTIVE_REVIEW_LABELS_UNKNOWN"
        or blind_report.get("registry_sha256") != registry["registry_sha256"]
        or blind_report.get("sqlite_sha256") != file_sha256(auto_dir / "auto-review.sqlite")
    ):
        raise PipelineError("Blind automatic review is incomplete or changed")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    db = sqlite3.connect(f"file:{auto_dir / 'auto-review.sqlite'}?mode=ro", uri=True)
    counts = Counter()
    proposal_shas = {}
    try:
        with (output / "unblind-comparison.jsonl").open("x") as stream:
            for source_info in registry["sources"]:
                source, paths, queue, _, proposals, _ = load_source(registry, source_info["id"])
                proposal_shas[source["id"]] = file_sha256(
                    paths["assist"] / "review-proposals.jsonl"
                )
                for rid, row in queue.items():
                    found = db.execute(
                        "SELECT request_id,source_id,record_json FROM decisions WHERE event_key=?",
                        (row["event_key"],),
                    ).fetchone()
                    if found is None or found[:2] != (rid, source["id"]):
                        raise PipelineError("Blind record missing before unblinding")
                    blind = json.loads(found[2])
                    proposal = proposals[rid]
                    claimed = proposal["collector_precommitted_intent"]
                    family = proposal["collector_precommitted_family"]
                    cues = blind["syntax_triage"]["candidate_families"]
                    if claimed not in ("attack", "benign"):
                        raise PipelineError("Collector proposal has an invalid intent")
                    signals = []
                    if claimed == "benign" and cues:
                        signals.append("syntax_cue_on_collector_benign_claim")
                    if claimed == "attack" and not cues:
                        signals.append("no_syntax_cue_on_collector_attack_claim")
                    if claimed == "attack" and cues and family not in cues:
                        signals.append("attack_family_cue_disagreement")
                    for signal in signals:
                        counts[signal] += 1
                    counts["requests_compared"] += 1
                    stream.write(
                        json.dumps(
                            {
                                "event_key": row["event_key"],
                                "request_id": rid,
                                "source_id": source["id"],
                                "blind_record_sha256": hashlib.sha256(
                                    found[2].encode()
                                ).hexdigest(),
                                "collector_claim": claimed,
                                "collector_family_claim": family,
                                "blind_syntax_cues": cues,
                                "triage_disagreements": signals,
                                "verified_label": None,
                                "training_eligible": False,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
        (output / "unblind-comparison.jsonl").chmod(0o600)
    finally:
        db.close()
    if counts["requests_compared"] != blind_report["automatically_reviewed_requests"]:
        raise PipelineError("Unblind comparison does not cover the frozen blind review")
    report = {
        "format_version": 1,
        "status": "UNBLINDED_TRIAGE_DISAGREEMENTS_NOT_LABELS",
        "blind_sqlite_sha256": blind_report["sqlite_sha256"],
        "blind_report_file_sha256": file_sha256(auto_dir / "report.json"),
        "collector_proposal_file_sha256": proposal_shas,
        "comparison_sha256": file_sha256(output / "unblind-comparison.jsonl"),
        "counts": dict(counts),
        "oracle_verified_labels": 0,
        "training_admission": 0,
        "limits": "Collector claims and syntax hints disagree or agree without proving semantic intent. This comparison cannot approve labels or change the blind record.",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sources")
    auto = sub.add_parser("auto")
    auto.add_argument("--output", required=True)
    auto.add_argument("--batch-size", type=int, default=128)
    auto.add_argument("--max-new", type=int)
    auto.add_argument("--resume", action="store_true")
    auto.add_argument("--recover", action="store_true")
    comparison = sub.add_parser("auto-compare")
    comparison.add_argument("--auto-dir", required=True)
    comparison.add_argument("--output", required=True)
    show = sub.add_parser("show")
    show.add_argument("--source", required=True)
    show.add_argument("--request-id", required=True)
    show.add_argument("--show-query", action="store_true")
    review = sub.add_parser("review")
    review.add_argument("--source", required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--output", required=True)
    finish = sub.add_parser("status")
    finish.add_argument("--source", required=True)
    finish.add_argument("--output", required=True)
    final = sub.add_parser("finalize")
    final.add_argument("--source", required=True)
    final.add_argument("--output", required=True)
    unblind = sub.add_parser("unblind")
    unblind.add_argument("--source", required=True)
    unblind.add_argument("--request-id", required=True)
    unblind.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        with resource_envelope(2, 2):
            registry = load_registry(args.registry)
            if args.command == "sources":
                print(json.dumps({"sources": [s["id"] for s in registry["sources"]]}))
                return
            if args.command == "auto":
                print(
                    json.dumps(
                        automated_review(
                            args.registry,
                            registry,
                            args.output,
                            batch_size=args.batch_size,
                            max_new=args.max_new,
                            resume=args.resume,
                            recover=args.recover,
                        ),
                        sort_keys=True,
                    )
                )
                return
            if args.command == "auto-compare":
                print(
                    json.dumps(
                        compare_after_blind(registry, args.auto_dir, args.output),
                        sort_keys=True,
                    )
                )
                return
            source, paths, queue, facts, proposals, bodies = load_source(registry, args.source)
            if args.command == "show":
                print(
                    json.dumps(
                        show_case(paths, queue, facts, bodies, args.request_id, args.show_query),
                        sort_keys=True,
                    )
                )
                return
            if args.command == "status":
                print(
                    json.dumps(
                        summarize_review(args.output, registry, source, queue, bodies),
                        sort_keys=True,
                    )
                )
                return
            if args.command == "finalize":
                print(
                    json.dumps(
                        finalize_review(args.output, registry, source, queue, bodies),
                        sort_keys=True,
                    )
                )
                return
            if args.command == "unblind":
                summarize_review(args.output, registry, source, queue, bodies)
                if args.request_id not in queue:
                    raise PipelineError("Request ID is outside the pinned blind queue")
                decision = _decision_path(args.output, queue[args.request_id]["event_key"])
                if not decision.is_file():
                    raise PipelineError("Record the independent blind decision before unblinding")
                print(
                    json.dumps(
                        {
                            "human_attestation": load_json(decision),
                            "collector_and_syntax_proposal_not_ground_truth": proposals[
                                args.request_id
                            ],
                            "next_step": "Investigate disagreement in a new immutable review session; never overwrite this decision or auto-promote a proposal.",
                        },
                        sort_keys=True,
                    )
                )
                return
            if not sys.stdin.isatty():
                raise PipelineError("Human review requires an interactive private terminal")
            print(
                "Reviewer must be a real person independent of the collector. This program cannot verify identity."
            )
            if input("Type I_REVIEW_INDEPENDENTLY to attest: ").strip() != "I_REVIEW_INDEPENDENTLY":
                raise PipelineError("Independent human attestation not provided")
            output = initialize_review(
                args.output, registry, source, args.reviewer_id, source["collector_id"]
            )
            for rid, row in queue.items():
                if _decision_path(output, row["event_key"]).exists():
                    continue
                print(
                    json.dumps(
                        show_case(paths, queue, facts, bodies, rid, show_query=True), sort_keys=True
                    )
                )
                choice = (
                    input("Decision [b=benign/a=attack/u=unknown/s=skip/q=quit]: ").strip().lower()
                )
                if choice == "q":
                    break
                if choice == "s":
                    continue
                if choice not in ("b", "a", "u"):
                    print("No decision saved; choose b/a/u/s/q.")
                    continue
                intent = {"b": "benign", "a": "attack", "u": "unknown"}[choice]
                family = (
                    input("Attack family [sqli/xss/path_traversal/cmd_injection]: ").strip()
                    if intent == "attack"
                    else None
                )
                reason = input("Independent semantic rationale (20–1000 chars; no secrets): ")
                body_inspected = False
                if row["http_method"] == "POST" and intent != "unknown" and rid in bodies:
                    body_inspected = (
                        input(
                            "Did you separately inspect the captured POST body in the private PCAP? [yes/no]: "
                        )
                        .strip()
                        .lower()
                        == "yes"
                    )
                try:
                    record_decision(
                        output,
                        row,
                        args.reviewer_id,
                        intent,
                        family,
                        reason,
                        rid in bodies,
                        body_inspected,
                    )
                except PipelineError as error:
                    print(str(error), file=sys.stderr)
                    continue
                print(
                    "Saved immutable decision. Collector proposal remains separate; no admission yet."
                )
            print(
                json.dumps(
                    summarize_review(output, registry, source, queue, bodies), sort_keys=True
                )
            )
    except PipelineError as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()

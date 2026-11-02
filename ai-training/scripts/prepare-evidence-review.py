#!/usr/bin/env python3
"""Create a blind, null-label review queue from verified AI lab captures."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data import evidence_campaign
from idps_ai.data.evidence_campaign import verify_blind_queue, verify_capture
from idps_ai.data.snapshot import new_destination
from idps_ai.training.resources import resource_envelope


def _syntax_cues(query):
    """Private triage hints only; deliberately not a label or ground truth."""
    values = parse_qs(query, keep_blank_values=True)
    text = " ".join(values.get("q", [])).lower()
    cues = []
    patterns = {
        "sqli": r"\b(?:union|select|or|and)\b|/\*|--",
        "xss": r"<[^>]+>|javascript:|\bon(?:load|error|toggle)\s*=",
        "path_traversal": r"\.\./|\.\.\\|%2e%2e|%2f",
        "cmd_injection": r"(?:;|&&|\|\||\$\(|`)\s*[a-z]",
    }
    for family, pattern in patterns.items():
        if re.search(pattern, text):
            cues.append(family)
    return cues


def prepare_assist(
    plan_dir, lab_dir, capture_dir, review_dir, output, collector_source, three_source_dir=None
):
    """Produce private request-bound triage; never approve intent or outcome."""
    verified = verify_blind_queue(
        plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir
    )
    capture_dir, lab_dir, review_dir = map(Path, (capture_dir, lab_dir, review_dir))
    with (capture_dir / "pending-evidence.jsonl").open() as stream:
        pending = {row["request_id"]: row for row in (json.loads(line) for line in stream)}
    with (review_dir / "blind-review.jsonl").open() as stream:
        queue = {row["request_id"]: row for row in (json.loads(line) for line in stream)}
    nginx = evidence_campaign._source_lines(lab_dir / "access-lab.log", set(pending))
    if len(queue) != verified["requests"] or len(pending) != verified["requests"]:
        raise PipelineError("Assist input does not cover the verified review queue")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    counts = {
        "requests": 0,
        "three_source": 0,
        "query_visible_private": 0,
        "syntax_cue_overlap": 0,
        "cue_on_collector_benign": 0,
        "cue_on_collector_attack": 0,
        "post_body_unobserved": 0,
    }
    with (
        (output / "review-assist.jsonl").open("x") as destination,
        (output / "review-proposals.jsonl").open("x") as proposals,
    ):
        for rid, item in pending.items():
            n, line_sha = nginx[rid][0]
            q = n.get("query_string") or ""
            cues = _syntax_cues(q)
            source_hashes = queue[rid]["source_line_sha256"]
            if line_sha != source_hashes["nginx"]:
                raise PipelineError("Assist Nginx line changed after blind review")
            record = {
                "request_id": rid,
                "event_key": queue[rid]["event_key"],
                "campaign_id": item["campaign_id"],
                "case_id": item["case_id"],
                "automatic_facts": {
                    "capture_and_queue_reverified": True,
                    "source_count": len(source_hashes),
                    "source_line_sha256": source_hashes,
                    "flow_record_sha256": queue[rid].get("flow_record_sha256"),
                    "query_present_in_private_nginx": bool(q),
                    "http_method": item["http_method"],
                    "status_code": item["status_code"],
                },
                "independent_review": {
                    "status": "pending",
                    "reviewer_id": None,
                    "semantic_evidence_sha256": None,
                    "decision": None,
                },
                "exploit_outcome": "unknown",
                "application_oracle_available": False,
                "training_eligible": False,
                "review_needs": [
                    "Independently inspect private request and authorized application context before reading collector claim.",
                    "POST body is not established by audit/Nginx/EVE HTTP headers; require separate body provenance if material.",
                    "Exploit outcome requires an application oracle; HTTP status and alert are insufficient.",
                ]
                if item["http_method"] == "POST"
                else [
                    "Independently inspect private request and authorized application context before reading collector claim.",
                    "Exploit outcome requires an application oracle; HTTP status and alert are insufficient.",
                ],
            }
            destination.write(json.dumps(record, sort_keys=True) + "\n")
            proposals.write(
                json.dumps(
                    {
                        "event_key": queue[rid]["event_key"],
                        "request_id": rid,
                        "collector_precommitted_intent": item["planned_intent"],
                        "collector_precommitted_family": item["planned_family"],
                        "syntax_cues_from_actual_query": cues,
                        "basis": "unblind only after independent request review; collector and syntax are not labels",
                        "reviewer_decision": None,
                        "training_eligible": False,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            counts["requests"] += 1
            counts["three_source"] += len(source_hashes) == 3
            counts["query_visible_private"] += bool(q)
            counts["syntax_cue_overlap"] += len(cues) > 1
            counts["cue_on_collector_benign"] += bool(cues) and item["planned_intent"] == "benign"
            counts["cue_on_collector_attack"] += bool(cues) and item["planned_intent"] == "attack"
            counts["post_body_unobserved"] += item["http_method"] == "POST"
    (output / "review-assist.jsonl").chmod(0o600)
    (output / "review-proposals.jsonl").chmod(0o600)
    result = {
        "format_version": 1,
        "status": "AUTOMATED_EVIDENCE_CHECKED_SEMANTIC_REVIEW_PENDING",
        "counts": counts,
        "capture_report_sha256": file_sha256(capture_dir / "report.json"),
        "blind_queue_sha256": file_sha256(review_dir / "blind-review.jsonl"),
        "three_source_report_sha256": (
            file_sha256(Path(three_source_dir) / "report.json") if three_source_dir else None
        ),
        "assist_sha256": file_sha256(output / "review-assist.jsonl"),
        "proposal_sha256": file_sha256(output / "review-proposals.jsonl"),
        "automatic_verified_labels": 0,
        "independently_reviewed_labels": 0,
        "training_admission": 0,
        "limits": "Blind facts and separate unblind proposals contain no independent semantic decision. Reviewers inspect private request context first; neither file may become training ground truth.",
    }
    atomic_json(output / "report.json", result)
    return result


def prepare(plan_dir, lab_dir, capture_dir, output, collector_source, three_source_dir=None):
    verified = verify_capture(plan_dir, lab_dir, capture_dir, collector_source)
    capture_dir = Path(capture_dir)
    report = load_json(capture_dir / "report.json")
    plan = load_json(Path(plan_dir) / "plan.json")
    if plan.get("case_profile") == "dev-oracle-observation-v1":
        oracle_path = capture_dir.parent / "oracle-verification/report.json"
        oracle = load_json(oracle_path)
        oracle_hash = oracle.pop("report_sha256", None)
        if (
            oracle_hash != evidence_campaign.digest(oracle)
            or oracle.get("status")
            != "EIGHT_REAL_REQUESTS_OBSERVED_DEVELOPMENT_ONLY_NO_INTENT_GROUND_TRUTH"
            or oracle.get("plan_sha256") != report.get("plan_sha256")
            or oracle.get("plan_file_sha256") != file_sha256(Path(plan_dir) / "plan.json")
            or oracle.get("capture_report_sha256") != file_sha256(capture_dir / "report.json")
            or oracle.get("three_source_report_sha256")
            != file_sha256(capture_dir.parent / "correlated/report.json")
            or oracle.get("response_evidence_sha256")
            != file_sha256(capture_dir / "response-evidence.jsonl")
            or oracle.get("before_oracle_sha256")
            != file_sha256(capture_dir.parent / "application-oracle-before.json")
            or oracle.get("after_oracle_sha256")
            != file_sha256(capture_dir.parent / "application-oracle.json")
            or oracle.get("cleanup_verification_sha256")
            != file_sha256(capture_dir.parent / "cleanup-verification.json")
            or oracle.get("physical_requests_verified") != verified["request_ids"]
            or oracle.get("intent_unknown") != verified["request_ids"]
            or oracle.get("formal_training_admission") != 0
            or oracle.get("independent_review") is not False
        ):
            raise PipelineError("Development observation lacks a verified zero-label oracle")
    elif report.get("application_workload_401") != 0:
        raise PipelineError("Auth-boundary-only workload cannot enter semantic review")
    three_source = (
        evidence_campaign.load_three_source_review_evidence(
            three_source_dir, capture_dir, verified["request_ids"]
        )
        if three_source_dir
        else None
    )
    output = new_destination(output)
    output.mkdir(mode=0o700)
    seen = set()
    max_clock_delta_seconds = 0.0
    with (
        (capture_dir / "pending-evidence.jsonl").open() as source,
        (output / "blind-review.jsonl").open("x") as destination,
    ):
        for line in source:
            item = json.loads(line)
            key = hashlib.sha256(
                (report["plan_sha256"] + ":" + item["request_id"]).encode()
            ).hexdigest()
            if key in seen:
                raise PipelineError("Duplicate review event")
            seen.add(key)
            try:
                clocks = [
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    for value in (
                        item["timestamp_utc"],
                        item["source_evidence"]["nginx_timestamp"],
                        item["source_evidence"]["student_timestamp"],
                    )
                ]
                if any(clock.tzinfo is None for clock in clocks):
                    raise ValueError
                delta = (max(clocks) - min(clocks)).total_seconds()
            except (KeyError, TypeError, ValueError):
                raise PipelineError("Request clocks lack a common timezone") from None
            if delta > 5:
                raise PipelineError("Correlated request clocks differ by more than 5 seconds")
            max_clock_delta_seconds = max(max_clock_delta_seconds, delta)
            eve = three_source.get(item["request_id"]) if three_source is not None else None
            if three_source is not None and (
                eve is None
                or eve.get("campaign_id") != item["campaign_id"]
                or eve.get("nginx_line_sha256")
                != item["source_evidence"]["nginx_access_line_sha256"]
                or eve.get("student_line_sha256")
                != item["source_evidence"]["student_audit_line_sha256"]
            ):
                raise PipelineError("Three-source evidence differs from pending request")
            source_hashes = {
                "nginx": item["source_evidence"]["nginx_access_line_sha256"],
                "student": item["source_evidence"]["student_audit_line_sha256"],
            }
            if eve is not None:
                source_hashes["eve_http"] = eve["eve_http_line_sha256"]
            destination.write(
                json.dumps(
                    {
                        "event_key": key,
                        "request_id": item["request_id"],
                        "campaign_id": item["campaign_id"],
                        "timestamp_utc": item["timestamp_utc"],
                        "http_method": item["http_method"],
                        "source_line_sha256": source_hashes,
                        "flow_record_sha256": (
                            eve["flow_record_sha256"] if eve is not None else None
                        ),
                        "intent": "unknown",
                        "attack_family": None,
                        "label": None,
                        "exploit_outcome": "unknown",
                        "review_status": "pending",
                        "training_eligible": False,
                        "reviewer_id": None,
                        "semantic_evidence_sha256": None,
                        "application_oracle_sha256": None,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    (output / "blind-review.jsonl").chmod(0o600)
    if len(seen) != verified["request_ids"]:
        raise PipelineError("Blind queue does not cover every verified request")
    critical_views = defaultdict(set)
    for campaign in plan["campaigns"]:
        for case in campaign["cases"]:
            if case["planned_intent"] == "attack" or case["scenario"] == "hard_negative_search":
                critical_views[case["target_sha256"]].add(campaign["campaign_id"])
    cross_campaign_critical_view_overlap = sum(
        len(groups) > 1 for groups in critical_views.values()
    )
    if cross_campaign_critical_view_overlap:
        raise PipelineError("Attack or hard-negative target repeats across campaigns")
    result = {
        "format_version": 1,
        "status": "BLIND_REVIEW_READY_NO_LABELS_APPROVED",
        "plan_sha256": report["plan_sha256"],
        "capture_report_sha256": file_sha256(capture_dir / "report.json"),
        "queue_sha256": file_sha256(output / "blind-review.jsonl"),
        "three_source_report_sha256": (
            file_sha256(Path(three_source_dir) / "report.json") if three_source_dir else None
        ),
        "requests": len(seen),
        "max_cross_source_clock_delta_seconds": max_clock_delta_seconds,
        "distinct_attack_and_hard_negative_targets": len(critical_views),
        "cross_campaign_critical_target_overlap": cross_campaign_critical_view_overlap,
        "approved_benign": 0,
        "approved_attack": 0,
        "new_training_admission": 0,
        "instructions": [
            (
                "A reviewer independent of the collector inspects the pinned private Nginx, Student and EVE/flow captures and the precommitted scenario plan; the blind queue contains no proposed label."
                if three_source is not None
                else "A reviewer independent of the collector inspects the pinned private Nginx and Student captures and the precommitted scenario plan; the blind queue contains no proposed label."
            ),
            "Record request-bound semantic intent evidence and reviewer identity; unknown stays unknown. Do not infer intent from response status, rule alerts or model scores.",
            "Exploit success/failure needs an application oracle. Traffic and audit logs alone support neither outcome.",
            "After review, create immutable dataset/provenance and evidence-v2 ledger, then run the existing corpus admission gate. Do not edit this queue in place.",
            "All current campaigns are development-only in one environment; a future independently authorized environment and sealed holdout remain required for generalization claims.",
        ],
    }
    atomic_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--lab", required=True)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--collector-source")
    parser.add_argument("--three-source")
    parser.add_argument("--assist-output")
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    try:
        with resource_envelope(2, 2):
            source = args.collector_source or evidence_campaign.__file__
            if args.verify_existing:
                result = verify_blind_queue(
                    args.plan, args.lab, args.capture, args.output, source, args.three_source
                )
            else:
                result = prepare(
                    args.plan, args.lab, args.capture, args.output, source, args.three_source
                )
            if args.assist_output:
                result = prepare_assist(
                    args.plan,
                    args.lab,
                    args.capture,
                    args.output,
                    args.assist_output,
                    source,
                    args.three_source,
                )
        print(json.dumps(result, sort_keys=True))
    except PipelineError as error:
        parser.exit(2, str(error) + "\n")

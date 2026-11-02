#!/usr/bin/env python3
"""Verify SOC-MLD review locators and prepare privacy-safe, unresolved dossiers.

No detector, time match, response status or publisher class is promoted to a label.
The raw capture remains in the local archive for a human reviewer to inspect.
"""

import argparse
import hashlib
import json
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256
from idps_ai.data.telemetry_audit import ACCESS
from idps_ai.training.resources import resource_envelope

EXPECTED_ARCHIVE = "66aafa96a69ab54ee061abbb69284444476919295f1b16985122283dae2b3054"
ACCESS_MEMBER = "SOC-MLD-v1.0/dataset/raw/access.log"
EVE_MEMBER = "SOC-MLD-v1.0/dataset/raw/eve.json"


def _event_key(index):
    return hashlib.sha256(
        f"{EXPECTED_ARCHIVE}:{ACCESS_MEMBER}:{index}:blind-review-v1".encode()
    ).hexdigest()


def _match_key(ip, method, target):
    # Used only in memory; neither client address nor target is exported.
    return hashlib.sha256(json.dumps([ip, method, target]).encode()).digest()


def review(archive, queue, audit_db, output, guard):
    if file_sha256(archive) != EXPECTED_ARCHIVE:
        raise PipelineError("SOC-MLD archive checksum mismatch")
    pending = [json.loads(line) for line in Path(queue).read_text().splitlines()]
    if len(pending) != 64 or len({r["event_key"] for r in pending}) != 64:
        raise PipelineError("Expected exactly 64 distinct pending review locators")
    by_index = {}
    for row in pending:
        index = row["source_line_index_0"]
        if (
            index in by_index
            or row["event_key"] != _event_key(index)
            or row["source_sha256"] != EXPECTED_ARCHIVE
            or row["source_member"] != ACCESS_MEMBER
            or row["review_status"] != "pending"
            or row["intent"] != "unknown"
            or row["label"] is not None
            or row["exploit_outcome"] != "unknown"
            or row["training_eligible"] is not False
        ):
            raise PipelineError("Pending queue binding or unknown-state violation")
        by_index[index] = row
    selected = {}
    with zipfile.ZipFile(archive) as z, z.open(ACCESS_MEMBER) as stream:
        for index, line in enumerate(stream):
            if index % 4096 == 0 and (guard.check() or guard.thermal_limit_reached):
                raise PipelineError("Resource or thermal guard reached")
            if index not in by_index:
                continue
            if len(line) > 2 * 1024**2:
                raise PipelineError("Oversized selected access line")
            row = by_index[index]
            if hashlib.sha256(line.rstrip(b"\r\n")).hexdigest() != row["observation_sha256"]:
                raise PipelineError("Raw access observation does not match review locator")
            match = ACCESS.fullmatch(line.decode("utf-8"))
            if match is None:
                raise PipelineError("Selected access line no longer parses")
            ip = line.split(b" ", 1)[0].decode("utf-8")
            selected[index] = (row, match, ip)
    if len(selected) != 64:
        raise PipelineError("Selected locators not present in source capture")

    # EVE can provide a candidate HTTP observation, but no immutable request ID
    # binds it to the access line. Matching by IP/URI/time is diagnostic only.
    lookups = defaultdict(list)
    for index, (_, match, ip) in selected.items():
        ts = datetime.strptime(match["time"], "%d/%b/%Y:%H:%M:%S %z").timestamp()
        lookups[_match_key(ip, match["method"], match["target"])].append((index, ts))
    candidates = Counter()
    status_agreement = Counter()
    eve_parse_errors = 0
    with zipfile.ZipFile(archive) as z, z.open(EVE_MEMBER) as stream:
        for index, line in enumerate(stream):
            if index % 4096 == 0 and (guard.check() or guard.thermal_limit_reached):
                raise PipelineError("Resource or thermal guard reached")
            if len(line) > 2 * 1024**2:
                raise PipelineError("Oversized EVE line")
            try:
                event = json.loads(line)
                if event.get("event_type") != "http":
                    continue
                http = event.get("http") or {}
                key = _match_key(event.get("src_ip"), http.get("http_method"), http.get("url"))
                hits = lookups.get(key, ())
                if not hits:
                    continue
                eve_ts = datetime.fromisoformat(
                    event["timestamp"].replace("Z", "+00:00")
                ).timestamp()
                for sample_index, access_ts in hits:
                    if abs(eve_ts - access_ts) <= 2:
                        candidates[sample_index] += 1
                        status_agreement[sample_index] += (
                            str(http.get("status")) == selected[sample_index][1]["status"]
                        )
            except (TypeError, ValueError, KeyError, AttributeError):
                eve_parse_errors += 1

    output = Path(output)
    output.mkdir(mode=0o700)
    dossiers = []
    profile = Counter()
    for index, (row, match, _) in sorted(selected.items()):
        target = match["target"]
        path, separator, query = target.partition("?")
        timestamp_utc = (
            datetime.strptime(match["time"], "%d/%b/%Y:%H:%M:%S %z")
            .astimezone(timezone.utc)
            .isoformat()
        )
        # Source URI, query, client address and user agent never leave the local archive.
        dossier = {
            "event_key": row["event_key"],
            "source_sha256": EXPECTED_ARCHIVE,
            "source_member": ACCESS_MEMBER,
            "source_line_index_0": index,
            "observation_sha256": row["observation_sha256"],
            "http_capture": {
                "timestamp_utc": timestamp_utc,
                "timestamp_source_offset": match["time"].rsplit(" ", 1)[-1],
                "method": match["method"],
                "status_code": int(match["status"]),
                "request_target_length": len(target),
                "path_depth": len([part for part in path.split("/") if part]),
                "query_present": bool(separator),
                "query_length": len(query),
                "percent_encoded_count": target.count("%"),
                "user_agent_present": bool(match["ua"]),
            },
            "eve_diagnostic": {
                "ip_method_target_within_2s_candidates": candidates[index],
                "status_agreeing_candidates": status_agreement[index],
                "binding": "unverified_no_shared_request_id",
            },
            "publisher_campaign": {
                "source_environment": "SOC-MLD cyber range",
                "scenario_id": None,
                "attack_instance_id": None,
                "binding": "unverified_operator_labels_have_no_request_id_or_timezone",
            },
            "decision": {
                "intent": "unknown",
                "attack_family": None,
                "exploit_outcome": "unknown",
                "review_status": "pending_human_confirmation",
                "training_eligible": False,
                "confidence": {
                    "source_archive_integrity": "verified_sha256",
                    "raw_http_observation": "verified_sha256",
                    "campaign": "unverified",
                    "intent": "unverified",
                    "exploit_outcome": "unverified",
                },
            },
            "human_confirmation_required": [
                "source_owner_request_to_scenario_or_attack_instance_binding",
                "independent_request_bound_intent_review_and_capture_provenance",
                "application_oracle_if_exploit_outcome_is_asserted",
                "immutable_dataset_and_provenance_binding_before_admission",
            ],
        }
        dossiers.append(dossier)
        profile["status_" + str(match["status"])[0] + "xx"] += 1
        profile["method_" + match["method"]] += 1
        profile["query_present"] += bool(separator)
        profile["eve_candidate_rows"] += bool(candidates[index])
        profile["eve_ambiguous_rows"] += candidates[index] > 1
    with (output / "pending-dossiers.jsonl").open("x") as f:
        for dossier in dossiers:
            f.write(json.dumps(dossier, sort_keys=True) + "\n")
    (output / "pending-dossiers.jsonl").chmod(0o600)

    db = sqlite3.connect(audit_db)
    try:
        shared = db.execute(
            "SELECT count(DISTINCT a.g) FROM curated a JOIN curated b ON a.g=b.g "
            "WHERE a.part='train' AND b.part='test' AND a.g IS NOT NULL AND a.g<>''"
        ).fetchone()[0]
        repeated_id = db.execute(
            "SELECT count(*) FROM (SELECT id FROM curated WHERE part IN ('train','test') "
            "AND id IS NOT NULL AND id<>'' GROUP BY id HAVING count(DISTINCT part)>1)"
        ).fetchone()[0]
        overlap_rows = db.execute(
            "SELECT count(*) FROM curated WHERE part IN ('train','test') AND g IN "
            "(SELECT g FROM curated WHERE part IN ('train','test') AND g IS NOT NULL "
            "AND g<>'' GROUP BY g HAVING count(DISTINCT part)>1)"
        ).fetchone()[0]
        overlap_by_role = {
            role: db.execute(
                "SELECT count(*) FROM curated WHERE part=? AND g IN "
                "(SELECT g FROM curated WHERE part IN ('train','test') AND g IS NOT NULL "
                "AND g<>'' GROUP BY g HAVING count(DISTINCT part)>1)",
                (role,),
            ).fetchone()[0]
            for role in ("train", "test")
        }
    finally:
        db.close()
    report = {
        "format_version": 1,
        "status": "PENDING_HUMAN_REVIEW_NO_ADMISSION",
        "source_sha256": EXPECTED_ARCHIVE,
        "queue_sha256": file_sha256(queue),
        "dossiers_sha256": file_sha256(output / "pending-dossiers.jsonl"),
        "pending_records": len(dossiers),
        "raw_http_sha256_verified": len(dossiers),
        "labels_approved": 0,
        "trusted_positive": 0,
        "trusted_benign": 0,
        "new_training_admission": 0,
        "verified_independent_campaigns": 0,
        "http_profile": dict(profile),
        "eve_parse_errors": eve_parse_errors,
        "original_split_leakage": {
            "shared_attack_instance_ids": shared,
            "rows_with_shared_attack_instance_ids": overlap_rows,
            "rows_with_shared_attack_instance_ids_by_role": overlap_by_role,
            "request_or_flow_ids_shared_train_test": repeated_id,
            "original_split_admissible": False,
        },
        "limits": [
            "Publisher operator labels have no request ID or timezone; scenario/intent cannot be joined by time alone.",
            "EVE HTTP joins are heuristic diagnostics, not independent ground truth or immutable request binding.",
            "No raw target, query, user agent, IP or payload is exported; reviewer reads the pinned private archive by locator.",
            "Response status and IDS signatures cannot establish intent or exploit success.",
        ],
        "formal_training_permitted": False,
    }
    atomic_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--audit-db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(2, 1) as (guard, resources):
        result = review(args.archive, args.queue, args.audit_db, args.output, guard)
    atomic_json(Path(args.output) / "resources.json", resources)
    print(json.dumps(result, sort_keys=True))

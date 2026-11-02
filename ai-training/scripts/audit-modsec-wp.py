#!/usr/bin/env python3
"""Stream the pinned ModSec-WP workbook for source quality, without payload export."""

import argparse
import hashlib
import json
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from idps_ai.common import PipelineError, atomic_json, file_sha256
from idps_ai.training.resources import resource_envelope

SHA256 = "f959c79e185502b03206f6fdeb29306a65571394c2f009dda503d43ba306d16d"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
FIELDS = (
    "transaction_id",
    "event_time",
    "remote_address",
    "request_host",
    "request_useragent",
    "request_line",
    "request_line_method",
    "request_line_url",
    "request_line_protocol",
    "response_protocol",
    "response_status",
    "action",
    "action_phase",
    "action_message",
    "message_type",
    "message_description",
    "message_rule_id",
    "message_rule_file",
    "message_msg",
    "message_severity",
    "message_accuracy",
    "message_maturity",
    "full_message_line",
    "request_body",
    "response_body",
    "label",
)


def _cell_value(cell):
    v = cell.find(NS + "v")
    if v is not None:
        return v.text or ""
    inline = cell.find(NS + "is")
    return "" if inline is None else "".join(inline.itertext())


def audit(workbook, output, guard):
    if file_sha256(workbook) != SHA256:
        raise PipelineError("Pinned ModSec-WP workbook checksum mismatch")
    output = Path(output)
    output.mkdir(mode=0o700)
    db = sqlite3.connect(output / "audit.sqlite")
    db.execute("PRAGMA cache_size=-8192")
    db.executescript(
        "CREATE TABLE tx(k BLOB PRIMARY KEY,label TEXT);"
        "CREATE TABLE views(k BLOB PRIMARY KEY,label TEXT);"
        "CREATE TABLE captured_events(k BLOB PRIMARY KEY,label TEXT);"
    )
    counts, labels, methods, statuses = Counter(), Counter(), Counter(), Counter()
    conflict_keys = {"tx": set(), "views": set(), "captured_events": set()}
    clocks = {"first": None, "last": None}
    try:
        with zipfile.ZipFile(workbook) as z:
            members = z.infolist()
            if (
                len(members) > 50
                or sum(m.file_size for m in members) > 600 * 1024**2
                or "xl/worksheets/sheet1.xml" not in z.namelist()
                or "xl/sharedStrings.xml" in z.namelist()
            ):
                raise PipelineError("Unexpected workbook members or expansion size")
            with z.open("xl/worksheets/sheet1.xml") as stream:
                for event, elem in ElementTree.iterparse(stream, events=("end",)):
                    if elem.tag != NS + "row":
                        continue
                    values = [_cell_value(cell) for cell in elem]
                    elem.clear()
                    if counts["rows_seen"] == 0:
                        if tuple(values) != FIELDS:
                            raise PipelineError("Unexpected ModSec-WP column contract")
                        counts["rows_seen"] += 1
                        continue
                    if counts["rows_seen"] > 110000 or len(values) != len(FIELDS):
                        raise PipelineError("ModSec-WP row or column budget exceeded")
                    row = dict(zip(FIELDS, values))
                    counts["rows_seen"] += 1
                    if counts["rows_seen"] % 4096 == 0:
                        if guard.check() or guard.thermal_limit_reached:
                            raise PipelineError("Resource or thermal guard reached")
                        db.commit()
                    labels[row["label"] or "missing"] += 1
                    methods[row["request_line_method"] or "missing"] += 1
                    statuses[row["response_status"] or "missing"] += 1
                    counts["missing_transaction_id"] += not bool(row["transaction_id"])
                    counts["missing_event_time"] += not bool(row["event_time"])
                    counts["missing_request_url"] += not bool(row["request_line_url"])
                    counts["request_body_present"] += bool(row["request_body"])
                    counts["response_body_present"] += bool(row["response_body"])
                    counts["waf_rule_id_present"] += bool(row["message_rule_id"])
                    counts["waf_rule_id_normal"] += row["label"].lower() == "normal" and bool(
                        row["message_rule_id"]
                    )
                    counts["waf_rule_id_attack"] += row["label"].lower() != "normal" and bool(
                        row["message_rule_id"]
                    )
                    timestamp = row["event_time"]
                    if timestamp:
                        try:
                            try:
                                instant = datetime.strptime(timestamp, "%d/%b/%Y:%H:%M:%S %z")
                            except ValueError:
                                instant = datetime.strptime(timestamp, "%d/%b/%Y:%H:%M:%S.%f %z")
                        except ValueError:
                            counts["invalid_event_time"] += 1
                        else:
                            counts["event_year_" + str(instant.year)] += 1
                            clocks["first"] = min(clocks["first"] or instant, instant)
                            clocks["last"] = max(clocks["last"] or instant, instant)
                    for table, payload in (
                        ("tx", row["transaction_id"]),
                        (
                            "views",
                            json.dumps(
                                [
                                    row["request_line_method"],
                                    row["request_line_url"],
                                    row["request_body"],
                                ],
                                separators=(",", ":"),
                            ),
                        ),
                        (
                            "captured_events",
                            json.dumps(
                                [
                                    row["transaction_id"],
                                    row["event_time"],
                                    row["request_line_method"],
                                    row["request_line_url"],
                                    row["request_body"],
                                    row["response_status"],
                                ],
                                separators=(",", ":"),
                            ),
                        ),
                    ):
                        if table == "tx" and not payload:
                            continue
                        key = hashlib.sha256(payload.encode()).digest()
                        prior = db.execute(
                            f"SELECT label FROM {table} WHERE k=?", (key,)
                        ).fetchone()
                        if prior is None:
                            db.execute(f"INSERT INTO {table} VALUES(?,?)", (key, row["label"]))
                        else:
                            counts["duplicate_" + table] += 1
                            counts["conflicting_" + table + "_labels"] += prior[0] != row["label"]
                            if prior[0] != row["label"]:
                                conflict_keys[table].add(key)
        db.commit()
        counts["distinct_transaction_ids"] = db.execute("SELECT count(*) FROM tx").fetchone()[0]
        counts["distinct_request_representations"] = db.execute(
            "SELECT count(*) FROM views"
        ).fetchone()[0]
        counts["distinct_captured_event_keys"] = db.execute(
            "SELECT count(*) FROM captured_events"
        ).fetchone()[0]
        for kind, keys in conflict_keys.items():
            counts["distinct_conflicting_" + kind + "_keys"] = len(keys)
        db.execute("CREATE TABLE conflicting_tx(k BLOB PRIMARY KEY)")
        db.executemany(
            "INSERT INTO conflicting_tx VALUES(?)", [(key,) for key in conflict_keys["tx"]]
        )
        distinct_consistent_labels = dict(
            db.execute(
                "SELECT label,count(*) FROM tx WHERE k NOT IN (SELECT k FROM conflicting_tx) GROUP BY label"
            ).fetchall()
        )
    finally:
        db.close()
    report = {
        "format_version": 1,
        "status": "SOURCE_AUDITED_LABEL_EVIDENCE_PENDING",
        "doi": "10.5281/zenodo.21872151",
        "license": "CC BY 4.0 (official Zenodo API metadata)",
        "workbook_sha256": SHA256,
        "rows": counts["rows_seen"] - 1,
        "counts": dict(counts),
        "publisher_labels": dict(labels),
        "distinct_transaction_ids_without_label_conflict_by_publisher_label": distinct_consistent_labels,
        "methods": dict(methods),
        "status_codes": dict(statuses),
        "timestamp_range_utc": {
            key: value.isoformat() if value is not None else None for key, value in clocks.items()
        },
        "verified_independent_campaigns": 0,
        "trusted_positive": 0,
        "trusted_benign": 0,
        "new_training_admission": 0,
        "training_blockers": [
            "Only one WordPress testbed; no verified independent campaign keys in workbook.",
            "Publisher describes mixed time/scenario/regex/manual labeling, without per-row label-basis evidence.",
            "ModSecurity rule/action and response fields are annotations, not causal request features or ground truth.",
            "Repeated transaction IDs, event keys and request views need source-owner explanation and group-aware partitioning.",
            "Raw bodies may contain sensitive data; no raw values were exported in this audit.",
        ],
        "formal_training_permitted": False,
    }
    atomic_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(2, 2) as (guard, resources):
        result = audit(args.workbook, args.output, guard)
    atomic_json(Path(args.output) / "resources.json", resources)
    print(json.dumps(result, sort_keys=True))

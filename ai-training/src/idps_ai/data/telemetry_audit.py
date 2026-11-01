"""Read-only SOC-MLD audit. Published telemetry is not request-level ground truth.

No publisher code is executed; no payload, IP, UA, cookie or body is exported.
Curated features and labels are inspected as provenance facts, never model input.
"""

import csv
import hashlib
import io
import json
import re
import sqlite3
import stat
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import PurePosixPath

from idps_ai.common import PipelineError, atomic_json, file_sha256
from idps_ai.data.http_curation import require_development_source
from idps_ai.data.snapshot import new_destination

PREFIX = "SOC-MLD-v1.0/"
ACCESS = re.compile(
    r'^\S+ - \S+ \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) '
    r'(?P<target>\S+) HTTP/(?:1\.[01]|2(?:\.0)?)" (?P<status>[1-5]\d{2}) '
    r'(?P<bytes>\d+|-)(?: "(?:[^"\\]|\\.)*" "(?P<ua>(?:[^"\\]|\\.)*)")?\s*$'
)


def _lines(archive, name):
    with archive.open(PREFIX + name) as stream:
        for index in range(300001):
            line = stream.readline(2 * 1024 * 1024 + 1)
            if not line:
                return
            if index == 300000 or len(line) > 2 * 1024 * 1024:
                raise PipelineError("Telemetry member row or line budget exceeded")
            try:
                yield line.decode("utf-8")
            except UnicodeError:
                raise PipelineError("Invalid telemetry UTF-8; source content omitted") from None


def _csv(archive, name):
    # Small publisher label/curated CSVs only. HTTP payloads are streamed separately.
    with archive.open(PREFIX + name) as stream:
        yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8", newline=""))


def audit_telemetry_bundle(archive, output, expected_sha256, guard=None):
    """Inventory request observations, label evidence and original split metadata.

    The caller must independently verify publisher identity and license. This
    structural audit cannot promote a source or establish label correctness.
    """
    require_development_source(archive)
    if file_sha256(archive) != expected_sha256:
        raise PipelineError("Telemetry source checksum mismatch")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    counts, methods, events, label_counts, status_counts = (Counter() for _ in range(5))
    clocks, curated, hashes = {}, {}, {}
    db = sqlite3.connect(output / "audit.sqlite")
    db.execute("PRAGMA cache_size=-8192")
    db.executescript(
        "CREATE TABLE observations(k TEXT PRIMARY KEY); CREATE TABLE views(k TEXT PRIMARY KEY); CREATE TABLE curated(part TEXT,id TEXT,g TEXT,t REAL,label TEXT);"
    )
    try:
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if len(members) > 200 or sum(m.file_size for m in members) > 200 * 1024**2:
                raise PipelineError("Telemetry archive expansion budget exceeded")
            names = set()
            for member in members:
                path = PurePosixPath(member.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in member.filename
                    or stat.S_ISLNK(member.external_attr >> 16)
                    or member.flag_bits & 1
                    or member.filename in names
                ):
                    raise PipelineError("Unsafe or repeated telemetry archive member")
                names.add(member.filename)
            for name in (
                "dataset/raw/access.log",
                "dataset/raw/eve.json",
                "dataset/raw/dataset_labels.csv",
                "code/extract_features.py",
                "LICENSE",
                "README.md",
            ):
                if PREFIX + name not in names:
                    raise PipelineError("Missing telemetry provenance member")
            member_hashes = {}
            for member in members:
                if member.is_dir():
                    continue
                h = hashlib.sha256()
                with source.open(member) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                member_hashes[member.filename] = h.hexdigest()
            atomic_json(output / "member-hashes.json", member_hashes)
            for index, line in enumerate(_lines(source, "dataset/raw/access.log")):
                if guard is not None and index % 4096 == 0:
                    if guard.check() or guard.thermal_limit_reached:
                        raise PipelineError("Telemetry audit resource or thermal guard reached")
                counts["raw_access_lines"] += 1
                match = ACCESS.fullmatch(line)
                if not match:
                    counts["unparsed_access_lines"] += 1
                    continue
                try:
                    ts = datetime.strptime(match["time"], "%d/%b/%Y:%H:%M:%S %z").timestamp()
                except ValueError:
                    counts["invalid_access_timestamp"] += 1
                    continue
                methods[match["method"]] += 1
                for table, value in (
                    ("observations", line.rstrip("\r\n")),
                    (
                        "views",
                        json.dumps(
                            [match["method"], match["target"], match["ua"] or ""],
                            separators=(",", ":"),
                        ),
                    ),
                ):
                    before = db.total_changes
                    db.execute(
                        f"INSERT OR IGNORE INTO {table} VALUES(?)",
                        (hashlib.sha256(value.encode()).hexdigest(),),
                    )
                    if table == "observations" and before == db.total_changes:
                        counts["repeated_complete_log_observations"] += 1
                counts["parseable_http_observations"] += 1
                clocks["http_min_utc"] = min(clocks.get("http_min_utc", ts), ts)
                clocks["http_max_utc"] = max(clocks.get("http_max_utc", ts), ts)
                if index % 4096 == 0:
                    db.commit()
            scenarios = set()
            for row in _csv(source, "dataset/raw/dataset_labels.csv"):
                counts["operator_label_rows"] += 1
                label_counts[row.get("label") or "missing"] += 1
                status_counts[row.get("status") or "missing"] += 1
                scenarios.add(row.get("scenario_id"))
                try:
                    clock = datetime.fromisoformat(row.get("timestamp", ""))
                    counts["operator_naive_clock_rows"] += clock.tzinfo is None
                except ValueError:
                    counts["operator_invalid_clock_rows"] += 1
                counts["operator_rows_with_request_id"] += bool(row.get("request_id"))
            counts["operator_scenario_ids"] = len(scenarios - {None, ""})
            for line in _lines(source, "dataset/raw/eve.json"):
                counts["eve_rows"] += 1
                try:
                    row = json.loads(line)
                    kind = row.get("event_type")
                    if not isinstance(kind, str) or len(kind) > 64:
                        raise ValueError()
                    events[kind] += 1
                except (ValueError, AttributeError):
                    counts["unparsed_eve_rows"] += 1
            for part in ("dataset", "train", "test"):
                families, sources = Counter(), Counter()
                for row in _csv(source, "dataset/curated/" + part + ".csv"):
                    families[row.get("label") or "missing"] += 1
                    sources[row.get("source") or "missing"] += 1
                    try:
                        ts = float(row["timestamp"])
                    except (ValueError, KeyError):
                        raise PipelineError("Invalid curated telemetry timestamp") from None
                    db.execute(
                        "INSERT INTO curated VALUES(?,?,?,?,?)",
                        (
                            part,
                            row.get("request_id") or row.get("flow_id"),
                            row.get("attack_instance_id"),
                            ts,
                            row.get("label"),
                        ),
                    )
                curated[part] = {
                    "rows": sum(families.values()),
                    "labels": dict(families),
                    "source_types": dict(sources),
                }
            # Static evidence points only. These are not universal code-verification claims.
            code = source.read(PREFIX + "code/extract_features.py").decode("utf-8")
            needles = {
                "time_proximity_label_assignment": "lbl = consume_label(label_queue, ts, L7_VALID, tol=30.0)",
                "payload_rule_fallback": 'lbl = label_l7_payload(pf, rec["path"], rec["query"], rec["ua"])',
                "unmatched_payload_normal_fallback": 'return "NORMAL"',
                "future_suricata_window": "bisect.bisect_right(self._a_ts[ip], ts+w)",
                "signature_based_network_labels": 'lbl = label_from_suricata(al["signature"], al["proto"])',
            }
            for name, needle in needles.items():
                hashes[name] = [i for i, line in enumerate(code.splitlines(), 1) if needle in line]
        db.commit()
        counts["distinct_complete_log_observations"] = db.execute(
            "SELECT count(*) FROM observations"
        ).fetchone()[0]
        counts["distinct_method_target_user_agent_representations"] = db.execute(
            "SELECT count(*) FROM views"
        ).fetchone()[0]
        overlap = db.execute(
            "SELECT count(DISTINCT a.g) FROM curated a JOIN curated b ON a.g=b.g WHERE a.part='train' AND b.part='test'"
        ).fetchone()[0]
        period = {
            p: db.execute("SELECT min(t),max(t) FROM curated WHERE part=?", (p,)).fetchone()
            for p in ("train", "test")
        }
    finally:
        db.close()
    result = {
        "format_version": 1,
        "archive_sha256": expected_sha256,
        "status": "QUARANTINED_PENDING_REQUEST_BOUND_INTENT_REVIEW",
        "counts": dict(counts),
        "http_methods": dict(methods),
        "clocks": clocks,
        "eve_types": dict(events),
        "operator_labels": dict(label_counts),
        "operator_statuses_not_exploit_success": dict(status_counts),
        "curated": curated,
        "original_split": {"shared_attack_instance_ids": overlap, "time_ranges": period},
        "publisher_code_evidence_line_numbers": hashes,
        "request_level_verified_labels": 0,
        "verified_physical_requests": None,
        "supervised_training_eligible": 0,
        "formal_training_permitted": False,
        "label_state_for_new_raw_observations": "unknown",
        "limits": [
            "Exact log lines and partial method/URI/UA representations are not independently verified physical request identities.",
            "Publisher curated labels mix temporal attribution and payload-rule fallback; no per-row label-basis trail is supplied. Nonmatches cannot be benign truth.",
            "Operator timestamps without timezone and missing request IDs cannot be reliably linked by a guessed offset or nearest timestamp.",
            "Precomputed alert/signature features, future +/-60s context, and complete-session aggregates are not accepted causal model inputs.",
            "A single scripted external cyber range is a different publisher environment, not broad production diversity. No model training/evaluation, feature projection, replays or final holdout designation here.",
        ],
        "member_hashes_sha256": file_sha256(output / "member-hashes.json"),
        "index_sha256": file_sha256(output / "audit.sqlite"),
    }
    atomic_json(output / "report.json", result)
    return result

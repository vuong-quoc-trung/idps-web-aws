"""Publisher-labeled real HTTP audit, never automatic supervised admission.

SR-BH2020 is partial HTTP from one WordPress environment, not three-source EVE.
CAPEC labels remain targets only; contradictory or absent labels stay unknown.
Bodies/cookies/IP/headers are never returned or logged, nor used as features.
"""

import csv
import hashlib
import hmac
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, file_sha256
from idps_ai.data.dataset import write_rows
from idps_ai.data.snapshot import new_destination
from idps_ai.features.request_view import fingerprint, project_request

REQUIRED = {"timestamp", "src_ip", "request_http_method", "request_http_request", "000 - Normal"}
KNOWN_FAMILIES = {
    "66": "sqli",
    "126": "path_traversal",
    "88": "cmd_injection",
    "248": "cmd_injection",
}
SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("natural_key", pa.string()),
        ("client_key", pa.string()),
        ("timestamp", pa.float64()),
        ("timestamp_state", pa.string()),
        ("label", pa.int8()),
        ("attack_family", pa.string()),
        ("published_capec", pa.list_(pa.string())),
        ("label_state", pa.string()),
        ("body_present", pa.bool_()),
        ("numbers_json", pa.string()),
        ("projection_state", pa.string()),
    ]
)


def iter_srbh(stream, identity_key, source_sha256, audit=None, project_fraction=1.0):
    if len(identity_key) < 32 or not 0 < project_fraction <= 1:
        raise PipelineError("Independent identity key and valid sampling fraction required")
    csv.field_size_limit(1024**2)
    reader = csv.DictReader(stream, strict=True)
    if not REQUIRED <= set(reader.fieldnames or []):
        raise PipelineError("SRBH publisher schema mismatch")
    label_keys = [k for k in reader.fieldnames if re.match(r"^\d+ - ", k)]
    attacks = [k for k in label_keys if k != "000 - Normal"]
    if not attacks:
        raise PipelineError("SRBH attack label schema missing")

    def mac(value):
        return hmac.new(identity_key, value.encode(), hashlib.sha256).hexdigest()

    for index, row in enumerate(reader):
        if index >= 1_000_000 or None in row or any(v is None for v in row.values()):
            raise PipelineError("SRBH malformed/oversized source; raw record omitted")
        if any(row[k] not in ("0", "1") for k in label_keys):
            raise PipelineError("Unrecognized publisher label encoding; never assume benign")
        active = [k.split(" - ", 1)[0] for k in attacks if row[k] == "1"]
        normal = row["000 - Normal"] == "1"
        state = "consistent_publisher_annotation"
        label = 0 if normal and not active else 1 if active and not normal else None
        if label is None:
            state = "conflicting_publisher_labels" if normal else "missing_publisher_labels"
        mapped = {KNOWN_FAMILIES.get(k) for k in active}
        family = (
            "benign"
            if label == 0
            else next(iter(mapped))
            if label == 1 and len(mapped) == 1 and None not in mapped
            else None
        )
        timestamp = None
        if row["timestamp"]:
            try:
                timestamp = datetime.strptime(row["timestamp"], "%d/%b/%Y:%H:%M:%S %z").timestamp()
            except ValueError:
                raise PipelineError("Invalid source timestamp; never invent a clock") from None
        identity = mac(f"{source_sha256}:record:{index}")
        natural = mac(
            json.dumps(
                {k: v for k, v in row.items() if k not in label_keys},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        selected = int(identity[:8], 16) < project_fraction * (2**32)
        numbers = None
        projection = "not_in_fixed_hash_sample"
        if selected:
            try:
                if not row["request_http_request"] or not row["request_http_method"]:
                    raise PipelineError("Missing source URI/method")
                numbers = project_request(row["request_http_request"], row["request_http_method"])[
                    "numbers"
                ]
                projection = "available"
            except PipelineError:
                projection = "unavailable_URI_contract"
        result = {
            "event_key": identity,
            "natural_key": natural,
            "client_key": mac("client:" + row["src_ip"]) if row["src_ip"].strip() else None,
            "timestamp": timestamp,
            "timestamp_state": "observed" if timestamp is not None else "missing",
            "label": label,
            "attack_family": family,
            "published_capec": active,
            "label_state": state,
            "body_present": bool(row.get("request_body", "").strip()),
            "numbers": numbers,
            "projection_state": projection,
        }
        if audit is not None:
            audit(result, selected)
        if selected:
            yield result


def import_srbh(source, download_manifest, output, identity_key, sample_fraction=0.1):
    manifest = json.loads(Path(download_manifest).read_text())
    if (
        manifest.get("doi") != "10.7910/DVN/OGOIXX"
        or manifest.get("license") != "CC0 1.0"
        or manifest.get("md5") != "173ec515308bdce5aec19cfd5b792596"
        or manifest.get("sha256")
        != "9c73c90ce6564ae48b14f7179cd864d037a6a130ef69c68c1626ec5d7ce4a910"
        or file_sha256(source) != manifest.get("sha256")
        or Path(source).stat().st_size != 436437661
    ):
        raise PipelineError("Pinned original real-HTTP source integrity/license mismatch")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    db = sqlite3.connect(output / "audit.sqlite")
    db.execute("PRAGMA cache_size=-8192")
    db.execute("CREATE TABLE observations(k TEXT PRIMARY KEY,n INTEGER,labels INTEGER)")
    count = 0
    selected_count = 0
    labels = Counter()
    days = Counter()
    states = Counter()
    capec = Counter()
    projections = Counter()
    body = Counter()
    earliest = float("inf")
    latest = float("-inf")

    def audit(r, selected):
        nonlocal count, selected_count, earliest, latest
        count += 1
        selected_count += int(selected)
        labels[str(r["label"])] += 1
        states[r["label_state"]] += 1
        days[
            datetime.fromtimestamp(r["timestamp"], timezone.utc).strftime("%Y-%m-%d")
            if r["timestamp"] is not None
            else "MISSING"
        ] += 1
        capec.update(r["published_capec"])
        body[str(r["label"])] += int(r["body_present"])
        if selected:
            projections[r["projection_state"]] += 1
        if r["timestamp"] is not None:
            earliest = min(earliest, r["timestamp"])
            latest = max(latest, r["timestamp"])
        bit = 1 if r["label"] == 0 else 2 if r["label"] == 1 else 4
        db.execute(
            "INSERT INTO observations VALUES(?,1,?) ON CONFLICT(k) DO UPDATE SET n=n+1,labels=labels|?",
            (r["natural_key"], bit, bit),
        )
        if count % 4096 == 0:
            db.commit()

    def records():
        with Path(source).open(newline="", encoding="utf-8-sig") as stream:
            for r in iter_srbh(stream, identity_key, manifest["sha256"], audit, sample_fraction):
                yield {k: v for k, v in r.items() if k != "numbers"} | {
                    "numbers_json": json.dumps(r["numbers"], sort_keys=True, separators=(",", ":"))
                    if r["numbers"] is not None
                    else None
                }

    write_rows(output / "sample.parquet", records(), SCHEMA)
    db.commit()
    unique = db.execute("SELECT count(*) FROM observations").fetchone()[0]
    conflicts = db.execute(
        "SELECT count(*) FROM observations WHERE labels&1 AND labels&2"
    ).fetchone()[0]
    report = {
        "format_version": 1,
        "source": "SR-BH2020",
        "source_sha256": manifest["sha256"],
        "source_doi": manifest["doi"],
        "license": manifest["license"],
        "publisher_records": count,
        "natural_observation_identities": unique,
        "duplicate_observation_records": count - unique,
        "same_observation_cross_label_groups": conflicts,
        "labels": dict(labels),
        "label_states": dict(states),
        "published_capec_counts": dict(capec),
        "body_present_by_label": dict(body),
        "dates": dict(days),
        "time_range": [earliest, latest],
        "sample_records": selected_count,
        "sample_fraction": sample_fraction,
        "sampling": "HMAC of physicalrecord identity; not label- or prediction-selected",
        "sample_projection": dict(projections),
        "identity_key_fingerprint": hashlib.sha256(identity_key).hexdigest(),
        "projection_sha256": fingerprint(),
        "files": {"sample.parquet": file_sha256(output / "sample.parquet")},
        "training_admitted": False,
        "independent_human_review": False,
        "full_source_count_matches_publisher": count == 907814,
        "limits": [
            "Single WordPress environment with real Internettraffic; no Student/flow/context invented",
            "Publisher labels use ModSecurity plus manual/semi-automatic review; not our independent adjudication",
            "Codeinjection242 is not guessed XSS; mixed/unmapped family staysunknown",
            "URI-only view misses body/header attacks; full sampled cohort primary, no selective easy subset",
            "Original source private; output contains no rawquery/body/cookie/host/IP/header strings",
            "No training/calibration/selection uses this new source in the current frozen study",
        ],
    }
    atomic_json(output / "manifest.json", report)
    db.close()
    return report


def audit_http_zip(path, max_bytes=64 * 1024**2):
    """Inspect public access-log archives without extraction or inferred labels.

    Logs repeated by rotation are one observation, not new HTTP requests. Rule
    YAML is counted as provenance only: nonmatches must never become benign.
    Raw headers, addresses, queries and identities never enter the result.
    """
    import gzip
    import ipaddress
    import stat
    import zipfile
    from pathlib import PurePosixPath

    from idps_ai.data.http_curation import require_development_source

    require_development_source(path)
    if not 1 <= max_bytes <= 256 * 1024**2:
        raise PipelineError("Invalid archive expansion budget")
    pattern = re.compile(
        rb'^(\S+)\s+\S+\s+\S+\s+\[([^\]]+)\]\s+"([^"\r\n]+)"\s+(\d{3})\s+(\d+|-)'
        rb'(?:\s+"[^"\r\n]*"\s+"([^"\r\n]*)")?'
    )
    counts, methods, statuses, days = Counter(), Counter(), Counter(), Counter()
    seen = set()
    total_bytes = 0
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 1024 or len({m.filename for m in members}) != len(members):
            raise PipelineError("Archive member count/name budget exceeded")
        for member in members:
            name = PurePosixPath(member.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in member.filename
                or stat.S_ISLNK(member.external_attr >> 16)
                or member.flag_bits & 1
            ):
                raise PipelineError("Unsafe archive member")
        if sum(m.file_size for m in members) > max_bytes:
            raise PipelineError("Archive expansion budget exceeded")
        for member in members:
            if member.is_dir():
                continue
            basename = PurePosixPath(member.filename).name
            if basename.endswith((".yaml", ".yml")):
                counts["publisher_rule_files"] += 1
                continue
            if "access.log" not in basename:
                counts["other_files"] += 1
                continue
            counts["access_log_members"] += 1
            with archive.open(member) as raw:
                stream = gzip.GzipFile(fileobj=raw) if basename.endswith(".gz") else raw
                try:
                    while line := stream.readline(1024**2 + 1):
                        total_bytes += len(line)
                        if len(line) > 1024**2 or total_bytes > max_bytes:
                            raise PipelineError("HTTP log expansion/line budget exceeded")
                        counts["access_log_lines"] += 1
                        match = pattern.match(line)
                        if not match:
                            counts["unparsed_lines"] += 1
                            continue
                        ip, timestamp, request, status, size, agent = match.groups()
                        pieces = request.split(b" ")
                        try:
                            ipaddress.ip_address(ip.decode("ascii"))
                            clock = datetime.strptime(
                                timestamp.decode("ascii"), "%d/%b/%Y:%H:%M:%S %z"
                            )
                            if len(pieces) != 3 or not pieces[2].startswith(b"HTTP/"):
                                raise ValueError
                            method = pieces[0].decode("ascii")
                        except (ValueError, UnicodeError):
                            counts["unparsed_lines"] += 1
                            continue
                        counts["HTTP_rows"] += 1
                        # Hash the complete observed log line, excluding line terminator.
                        # The key remains memory-only; output contains aggregate counts.
                        key = hashlib.sha256(line.rstrip(b"\r\n")).digest()
                        if key in seen:
                            counts["duplicate_HTTP_observations"] += 1
                            continue
                        seen.add(key)
                        methods[
                            method
                            if method
                            in {
                                "GET",
                                "POST",
                                "HEAD",
                                "OPTIONS",
                                "PUT",
                                "DELETE",
                                "PATCH",
                                "CONNECT",
                                "TRACE",
                            }
                            else "OTHER"
                        ] += 1
                        statuses[status.decode("ascii")] += 1
                        days[clock.astimezone(timezone.utc).date().isoformat()] += 1
                finally:
                    if stream is not raw:
                        stream.close()
    return {
        "archive_sha256": file_sha256(path),
        "extracted": False,
        **dict(counts),
        "HTTP_rows": counts["HTTP_rows"],
        "unique_HTTP_observations": len(seen),
        "duplicate_HTTP_observations": counts["duplicate_HTTP_observations"],
        "methods": dict(methods),
        "status_codes": dict(statuses),
        "UTC_days": dict(days),
        "labels": "unknown; publisher matching rules are not applied as ground truth",
        "supervised_admitted_requests": 0,
        "count_caution": "Deduplicated log observations, not independently verified unique physical requests; missing request IDs and possible HTTP/2 format gaps.",
        "raw_or_PII_exported": False,
    }

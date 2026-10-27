"""Disk-backed collection, explicit reviewed labels and immutable Parquet snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from idps_ai.common import (
    CLASSES,
    REPO_ROOT,
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    fsync_dir,
    load_json,
)
from idps_ai.data.privacy import pseudonym
from idps_ai.data.readers import read_events

OBSERVATION_SCHEMA = pa.schema(
    [
        ("event_key", pa.string()),
        ("source", pa.string()),
        ("timestamp", pa.float64()),
        ("request_key", pa.string()),
        ("client_key", pa.string()),
        ("user_key", pa.string()),
        ("session_key", pa.string()),
        ("flow_key", pa.string()),
        ("http_method", pa.string()),
        ("uri_path", pa.string()),
        ("status_code", pa.int16()),
        ("latency_ms", pa.float64()),
        ("role", pa.string()),
        ("user_agent", pa.string()),
        ("event_type", pa.string()),
        ("request_bytes", pa.float64()),
        ("response_bytes", pa.float64()),
        ("flow_json", pa.string()),
        ("numeric_json", pa.string()),
        ("redacted", pa.bool_()),
        ("truncated", pa.bool_()),
        ("provenance", pa.string()),
    ]
)
REQUEST_SCHEMA = pa.schema(
    list(OBSERVATION_SCHEMA)
    + [
        ("observation_count", pa.int32()),
        ("sources", pa.list_(pa.string())),
        ("correlation", pa.string()),
        ("ip_time_context_count", pa.int32()),
        ("ip_time_ambiguous", pa.bool_()),
        ("suricata_alert_counts", pa.list_(pa.int32())),
        ("campaign_key", pa.string()),
        ("label", pa.int8()),
        ("attack_family", pa.string()),
        ("label_source", pa.string()),
        ("label_confidence", pa.float64()),
        ("split", pa.string()),
        ("group_key", pa.string()),
    ]
)


def storage_row(event):
    row = dict(event)
    row["flow_json"] = json.dumps(row.pop("flow", {}), sort_keys=True, allow_nan=False)
    row["numeric_json"] = json.dumps(row.pop("numeric", {}), sort_keys=True, allow_nan=False)
    return row


def write_rows(path, rows, schema, batch_size=512):
    count = 0
    with pq.ParquetWriter(path, schema, compression="zstd") as writer:
        batch = []
        for row in rows:
            batch.append(row)
            if len(batch) >= batch_size:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                count += len(batch)
                batch.clear()
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            count += len(batch)
    os.chmod(path, 0o600)
    with Path(path).open("rb") as stream:
        os.fsync(stream.fileno())
    return count


def iter_rows(path, columns=None, batch_size=512):
    for batch in pq.ParquetFile(path).iter_batches(
        batch_size=batch_size, columns=columns, use_threads=False
    ):
        yield from batch.to_pylist()


def load_labels(path, key):
    labels = {}
    family_seen = {}
    if path is None:
        return labels
    with Path(path).open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536:
                raise PipelineError("Oversized label record")
            try:
                value = json.loads(line)
                family = value.get("attack_family", value.get("label"))
                if family == 0:
                    family = "benign"
                if family not in CLASSES:
                    raise ValueError
                if value.get("label") in (0, 1) and value["label"] != int(family != "benign"):
                    raise ValueError
                label_source = value["label_source"]
                if label_source not in ("scenario_manifest", "human_review", "weak_rule"):
                    raise ValueError
                confidence = float(value.get("label_confidence", 1.0))
                if not 0 <= confidence <= 1:
                    raise ValueError
                request_key = value.get("request_key") or pseudonym(
                    key, "request", value.get("request_id")
                )
                if (
                    not isinstance(request_key, str)
                    or len(request_key) != 64
                    or any(c not in "0123456789abcdef" for c in request_key)
                ):
                    raise ValueError
                reviewed = value.get("review_status") == "approved" and label_source != "weak_rule"
                item = {
                    "campaign_key": pseudonym(key, "campaign", value.get("campaign_id")),
                    "label": int(family != "benign") if reviewed else None,
                    "attack_family": family if reviewed else None,
                    "label_source": label_source,
                    "label_confidence": confidence,
                }
                if reviewed and item["campaign_key"] is None:
                    raise ValueError
                if request_key in labels and (
                    labels[request_key] != item or family_seen[request_key] != family
                ):
                    raise PipelineError(
                        "Conflicting labels for one request; resolve review manifest"
                    )
                labels[request_key] = item
                family_seen[request_key] = family
            except (ValueError, KeyError, TypeError):
                raise PipelineError("Invalid, unreviewed or conflicting label record") from None
    return labels


def manifest(directory, stage, files, **metadata):
    files = {
        name: {
            "sha256": file_sha256(Path(directory) / name),
            "bytes": (Path(directory) / name).stat().st_size,
        }
        for name in files
    }
    result = {
        "format_version": 1,
        "stage": stage,
        "schema_version": "1.0",
        "schema_sha256": file_sha256(REPO_ROOT / "contracts/canonical-event-v1.schema.json"),
        "normalizer_version": "ai-normalizer-2",
        "files": files,
        **metadata,
    }
    result["dataset_sha256"] = digest(result)
    atomic_json(Path(directory) / "dataset_manifest.json", result)
    return result


def verify_dataset(directory, required_stage=None):
    directory = Path(directory)
    value = load_json(directory / "dataset_manifest.json")
    expected = value.pop("dataset_sha256", None)
    if digest(value) != expected or value.get("schema_version") != "1.0":
        raise PipelineError("Dataset manifest checksum or schema mismatch")
    if value.get("schema_sha256") != file_sha256(
        REPO_ROOT / "contracts/canonical-event-v1.schema.json"
    ):
        raise PipelineError("Dataset references a different frozen canonical contract")
    if required_stage and value.get("stage") != required_stage:
        raise PipelineError("Dataset has not been prepared for training")
    for name, info in value["files"].items():
        if name not in (
            "observations.parquet",
            "requests.parquet",
            "features.parquet",
            "feature_spec.json",
        ):
            raise PipelineError("Unsupported dataset file reference")
        path = directory / name
        if path.is_symlink() or not path.is_file() or file_sha256(path) != info["sha256"]:
            raise PipelineError("Missing or modified dataset shard")
    value["dataset_sha256"] = expected
    return value


def collect(inputs, output, key, labels_path=None, correlation_seconds=2.0, max_records=2_000_000):
    output = Path(output).resolve()
    if output.exists():
        raise PipelineError("Dataset destination already exists; choose a new immutable version")
    if not 0 <= correlation_seconds <= 10:
        raise PipelineError("Correlation window must be within 0–10 seconds")
    if any(Path(item.path).resolve().is_relative_to(output) for item in inputs):
        raise PipelineError("Input files must be outside the output dataset")
    labels = load_labels(labels_path, key)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    quality = {"duplicates": 0}
    input_info = [
        {
            "source": item.source,
            "sha256": file_sha256(item.path),
            "bytes": Path(item.path).stat().st_size,
        }
        for item in inputs
    ]
    with tempfile.TemporaryDirectory(prefix=".collect-", dir=output.parent) as temporary:
        work = Path(temporary)
        connection = sqlite3.connect(work / "scratch.sqlite")
        try:
            connection.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
                CREATE TABLE events (eid TEXT PRIMARY KEY,t REAL,rid TEXT,ip TEXT,fid TEXT,source TEXT,kind TEXT,payload TEXT,used INTEGER DEFAULT 0);
                CREATE INDEX rid_time ON events(rid,t); CREATE INDEX ip_time ON events(ip,t,kind);
                CREATE INDEX flow_time ON events(fid,t);
                CREATE INDEX pending ON events(kind,used,source,t);""")
            for event in read_events(inputs, key, quality, max_records=max_records):
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO events(eid,t,rid,ip,fid,source,kind,payload) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        event["event_key"],
                        event["timestamp"],
                        event["request_key"],
                        event["client_key"],
                        event["flow_key"],
                        event["source"],
                        event["event_type"],
                        json.dumps(event, allow_nan=False),
                    ),
                ).rowcount
                quality["duplicates"] += int(not inserted)
            if any(
                file_sha256(item.path) != info["sha256"] for item, info in zip(inputs, input_info)
            ):
                raise PipelineError("Input changed during collection; use immutable snapshots")
            connection.commit()

            def observations():
                for (row,) in connection.execute("SELECT payload FROM events ORDER BY t,eid"):
                    yield storage_row(json.loads(row))

            n_observations = write_rows(
                work / "observations.parquet", observations(), OBSERVATION_SCHEMA
            )
            if not n_observations:
                raise PipelineError("No valid source observations were accepted")
            connection.execute("CREATE TABLE requests (eid TEXT PRIMARY KEY,t REAL,payload TEXT)")
            cursor = connection.execute(
                "SELECT eid,payload FROM events WHERE kind='http_request' ORDER BY CASE source WHEN 'STUDENT_AUDIT' THEN 0 WHEN 'NGINX' THEN 1 ELSE 2 END,t,eid"
            )
            for eid, payload in cursor:
                if connection.execute("SELECT used FROM events WHERE eid=?", (eid,)).fetchone()[0]:
                    continue
                event = json.loads(payload)
                matches = [event]
                correlation = "unmatched"
                if event["request_key"] is not None:
                    candidates = [
                        json.loads(row[0])
                        for row in connection.execute(
                            "SELECT payload FROM events WHERE rid=? AND kind='http_request' AND used=0 AND t BETWEEN ? AND ? AND (ip=? OR ip IS NULL OR ? IS NULL) ORDER BY CASE source WHEN 'STUDENT_AUDIT' THEN 0 WHEN 'NGINX' THEN 1 ELSE 2 END,t,eid",
                            (
                                event["request_key"],
                                event["timestamp"] - correlation_seconds,
                                event["timestamp"] + correlation_seconds,
                                event["client_key"],
                                event["client_key"],
                            ),
                        )
                    ]
                    counts = Counter(c["source"] for c in candidates)
                    if max(counts.values(), default=0) <= 1:
                        matches = candidates
                        correlation = "request_id" if len(matches) > 1 else "unmatched"
                    else:
                        correlation = "ambiguous_request_id"
                connection.executemany(
                    "UPDATE events SET used=1 WHERE eid=?", [(e["event_key"],) for e in matches]
                )
                event["timestamp"] = max(e["timestamp"] for e in matches)
                for field in (
                    "request_bytes",
                    "response_bytes",
                    "latency_ms",
                    "flow_key",
                    "user_key",
                    "session_key",
                ):
                    if event[field] is None:
                        event[field] = next(
                            (e[field] for e in matches if e[field] is not None), None
                        )
                # Preserve a complete numeric view, preferring actual available
                # lexical/original counters over already-masked source views.
                event["numeric"] = max(
                    matches,
                    key=lambda e: (
                        e["numeric"]["query_lexical_available"],
                        e["numeric"]["query_original_available"],
                        e["numeric"]["uri_lexical_available"],
                    ),
                )["numeric"]
                if event["flow_key"] is not None:
                    observed_flow = connection.execute(
                        "SELECT payload FROM events WHERE fid=? AND kind='flow' AND t<=? AND t>=? ORDER BY t DESC LIMIT 1",
                        (event["flow_key"], event["timestamp"], event["timestamp"] - 300),
                    ).fetchone()
                    if observed_flow:
                        event["flow"] = json.loads(observed_flow[0])["flow"]
                row = storage_row(event)
                row.update(
                    observation_count=len(matches),
                    sources=sorted({e["source"] for e in matches}),
                    correlation=correlation,
                )
                t, ip = event["timestamp"], event["client_key"]
                row["suricata_alert_counts"] = [
                    connection.execute(
                        "SELECT count(*) FROM events WHERE source='SURICATA' AND kind='alert' AND ip=? AND t BETWEEN ? AND ?",
                        (ip, t - window, t),
                    ).fetchone()[0]
                    for window in (10, 60, 300)
                ]
                row["ip_time_context_count"] = connection.execute(
                    "SELECT count(*) FROM events WHERE source='SURICATA' AND kind IN ('flow','http_request') AND ip=? AND t BETWEEN ? AND ? AND (rid IS NULL OR rid<>?)",
                    (ip, t - 1, t, event["request_key"] or ""),
                ).fetchone()[0]
                row["ip_time_ambiguous"] = (
                    connection.execute(
                        "SELECT count(DISTINCT COALESCE(rid,eid)) FROM events WHERE kind='http_request' AND ip=? AND t BETWEEN ? AND ?",
                        (ip, t - 1, t),
                    ).fetchone()[0]
                    > 1
                )
                row.update(
                    labels.get(
                        event["request_key"],
                        {
                            "campaign_key": None,
                            "label": None,
                            "attack_family": None,
                            "label_source": "unknown",
                            "label_confidence": None,
                        },
                    )
                )
                if correlation == "ambiguous_request_id":
                    row.update(
                        label=None,
                        attack_family=None,
                        label_source="unknown",
                        label_confidence=None,
                    )
                row.update(split="unassigned", group_key=None)
                connection.execute(
                    "INSERT INTO requests VALUES(?,?,?)", (eid, t, json.dumps(row, allow_nan=False))
                )
            connection.commit()

            def requests():
                for (row,) in connection.execute("SELECT payload FROM requests ORDER BY t,eid"):
                    yield json.loads(row)

            n_requests = write_rows(work / "requests.parquet", requests(), REQUEST_SCHEMA)
            sources = dict(connection.execute("SELECT source,count(*) FROM events GROUP BY source"))
            times = connection.execute("SELECT min(t),max(t) FROM requests").fetchone()
        finally:
            connection.close()
        (work / "scratch.sqlite").unlink()
        result = manifest(
            work,
            "collected",
            ["observations.parquet", "requests.parquet"],
            inputs=input_info,
            label_manifest_sha256=file_sha256(labels_path) if labels_path else None,
            redaction_key_fingerprint=pseudonym(key, "fingerprint", "v1"),
            rows={"observations": n_observations, "requests": n_requests},
            sources=sources,
            quality=quality,
            time_range=list(times),
            labels="explicit_review_only",
            correlation_window_seconds=correlation_seconds,
            input_semantics="finite immutable snapshots; raw input files never written",
        )
        os.replace(work, output)
        fsync_dir(output.parent)
    return result

"""Full-row research curation with immutable publisher labels and traceable exclusions.

Structural research admission is not independent semantic review or production
admission. Every source row is retained in the decision ledger by hash/index;
raw secrets never enter derived Parquet or diagnostics.
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

import pyarrow as pa

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, write_rows
from idps_ai.data.snapshot import new_destination
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import fingerprint, validate_numbers

POLICY = {
    "version": "http-curation-1",
    "time_start_UTC": 1593561600.0,  # July1; original publisher describes July2020.
    "time_end_UTC_exclusive": 1596240000.0,
    "supported_positive_families": ["sqli", "path_traversal", "cmd_injection"],
    "body_policy": "exclude all body-present records from URI-only research fit",
    "conflict_policy": "quarantine every member, never majority vote or relabel",
    "duplicate_policy": "first physical source row; later exact observation duplicates retain references",
    "label_basis": "publisher annotations plus structural audit; no independent human review claim",
    "role": "development_exposed",
}
BASE_SCHEMA = pa.schema(
    [
        ("record_index", pa.int64()),
        ("event_key", pa.string()),
        ("source_id", pa.string()),
        ("natural_key", pa.string()),
        ("client_key", pa.string()),
        ("timestamp", pa.float64()),
        ("original_label", pa.int8()),
        ("attack_family", pa.string()),
        ("published_capec", pa.list_(pa.string())),
        ("body_present", pa.bool_()),
        ("feature_key", pa.string()),
        ("model_key", pa.string()),
        ("decision", pa.string()),
        ("reasons", pa.list_(pa.string())),
        ("duplicate_of", pa.string()),
    ]
)
CURATED_SCHEMA = pa.schema(list(BASE_SCHEMA) + [("numeric_json", pa.string())])


def require_development_source(path):
    """Fail closed on explicit sealed-source markers before loading observations."""
    location = Path(path).resolve()
    for parent in (location, *location.parents):
        for name in ("AI_HOLDOUT.json", "seal.json"):
            marker = parent / name
            if marker.is_file() and str(load_json(marker).get("role", "")).startswith("sealed"):
                raise PipelineError("Sealed holdout cannot enter development curation or training")


def curate_records(records, output, source_id, provenance, policy=None):
    policy = dict(POLICY if policy is None else policy)
    if policy.get("version") != "http-curation-1" or policy.get("role") != "development_exposed":
        raise PipelineError("Explicit development curation policy required")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    atomic_json(output / "policy.json", policy)
    db = sqlite3.connect(output / "curation.sqlite")
    db.execute("PRAGMA cache_size=-32768")
    db.execute("PRAGMA temp_store=FILE")
    db.executescript("""CREATE TABLE r(i INTEGER PRIMARY KEY,id TEXT UNIQUE,nat TEXT,client TEXT,t REAL,y INT,f TEXT,c TEXT,b INT,v TEXT,m TEXT,why TEXT);
    CREATE TABLE vectors(k TEXT PRIMARY KEY,n TEXT);
    CREATE INDEX rn ON r(nat); CREATE INDEX rm ON r(m); CREATE INDEX rv ON r(v);""")
    spec = bounded_spec()
    count = 0
    for i, r in enumerate(records):
        if i >= 1_000_000 or r["label"] not in (None, 0, 1):
            raise PipelineError("Curation source count/label contract exceeded")
        reasons = []
        timestamp = r.get("timestamp")
        numbers = r.get("numbers")
        if timestamp is None:
            reasons.append("missing_timestamp")
        elif not policy["time_start_UTC"] <= timestamp < policy["time_end_UTC_exclusive"]:
            reasons.append("outside_documented_time_range")
        if r.get("client_key") is None:
            reasons.append("missing_client_identity")
        if r["label"] is None or r.get("label_state") != "consistent_publisher_annotation":
            reasons.append("unknown_or_conflicting_record_label")
        if r.get("body_present"):
            reasons.append("body_view_unavailable")
        if r["label"] == 1 and r.get("attack_family") not in policy["supported_positive_families"]:
            reasons.append("unsupported_attack_scope")
        v = m = None
        if numbers is None or r.get("projection_state") != "available":
            reasons.append("missing_URI_projection")
        else:
            validate_numbers(numbers)
            v = digest(numbers)
            m = digest(encode_request(spec, numbers).tolist())
            db.execute(
                "INSERT OR IGNORE INTO vectors VALUES(?,?)",
                (v, json.dumps(numbers, sort_keys=True, separators=(",", ":"))),
            )
        try:
            db.execute(
                "INSERT INTO r VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    i,
                    r["event_key"],
                    r["natural_key"],
                    r.get("client_key"),
                    timestamp,
                    r["label"],
                    r.get("attack_family"),
                    json.dumps(r.get("published_capec", [])),
                    int(bool(r.get("body_present"))),
                    v,
                    m,
                    json.dumps(reasons),
                ),
            )
        except sqlite3.IntegrityError:
            raise PipelineError("Duplicate physical source-row identity") from None
        count += 1
        if count % 4096 == 0:
            db.commit()
    db.commit()
    db.executescript("""CREATE TABLE natural_groups AS SELECT nat,min(i) first_i,min(id) placeholder,
    max(y=0) zero,max(y=1) one,max(y IS NULL) unknown,count(*) n FROM r GROUP BY nat;
    CREATE UNIQUE INDEX ng ON natural_groups(nat);
    CREATE TABLE model_groups AS SELECT m,max(y=0) zero,max(y=1) one FROM r WHERE m IS NOT NULL GROUP BY m;
    CREATE UNIQUE INDEX mg ON model_groups(m);""")
    # Compute conflicts from all annotations, including subsequently rejected rows;
    # otherwise excluding one side could silently turn a contradiction into truth.
    counts = Counter()
    reason_counts = Counter()
    labels = Counter()
    families = Counter()

    def decisions():
        query = """SELECT r.*,g.first_i,g.zero,g.one,g.unknown,mg.zero,mg.one,first.id
        FROM r JOIN natural_groups g USING(nat) LEFT JOIN model_groups mg ON r.m=mg.m
        JOIN r first ON first.i=g.first_i ORDER BY r.i"""
        for row in db.execute(query):
            (
                i,
                event,
                natural,
                client,
                ts,
                y,
                f,
                c,
                b,
                v,
                m,
                why,
                first,
                nzero,
                none,
                nunknown,
                mzero,
                mone,
                first_id,
            ) = row
            reasons = json.loads(why)
            if nzero and none or nunknown and (nzero or none):
                reasons.append("contradictory_observation_labels")
            if mzero and mone:
                reasons.append("contradictory_model_view_labels")
            if reasons:
                decision = "quarantine"
            elif i != first:
                decision = "duplicate"
                reasons.append("duplicate_observation")
            else:
                decision = "accepted_research"
            counts[decision] += 1
            reason_counts.update(reasons)
            if decision == "accepted_research":
                labels[str(y)] += 1
                families[f] += 1
            yield dict(
                record_index=i,
                event_key=event,
                source_id=source_id,
                natural_key=natural,
                client_key=client,
                timestamp=ts,
                original_label=y,
                attack_family=f,
                published_capec=json.loads(c),
                body_present=bool(b),
                feature_key=v,
                model_key=m,
                decision=decision,
                reasons=reasons,
                duplicate_of=first_id if i != first else None,
            )

    write_rows(output / "decisions.parquet", decisions(), BASE_SCHEMA)

    def accepted():
        for r in iter_rows(output / "decisions.parquet"):
            if r["decision"] == "accepted_research":
                numbers = db.execute(
                    "SELECT n FROM vectors WHERE k=?", (r["feature_key"],)
                ).fetchone()[0]
                yield {**r, "numeric_json": numbers}

    write_rows(output / "curated.parquet", accepted(), CURATED_SCHEMA)
    assert sum(counts.values()) == count
    for name in ("accepted_research", "duplicate", "quarantine"):
        counts.setdefault(name, 0)
    result = {
        "format_version": 1,
        "stage": "research_curated",
        "source_id": source_id,
        "input_records": count,
        "decisions": dict(counts),
        "reason_counts_overlapping": dict(reason_counts),
        "accepted_label_counts": dict(labels),
        "accepted_family_counts": dict(families),
        "policy_sha256": file_sha256(output / "policy.json"),
        "policy": policy,
        "provenance": provenance,
        "projection_sha256": fingerprint(),
        "encoder_sha256": spec["encoding"]["implementation_sha256"],
        "all_source_rows_accounted_for": sum(counts.values()) == count,
        "original_labels_unchanged": True,
        "independent_human_review": False,
        "production_admitted": False,
        "scale_admitted": False,
        "research_admission": "structural integrity, complete URI view, documented time, supported scope, no exact/model-view label contradiction",
        "decision_reference": "sourceSHA+zero-based record_index+eventHMAC; original private file retained",
        "natural_conflict_groups": db.execute(
            "SELECT count(*) FROM natural_groups WHERE zero AND one"
        ).fetchone()[0],
        "model_view_conflict_groups": db.execute(
            "SELECT count(*) FROM model_groups WHERE zero AND one"
        ).fetchone()[0],
        "files": {
            f: file_sha256(output / f)
            for f in ["decisions.parquet", "curated.parquet", "policy.json"]
        },
    }
    db.commit()
    db.close()
    (output / "curation.sqlite").chmod(0o600)
    result["curation_sha256"] = digest(result)
    atomic_json(output / "manifest.json", result)
    return result


def verify_curation(directory):
    directory = Path(directory)
    r = load_json(directory / "manifest.json")
    expected = r.pop("curation_sha256", None)
    if (
        digest(r) != expected
        or r.get("stage") != "research_curated"
        or r.get("projection_sha256") != fingerprint()
    ):
        raise PipelineError("Curation manifest/projection integrity mismatch")
    for f, h in r["files"].items():
        if (
            f not in ["decisions.parquet", "curated.parquet", "policy.json"]
            or (directory / f).is_symlink()
            or file_sha256(directory / f) != h
        ):
            raise PipelineError("Curation immutable output integrity mismatch")
    return dict(r, curation_sha256=expected)

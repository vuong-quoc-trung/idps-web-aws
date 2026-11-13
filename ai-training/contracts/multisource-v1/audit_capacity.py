#!/usr/bin/env python3
"""T02 bounded TRAIN metadata inspection; never import application/training code.

Writes only capacity-sample.json next to this file. Reads no feature tensors,
HTTP bodies, CAL/DEV/TEST payloads or source generators. SQL aggregate counts
are metadata, separately accounted from the <=10K inspected record budget.
"""
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PUB = ROOT / "ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1"
GROUND = ROOT / "ai-training/.artifacts/data_scaling_20261109/pilot-r2"
BRONZE = ROOT / ".local-dev/large-request-2m-20261110-r1"
GLU = ROOT / "ai-training/.artifacts/glu207_derivative_20261107"


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def db(path):
    # No existing job is modified; immutable read-only connections create no WAL/SHM.
    if Path(str(path) + "-wal").exists():
        raise RuntimeError("WAL present: refuse an immutable snapshot of a potentially active DB")
    c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    c.execute("PRAGMA query_only=ON")
    c.execute("PRAGMA cache_size=-8192")
    return c


def categories(rows, keys):
    return {k: dict(sorted(collections.Counter(str(r.get(k)) for r in rows).items())) for k in keys}


def main():
    start = time.monotonic()
    # This is a small metadata task, not a T03 resource controller implementation.
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    files = [PUB / "final-data/train.npz", PUB / "materialized/index.sqlite",
             GROUND / "index.sqlite", BRONZE / "qualification.sqlite",
             GLU / "requests_train.parquet"]
    before = {str(p.relative_to(ROOT)): [p.stat().st_size, p.stat().st_mtime_ns] for p in files}

    # The dedicated TRAIN archive establishes the role before any row lookup.
    config = json.loads((PUB / "final-training-config.json").read_text())
    with zipfile.ZipFile(files[0]) as z, z.open("rows.npy") as f:
        magic = f.read(8)
        assert magic[:6] == b"\x93NUMPY"
        width = 2 if magic[6] == 1 else 4
        length = struct.unpack("<H" if width == 2 else "<I", f.read(width))[0]
        header = ast.literal_eval(f.read(length).decode("latin1"))
        assert header == {"descr": "<i8", "fortran_order": False, "shape": (15890,)}
        ids = list(struct.unpack("<4096q", f.read(4096 * 8)))
    with files[0].open("rb") as f:
        assert hashlib.file_digest(f, "sha256").hexdigest() == config["data_files"]["train.npz"]
    c = db(files[1])
    pub = []
    stream = hashlib.sha256()
    for i in ids:
        item = c.execute("SELECT r.j,student.j,accepted.v FROM r JOIN student USING(i) JOIN accepted USING(i) WHERE r.i=?", (i,)).fetchone()
        assert item is not None
        r, m = json.loads(item[0]), json.loads(item[1])
        assert r["view_key"] == item[2] and m["tier"] == "SILVER"
        # Retain only aggregates; no IDs/labels per request are exported.
        stream.update(canonical([i, r, m]) + b"\n")
        pub.append({**r, **m})
    pub_summary = {"inspected": len(pub), "selection": "first4096 rows.npy coordinates in hash-verified final-data/train.npz; indexed SQLite lookups",
        "selected_metadata_sha256": stream.hexdigest(),
        "train_coordinate_sha256": sha_bytes(canonical(ids)),
        "unique_representations_in_sample": len({r["representation_key"] for r in pub}),
        "unique_feature_views_in_sample": len({r["view_key"] for r in pub}),
        "verified_physical_requests": sum(r["identity_verified"] for r in pub),
        "categories": categories(pub, ["source", "target_task", "tier", "intent", "outcome", "body_observation", "physical_identity", "headers_observation", "target"]),
        "native_NSA_mask": "NOT_APPLICABLE_CONTENT_ONLY", "new_contract_admitted": 0}
    c.close()

    c = db(files[2])
    # Read all 68 TRAIN metadata records, with existing exclusion relations.
    q = """SELECT r.i,r.j,bad.c,conflicts.i,overflow.i,
       (SELECT min(x.i) FROM r x WHERE x.req=r.req),
       (SELECT min(x.i) FROM r x WHERE x.raw=r.raw)
       FROM r JOIN roots USING(i) LEFT JOIN bad USING(c)
       LEFT JOIN conflicts USING(i) LEFT JOIN overflow USING(i)
       WHERE r.s='grounded-v3' AND r.role='TRAIN' ORDER BY r.i LIMIT 68"""
    ground, eligible, reasons = [], [], collections.Counter()
    for i, j, cross, conflict, over, first_request, first_raw in c.execute(q):
        r = json.loads(j)
        why = list(r["reasons"])
        checks = [(r["identity_verified"] and r["request_key"] is not None, "IDENTITY_UNVERIFIED"),
            (r["tier"] in {"A", "B"} and r["label_task"] == "attack_intent" and r["label_verified"] and r["label"] is not None, "TARGET_LABEL_UNSUPPORTED"),
            (r["feature_valid"], "FEATURE_INVALID"), (r["lineage_verified"], "LINEAGE_UNVERIFIED"),
            (r["privacy_valid"], "PRIVACY_FAILED"), (r["inherited_eligible"], "INHERITED_EXCLUSION"),
            (cross is None, "CROSS_ROLE_COMPONENT"), (conflict is None, "CONFLICT"),
            (over is None, "NEAR_BUCKET_OVERFLOW"),
            (r["request_key"] is None or first_request == i, "DUPLICATE_REQUEST"),
            (r["representation_key"] is None or first_raw == i, "REPEATED_REPRESENTATION")]
        why.extend(code for ok, code in checks if not ok)
        if not why:
            eligible.append(r)
        reasons.update(set(why))
        ground.append(r)
    assert len(ground) == 68
    summary = json.loads((GROUND / "summary.json").read_text())
    assert len(eligible) == summary["counts"]["TRAIN_ADMITTED"] == 48
    assert len({r["view_key"] for r in eligible}) == summary["strict_feature_views"]["TRAIN"] == 42
    ground_summary = {"inspected": len(ground), "selection": "grounded-v3 TRAIN-only SQL predicate; existing exclusions read as metadata, no CAL/DEV rows decoded",
        "selected_metadata_sha256": sha_bytes(canonical(ground)), "historical_eligible_records_reconciled": len(eligible),
        "historical_eligible_views_reconciled": 42, "categories": categories(eligible, ["tier", "label_task", "label", "body_state", "family"]),
        "exclusion_reasons_overlapping": dict(reasons),
        "native_NSA_mask": "UNVERIFIED_NOT_IN_ADMISSION_METADATA", "new_contract_admitted": 0}
    c.close()

    # Non-empty WAL exists. Do not ignore it with immutable=1, checkpoint the
    # original, create a source SHM, or copy a 68MB database for a small T02 audit.
    # The already recorded POSTPONED manifest is sufficient for this asset's scope.
    wal = Path(str(files[3]) + "-wal")
    postponed = json.loads((BRONZE / "POSTPONED.json").read_text())
    bronze_summary = {"inspected": 0, "sample_status": "BLOCKED_NONEMPTY_WAL_USE_RECORDED_METADATA",
        "recorded_receipts": postponed["verified_distinct_receipts"],
        "count_freshness": "POSTPONED_MANIFEST_NOT_CURRENT_SQL_RECOUNT",
        "wal_bytes": wal.stat().st_size if wal.exists() else None,
        "native_NSA_mask": "NOT_APPLICABLE_DSL_CONTENT_ONLY", "new_contract_admitted": 0}

    import pyarrow.parquet as pq
    p = pq.ParquetFile(files[4])
    assert p.metadata.num_rows == 41607
    columns = ["source", "sources", "observation_count", "correlation", "provenance", "available_at", "timestamp", "label_source", "label_confidence", "split"]
    glu = next(p.iter_batches(batch_size=512, columns=columns, use_threads=False)).to_pylist()
    assert len(glu) == 512 and all(r["split"] == "train" for r in glu)
    masks = collections.Counter("".join(k for k, v in [("N", "NGINX"), ("S", "SURICATA"), ("A", "STUDENT_AUDIT")] if v in r["sources"]) for r in glu)
    glu_summary = {"inspected": len(glu), "selection": "first512 metadata projections from dedicated requests_train.parquet; no feature/numeric/flow blobs or URI read",
        "selected_metadata_sha256": sha_bytes(canonical(glu)), "legacy_declared_source_masks": dict(masks),
        "categories": categories(glu, ["correlation", "label_source", "label_confidence", "observation_count"]),
        "legacy_available_at_before_fused_timestamp": sum(r["available_at"] < r["timestamp"] for r in glu),
        "missing_contract_columns": ["received_at", "decision_time", "sensor_instance", "tx_id", "per_feature_evidence"],
        "new_contract_verified_masks": {k: 0 for k in ["N", "S", "A", "NS", "NA", "SA", "NSA"]},
        "new_contract_admitted": 0,
        "limit": "legacy NSA declaration and confidence1.0 are not new verified correlation/label evidence"}
    after = {str(f.relative_to(ROOT)): [f.stat().st_size, f.stat().st_mtime_ns] for f in files}
    assert before == after, "Source changed during read-only audit"
    total = sum(r["inspected"] for r in [pub_summary, ground_summary, bronze_summary, glu_summary])
    assert total == 4676 and total + 4164 + 2 <= 10000
    result = {"schema_version": "t02-capacity-sample-1", "sampling_locked_by": "audit_capacity.py SHA in acceptance.json",
        "inspection_budget": {"maximum": 10000, "script_record_inspections": total,
          "prior_exploratory_inspections": 2,
          "prior_aborted_attempt_inspections": 4164,
          "prior_attempt_stop": "Non-empty BRONZE WAL detected before any BRONZE record read; no output published",
          "total_record_inspections_this_task": total + 4164 + 2,
          "distinct_selected_records": total,
          "repeat_same_rows_not_new_capacity": True},
        "payload_access": {"raw_HTTP": False, "feature_tensors": False, "CAL_DEV_TEST": False, "sealed": False},
        "publisher": pub_summary, "grounded": ground_summary, "bronze": bronze_summary, "glu": glu_summary,
        "input_stat_before_after_equal": before == after, "input_stats": before,
        "duration_seconds": round(time.monotonic() - start, 3),
        "limits": ["Deterministic bounded convenience sample, not a statistical yield estimate",
                   "No cross-dataset physical uniqueness claim; different HMAC domains cannot be equated",
                   "Metadata counts of all roles are not admission or inspection of protected payloads",
                   "No adapters, encoders, model scores, training or T03 resource changes executed"]}
    (OUT / "capacity-sample.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"state": "PASS", "records_inspected": total, "grounded_records": len(eligible), "grounded_views": 42, "seconds": result["duration_seconds"]}))


if __name__ == "__main__":
    main()

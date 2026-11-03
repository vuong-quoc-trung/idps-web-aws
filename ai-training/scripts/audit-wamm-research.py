#!/usr/bin/env python3
"""Audit a pinned WAMM SQLite release without persisting HTTP content.

This is a publisher-label research screen, never a physical request count,
independent evaluation, or formal admission decision.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.training.resources import resource_envelope

REQUEST_LINE = re.compile(r"^([!#$%&'*+.^_`|~0-9A-Za-z-]{1,24}) (\S{1,8192}) HTTP/\d\.\d$")
NORMAL = "000 - Normal"
ATTACK_LABELS = frozenset(
    {
        "66 - SQL Injection",
        "88 - OS Command Injection",
        "126 - Path Traversal",
        "79 - Cross-Site Scripting",
        "918 - SSRF",
        "248 - Command Injection",
        "1336 - SSTI",
        "94 - Code Injection",
    }
)
MAX_ROWS = 1_000_000
MAX_TEXT = 1_000_000


def _identity_counts(values):
    """Return unique, duplicate, conflicting-key and conflicting-row counts."""
    unique = len(values)
    rows = sum(n0 + n1 for n0, n1 in values.values())
    conflict = [(n0, n1) for n0, n1 in values.values() if n0 and n1]
    return {
        "unique": unique,
        "duplicate_rows": rows - unique,
        "mixed_label_keys": len(conflict),
        "rows_on_mixed_label_keys": sum(n0 + n1 for n0, n1 in conflict),
        "minority_label_rows_on_mixed_keys": sum(min(n0, n1) for n0, n1 in conflict),
    }


def audit(database, expected_sha256, archive, license_file, readme, output, staging=None):
    database, archive, license_file, readme, output = map(
        Path, (database, archive, license_file, readme, output)
    )
    staging = Path(staging) if staging is not None else None
    if output.exists() or (staging is not None and staging.exists()):
        raise PipelineError(
            "Audit output already exists; immutable results must not be overwritten"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PipelineError("Expected WAMM database SHA256 is invalid")
    if database.is_symlink() or database.stat().st_size > 1_000_000_000:
        raise PipelineError("WAMM database is missing or exceeds audit bound")
    if file_sha256(database) != expected_sha256:
        raise PipelineError("WAMM database SHA256 changed")
    if not license_file.read_text().startswith("Creative Commons Attribution 4.0"):
        raise PipelineError("WAMM license text changed; stop research intake")
    db = sqlite3.connect(f"file:{database.resolve()}?mode=ro&immutable=1", uri=True)
    db.execute("PRAGMA query_only=ON")
    try:
        if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise PipelineError("WAMM SQLite integrity failed")
        schema = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='combined_data'"
        ).fetchone()
        if schema != ("CREATE TABLE combined_data (col1 TEXT, col2 TEXT)",):
            raise PipelineError("WAMM request/label schema changed")
        counts = Counter()
        labels = Counter()
        methods = Counter()
        raw_keys = defaultdict(lambda: [0, 0])
        view_keys = defaultdict(lambda: [0, 0])
        view_vectors = {} if staging is not None else None
        spec = bounded_spec()
        for request, label in db.execute("SELECT col1,col2 FROM combined_data ORDER BY rowid"):
            counts["raw_records"] += 1
            if counts["raw_records"] > MAX_ROWS:
                raise PipelineError("WAMM row budget exceeded")
            labels[str(label)] += 1
            if label not in ATTACK_LABELS | {NORMAL}:
                counts["unknown_publisher_label_rows"] += 1
                continue
            if not isinstance(request, str) or len(request) > MAX_TEXT:
                counts["missing_or_oversized_request_rows"] += 1
                continue
            first = request.split("\n", 1)[0].rstrip("\r")
            match = REQUEST_LINE.fullmatch(first)
            if match is None:
                counts["invalid_request_line_rows"] += 1
                continue
            method, target = match.groups()
            try:
                numbers = project_request(target, method)["numbers"]
                vector = encode_request(spec, numbers)
            except (PipelineError, ValueError, OverflowError):
                counts["unprojectable_request_rows"] += 1
                continue
            binary = int(label != NORMAL)
            raw_key = hashlib.sha256(request.encode("utf-8")).digest()
            view_key = hashlib.sha256(vector.tobytes()).digest()
            raw_keys[raw_key][binary] += 1
            view_keys[view_key][binary] += 1
            if view_vectors is not None:
                view_vectors.setdefault(view_key, vector.tobytes())
            methods[method] += 1
            counts["parsed_request_representations"] += 1
            counts["publisher_benign_parsed" if binary == 0 else "publisher_attack_parsed"] += 1
            if "\r\n\r\n" in request:
                body = request.partition("\r\n\r\n")[2]
            else:
                body = request.partition("\n\n")[2]
            counts["nonempty_body_rows"] += bool(body)
    finally:
        db.close()
    raw = _identity_counts(raw_keys)
    views = _identity_counts(view_keys)
    staged = None
    if staging is not None:
        clean = sorted(key for key, (n0, n1) in view_keys.items() if not (n0 and n1))
        width = len(spec["columns"])
        flat = np.frombuffer(b"".join(view_vectors[key] for key in clean), dtype=np.float32)
        features = pa.FixedSizeListArray.from_arrays(pa.array(flat, type=pa.float32()), width)
        labels_clean = [int(view_keys[key][1] > 0) for key in clean]
        table = pa.table(
            {
                "view_sha256": pa.array([key.hex() for key in clean]),
                "label": pa.array(labels_clean, type=pa.int8()),
                "occurrence_rows": pa.array(
                    [sum(view_keys[key]) for key in clean], type=pa.int32()
                ),
                "features": features,
            }
        )
        staging.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = staging.with_suffix(staging.suffix + ".partial")
        if partial.exists() or partial.is_symlink():
            raise PipelineError("Staging partial already exists")
        try:
            pq.write_table(table, partial, compression="zstd", row_group_size=4096)
            partial.chmod(0o600)
            with partial.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(partial, staging)
        finally:
            if partial.exists():
                partial.unlink()
        staged = {
            "path": str(staging),
            "sha256": file_sha256(staging),
            "rows_one_per_nonconflicting_float32_view": len(clean),
            "publisher_benign_views": labels_clean.count(0),
            "publisher_attack_views": labels_clean.count(1),
            "source_time_campaign_metadata": False,
            "partition": "UNASSIGNED_RESEARCH_STAGING_ONLY",
            "raw_http_retained": False,
        }
    report = {
        "format_version": 1,
        "source": "WAMM DS-Augmented-v2, pinned repository revision 2783eab560c4355f5976a57fc2e97a2e6c5c79a1",
        "source_url": "https://github.com/CyShield-Security-R-D/WAMM-Dataset-Repository",
        "license_claim": "CC BY 4.0; attribution required",
        "trust_tier": "B_EXTERNAL_PUBLISHER_LABEL_NOT_INDEPENDENT_REQUEST_GROUND_TRUTH",
        "lineage": "SR-BH 2020 derivative plus Burp augmentation; exact per-row origin/campaign/time not provided",
        "input_sha256": {
            "sqlite": expected_sha256,
            "archive": file_sha256(archive),
            "license": file_sha256(license_file),
            "readme": file_sha256(readme),
            "audit_script": file_sha256(__file__),
        },
        "request_profile": spec["profile"],
        "request_features": len(spec["columns"]),
        "request_feature_spec_sha256": digest(spec),
        "counts": dict(counts),
        "publisher_label_counts": dict(labels),
        "http_method_counts": dict(methods),
        "exact_text_representation": raw,
        "exact_float32_request_view": views,
        "numeric_research_staging": staged,
        "verified_physical_requests": 0,
        "machine_verified_intent_labels": 0,
        "independently_verified_intent_labels": 0,
        "formal_admitted_requests": 0,
        "partition_or_independent_evaluation_ready": False,
        "limits": [
            "Publisher README counts are not substituted for SQLite counts.",
            "One row or one exact text representation is not proven to be a distinct physical request.",
            "Request-only features omit body/headers and cannot be padded into GLU207.",
            "WAMM is SR-BH-derived, so exposed SR-BH cannot be an independent acceptance source.",
            "Exact float32 collisions with opposing publisher labels remain unresolved, never silently relabeled.",
        ],
    }
    report["report_sha256"] = digest(report)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--readme", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--staging")
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = audit(
            args.database,
            args.expected_sha256,
            args.archive,
            args.license,
            args.readme,
            args.output,
            args.staging,
        )
    print({"rows": result["counts"]["raw_records"], "report": args.output})

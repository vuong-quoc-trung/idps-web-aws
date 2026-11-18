"""Measure retrospective HTTP coverage of the pinned Organization X archive offline."""

import argparse
import gzip
import hashlib
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json

CONTRACTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(CONTRACTS / "quality-recovery-r261"),
    str(CONTRACTS / "development-bulk-v1"),
]
from lab_auth import uri100  # noqa: E402

REQUEST_LINE = re.compile(
    rb'\[([0-9]{2}/[A-Za-z]{3}/[0-9]{4}):[^\]\r\n]+\]\s+"([A-Z]{1,20}) ([^\s"]+) HTTP/[0-9.]+"\s'
)
ARCHIVE_BYTES = 2_135_289
ARCHIVE_MD5 = "b4bf79effa6f3ee1b9e53f278d916620"
ARCHIVE_SHA256 = "1429caba2803c3e8c90e9fb287bc04f6f8249f8bb34712b39127044e134d631f"
LINE_LIMIT = 65536
EXPANSION_LIMIT = 128 * 1024**2
METADATA_DOI = "10.5281/zenodo.20001206"


def require(condition, reason):
    if not condition:
        raise PipelineError(reason)


def audit(run):
    archive = run / "organization-x.zip"
    metadata_path = run / "zenodo-20001206.json"
    metadata = load_json(metadata_path)
    member = next(row for row in metadata["files"] if row["key"] == archive.name)
    require(
        metadata["metadata"]["doi"] == METADATA_DOI
        and metadata["metadata"]["license"]["id"] == "mit-license"
        and member["checksum"] == "md5:" + ARCHIVE_MD5
        and archive.stat().st_size == member["size"] == ARCHIVE_BYTES
        and file_sha256(archive) == ARCHIVE_SHA256,
        "FORENSIC_ARCHIVE_IDENTITY_MISMATCH",
    )
    count, methods, days = Counter(), Counter(), set()
    distinct_lines, distinct_representations = set(), set()
    counts_by_view = Counter()
    with zipfile.ZipFile(archive) as bundle:
        files = [item for item in bundle.infolist() if not item.is_dir()]
        access = [item for item in files if "access" in Path(item.filename).name.lower()]
        rules = [item for item in files if Path(item.filename).suffix.lower() in (".yaml", ".yml")]
        require(len(access) <= 64 and len(rules) == 1, "UNEXPECTED_FORENSIC_MEMBERS")
        require(rules[0].file_size <= 256 * 1024, "FORENSIC_RULE_METADATA_BUDGET")
        rule_rows = yaml.safe_load(bundle.read(rules[0]))
        require(
            isinstance(rule_rows, list)
            and all(
                set(r) == {"filter", "ground_truth_label", "id", "sensitivity"} for r in rule_rows
            ),
            "UNEXPECTED_FORENSIC_LABEL_SCHEMA",
        )
        processed = {}  # One projection per exact method/target representation.
        for item in access:
            with bundle.open(item) as wrapped:
                stream = (
                    gzip.GzipFile(fileobj=wrapped) if item.filename.endswith(".gz") else wrapped
                )
                try:
                    while line := stream.readline(LINE_LIMIT + 1):
                        count["expanded_access_bytes"] += len(line)
                        require(
                            len(line) <= LINE_LIMIT
                            and count["expanded_access_bytes"] <= EXPANSION_LIMIT,
                            "FORENSIC_EXPANSION_BUDGET",
                        )
                        count["access_log_lines"] += 1
                        match = REQUEST_LINE.search(line)
                        if match is None:
                            count["unparsed_request_line"] += 1
                            continue
                        day, method, target = match.groups()
                        days.add(day)
                        kind = method.decode("ascii")
                        methods[
                            kind
                            if kind in {"GET", "POST", "HEAD", "PUT", "DELETE", "OPTIONS"}
                            else "OTHER"
                        ] += 1
                        count["parseable_request_lines"] += 1
                        count["query_present"] += b"?" in target
                        distinct_lines.add(hashlib.sha256(line.rstrip(b"\r\n")).digest())
                        key = hashlib.sha256(method + b"\x00" + target).digest()
                        distinct_representations.add(key)
                        if key not in processed:
                            try:
                                view = uri100(target.decode("ascii"), kind)
                                require(
                                    view.shape == (100,) and np.isfinite(view).all(),
                                    "BAD_URI100_VIEW",
                                )
                                processed[key] = view.astype("<f4", copy=False).tobytes()
                            except (UnicodeError, PipelineError, ValueError):
                                processed[key] = None
                        encoded = processed[key]
                        if encoded is None:
                            count["unsupported_projection_rows"] += 1
                        else:
                            count["projected_rows"] += 1
                            counts_by_view[encoded] += 1
                finally:
                    if stream is not wrapped:
                        stream.close()
    require(sum(counts_by_view.values()) == count["projected_rows"], "FORENSIC_COUNT_MISMATCH")
    views = sorted(counts_by_view)
    out = run / "forensic-unlabeled-uri100.npz"
    with out.open("xb") as stream:
        np.savez_compressed(
            stream,
            x=np.frombuffer(b"".join(views), dtype="<f4").reshape(-1, 100),
            observed_count=np.array([counts_by_view[key] for key in views], dtype=np.int64),
        )
    return {
        "version": "idps-r30-forensic-http-profile-v1",
        "source": METADATA_DOI,
        "license_id": "mit-license",
        "source_archive_bytes": ARCHIVE_BYTES,
        "source_archive_sha256": ARCHIVE_SHA256,
        "publisher_archive_checksum": "md5:" + ARCHIVE_MD5,
        "metadata_sha256": file_sha256(metadata_path),
        "access_members": len(access),
        "observed_log_days": len(days),
        "organization_count": 1,
        "census": dict(count),
        "methods": dict(methods),
        "exact_distinct_log_lines": len(distinct_lines),
        "exact_distinct_method_targets": len(distinct_representations),
        "projectable_distinct_method_targets": sum(view is not None for view in processed.values()),
        "unique_uri100_unlabeled": len(views),
        "unlabeled_numeric_derivative_sha256": file_sha256(out),
        "rule_definitions": len(rule_rows),
        "request_level_label_table_present": False,
        "train_permission_under_project_protocol": False,
        "evidence_scope": "UNLABELED_FORENSIC_OBSERVABILITY_ONLY",
        "authoritative_physical_request_ids_proven": 0,
        "decision_time_availability_witnesses": 0,
        "verified_native_benign_or_attack": 0,
        "formal_admission": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    atomic_json(args.run / "forensic-census.json", audit(args.run))

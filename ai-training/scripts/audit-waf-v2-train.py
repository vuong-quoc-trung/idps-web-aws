#!/usr/bin/env python3
"""Audit only a pinned WAF Data v2 train Parquet without exporting HTTP content."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.training.resources import resource_envelope

FIELDS = ("method", "url", "protocol", "headers", "body", "label")
LABELS = {"normal": 0, "anomalous": 1}


def audit(path, expected_sha, readme, output):
    path, readme, output = Path(path), Path(readme), Path(output)
    if output.exists() or path.is_symlink() or readme.is_symlink():
        raise PipelineError("WAF train audit refuses existing output or symlink input")
    if file_sha256(path) != expected_sha:
        raise PipelineError("Pinned WAF train checksum mismatch")
    card = readme.read_text()
    if "license: mit" not in card or "anomalous" not in card or "normal" not in card:
        raise PipelineError("WAF dataset card/license/label contract changed")
    parquet = pq.ParquetFile(path)
    if parquet.schema_arrow.names != list(FIELDS) or parquet.metadata.num_rows > 2_000_000:
        raise PipelineError("WAF train schema or row bound changed")
    rows = Counter()
    exact = defaultdict(lambda: [0, 0])
    method_labels = defaultdict(lambda: [0, 0])
    sampled_views = defaultdict(lambda: [0, 0])
    spec = bounded_spec()
    for batch in parquet.iter_batches(batch_size=4096, columns=list(FIELDS)):
        columns = {name: batch.column(name).to_pylist() for name in FIELDS}
        for method, url, protocol, headers, body, label in zip(
            *(columns[name] for name in FIELDS), strict=True
        ):
            rows["publisher_rows"] += 1
            if label not in LABELS:
                rows["unknown_label_rows"] += 1
                continue
            binary = LABELS[label]
            rows[f"publisher_{label}_rows"] += 1
            if any(
                value is not None and not isinstance(value, str)
                for value in (method, url, protocol, headers, body)
            ):
                raise PipelineError("WAF request field type changed")
            if (
                not method
                or not url
                or len(url) > 8192
                or len(headers or "") > 1_000_000
                or len(body or "") > 1_000_000
            ):
                rows["invalid_or_oversized_request_rows"] += 1
                continue
            rows["nonempty_headers"] += bool(headers)
            rows["nonempty_body"] += bool(body)
            key = digest([method, url, protocol, headers, body])
            exact[key][binary] += 1
            method_labels[method][binary] += 1
            # A deterministic 1/32 sample measures numeric-view diversity without
            # claiming a full-corpus view count or retaining request text.
            if int(key[:8], 16) % 32 == 0:
                rows["sampled_request_rows"] += 1
                try:
                    vector = encode_request(spec, project_request(url, method)["numbers"])
                except (PipelineError, ValueError, OverflowError):
                    rows["sampled_unprojectable_rows"] += 1
                    continue
                sampled_views[hashlib.sha256(vector.tobytes()).hexdigest()][binary] += 1
    if rows["publisher_rows"] != parquet.metadata.num_rows:
        raise PipelineError("WAF row count mismatch")
    mixed_exact = sum(bool(a and b) for a, b in exact.values())
    mixed_view = sum(bool(a and b) for a, b in sampled_views.values())
    report = {
        "format_version": 1,
        "source": "puyang2025/waf_data_v2 train only",
        "revision": "b035dc17f875f1f732c10654709abed66a4e9742",
        "input_sha256": {"train": expected_sha, "readme": file_sha256(readme)},
        "audit_script_sha256": file_sha256(__file__),
        "card_license_claim": "MIT",
        "publisher_label_semantics": "normal=benign/legitimate; anomalous=suspicious or attack-like; not confirmed attack intent",
        "counts": dict(rows),
        "exact_request_representations": len(exact),
        "exact_duplicate_rows": sum(sum(v) for v in exact.values()) - len(exact),
        "exact_request_label_conflicts": mixed_exact,
        "sampled_unique_76_feature_views": len(sampled_views),
        "sampled_76_feature_label_conflicts": mixed_view,
        "sample_scope": "deterministic SHA256 modulo 32 of complete request representation; not full-corpus view count",
        "method_label_counts": {name: values for name, values in sorted(method_labels.items())},
        "provenance": "publisher card does not document capture process, request IDs, times, campaign IDs or independent label review",
        "research_use": "weak-label anomaly investigation only; no confirmed attack ground truth, independent evaluation or formal admission",
        "test_or_heldout_opened": False,
        "physical_requests_verified": 0,
        "formal_admitted": 0,
    }
    report["report_sha256"] = digest(report)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--readme", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = audit(args.train, args.sha256, args.readme, args.output)
    print({"rows": result["counts"]["publisher_rows"], "report": args.output})

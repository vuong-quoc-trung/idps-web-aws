#!/usr/bin/env python3
"""Make a private, numeric-only WAF train-split weak-label research corpus."""

from __future__ import annotations

import argparse
import hashlib
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.common import PipelineError, atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.safe_content import symbolic_request
from idps_ai.training.resources import resource_envelope

FIELDS = ("method", "url", "protocol", "headers", "body", "label")
LABELS = {"normal": 0, "anomalous": 1}
SAMPLE_DIVISOR = 16
CONTENT_DIM = 512


def _rows(parquet):
    for batch in parquet.iter_batches(batch_size=4096, columns=list(FIELDS)):
        columns = [batch.column(name).to_pylist() for name in FIELDS]
        yield from zip(*columns, strict=True)


def _exact_key(row):
    return hashlib.sha256(canonical_bytes(row[:5])).digest()


def curate(train, train_sha, readme, output):
    train, readme, output = Path(train), Path(readme), Path(output)
    if output.exists() or output.is_symlink() or train.is_symlink():
        raise PipelineError("Content corpus output exists or input is symlink")
    if file_sha256(train) != train_sha or "license: mit" not in readme.read_text():
        raise PipelineError("Pinned WAF train/license evidence mismatch")
    parquet = pq.ParquetFile(train)
    if parquet.schema_arrow.names != list(FIELDS) or parquet.metadata.num_rows != 1_924_461:
        raise PipelineError("WAF train schema/row count changed")
    labels_by_exact = {}
    counts = Counter()
    for row in _rows(parquet):
        *request, label = row
        counts["raw_rows"] += 1
        if (
            label not in LABELS
            or not isinstance(request[0], str)
            or not isinstance(request[1], str)
        ):
            counts["unknown_or_invalid_label_rows"] += 1
            continue
        if not request[0] or not request[1] or len(request[1]) > 8192:
            counts["invalid_request_rows"] += 1
            continue
        key = _exact_key(row)
        labels_by_exact[key] = labels_by_exact.get(key, 0) | (1 << LABELS[label])
    conflicts = {key for key, mask in labels_by_exact.items() if mask == 3}
    counts["exact_unique_representations"] = len(labels_by_exact)
    counts["exact_conflicting_representations"] = len(conflicts)
    if len(labels_by_exact) != 1_612_017 or len(conflicts) != 192:
        raise PipelineError("Exact WAF counts differ from pinned audit")
    seen = set()
    numeric, safe_text, group, exact, labels = [], [], [], [], []
    spec = bounded_spec()
    for row in _rows(parquet):
        *request, label = row
        if (
            label not in LABELS
            or not isinstance(request[0], str)
            or not isinstance(request[1], str)
        ):
            continue
        if not request[0] or not request[1] or len(request[1]) > 8192:
            continue
        key = _exact_key(row)
        if key in conflicts or key in seen or int.from_bytes(key[:4], "big") % SAMPLE_DIVISOR:
            continue
        seen.add(key)
        method, url, _, headers, body = request
        try:
            values = encode_request(spec, project_request(url, method)["numbers"])
            symbolic, availability = symbolic_request(method, url, headers, body)
        except (PipelineError, ValueError, OverflowError):
            counts["selected_unprojectable"] += 1
            continue
        numeric.append(values)
        safe_text.append(symbolic)
        group.append(hashlib.sha256(symbolic.encode()).hexdigest())
        exact.append(key.hex())
        labels.append(LABELS[label])
        counts["redacted_query_fields"] += availability["redacted_query_fields"]
        counts["body_redacted_rows"] += availability["body_redacted"]
        counts["body_nonempty_rows"] += availability["body_nonempty"]
        if len(numeric) > 150_000:
            raise PipelineError("Bounded WAF research sample exceeded")
    if len(numeric) < 10_000 or len(set(labels)) != 2:
        raise PipelineError("WAF weak-label sample lacks both classes")
    vectorizer = HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=CONTENT_DIM,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    content = vectorizer.transform(safe_text).toarray().astype(np.float32)
    numeric = np.asarray(numeric, np.float32)
    labels = np.asarray(labels, np.int8)
    # The model sees only the persisted numeric vectors. If two distinct raw
    # requests collide in this view with opposite labels, quarantine the view.
    view = [
        hashlib.sha256(np.concatenate((a, b)).tobytes()).hexdigest()
        for a, b in zip(numeric, content, strict=True)
    ]
    view_labels = defaultdict(set)
    for key, label in zip(view, labels, strict=True):
        view_labels[key].add(int(label))
    mixed = {key for key, values in view_labels.items() if len(values) > 1}
    unique = set()
    keep = []
    for i, key in enumerate(view):
        if key not in mixed and key not in unique:
            keep.append(i)
            unique.add(key)
    role = np.asarray(
        [
            0 if int(group[i][:2], 16) < 192 else 1 if int(group[i][:2], 16) < 224 else 2
            for i in keep
        ],
        np.int8,
    )
    label_final = labels[keep]
    coverage = {
        name: {
            label: int(np.sum((role == r) & (label_final == binary)))
            for label, binary in LABELS.items()
        }
        for name, r in (("train", 0), ("calibration", 1), ("validation", 2))
    }
    output.mkdir(parents=True, mode=0o700)
    data_path = output / "numeric-only.npz"
    with data_path.open("xb") as stream:
        np.savez_compressed(
            stream,
            numeric=numeric[keep],
            content=content[keep],
            label=label_final,
            role=role,
            group=np.asarray([group[i] for i in keep], dtype="S64"),
            exact=np.asarray([exact[i] for i in keep], dtype="S64"),
            view=np.asarray([view[i] for i in keep], dtype="S64"),
        )
        stream.flush()
        os.fsync(stream.fileno())
    data_path.chmod(0o600)
    groups_by_role = [
        set(np.asarray([group[i] for i in keep], dtype="S64")[role == r]) for r in (0, 1, 2)
    ]
    if any(groups_by_role[a] & groups_by_role[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise PipelineError("Symbolic template group crossed research roles")
    report = {
        "format_version": 1,
        "source": "puyang2025/waf_data_v2 pinned train split; MIT publisher claim",
        "label_task": "publisher NORMAL versus ANOMALOUS, not confirmed attack intent",
        "input_sha256": {"train": train_sha, "readme": file_sha256(readme)},
        "code_sha256": file_sha256(__file__),
        "safe_content_code_sha256": file_sha256(
            Path(__file__).resolve().parents[1] / "src/idps_ai/features/safe_content.py"
        ),
        "numeric_spec_sha256": digest(spec),
        "selection": "SHA256 complete-request modulo 16; exact conflicting requests excluded",
        "counts": dict(counts),
        "selected_exact_representations": len(seen),
        "selected_projectable_representations": len(numeric),
        "selected_unique_numeric_content_views": len(keep),
        "quarantined_mixed_feature_views": len(mixed),
        "quarantined_rows_on_mixed_views": sum(key in mixed for key in view),
        "symbolic_template_groups": len(set(group[i] for i in keep)),
        "symbolic_template_cross_role_overlap": 0,
        "role_class_coverage": coverage,
        "data_file_sha256": file_sha256(data_path),
        "physical_requests_verified": 0,
        "machine_verified_intent": 0,
        "formal_admitted": 0,
        "evaluation_scope": "internal publisher-label study only; no source/campaign/time independence or label verification",
        "near_duplicate_limit": "symbolic template groups catch normalization collisions; residual cross-template similarity unmeasured",
        "test_or_heldout_opened": False,
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--readme", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = curate(args.train, args.sha256, args.readme, args.output)
    print({"views": result["selected_unique_numeric_content_views"], "report": args.output})

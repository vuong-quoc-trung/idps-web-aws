#!/usr/bin/env python3
"""Attribute WAF label conflicts to raw identity and lossy request views."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.common import PipelineError, atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content import rich_request
from idps_ai.features.safe_content import symbolic_request
from idps_ai.training.resources import resource_envelope

FIELDS = ("method", "url", "protocol", "headers", "body", "label")
LABELS = {"normal": 0, "anomalous": 1}


def rows(parquet):
    for batch in parquet.iter_batches(batch_size=4096, columns=list(FIELDS)):
        columns = [batch.column(name).to_pylist() for name in FIELDS]
        yield from zip(*columns, strict=True)


def _key(values):
    return hashlib.sha256(canonical_bytes(values)).digest()


def _summary(keys, labels, raw_keys):
    groups = defaultdict(lambda: [0, 0, set()])
    for key, label, raw in zip(keys, labels, raw_keys, strict=True):
        group = groups[key]
        group[label] += 1
        group[2].add(raw)
    mixed = [v for v in groups.values() if v[0] and v[1]]
    return {
        "unique_keys": len(groups),
        "mixed_label_keys": len(mixed),
        "rows_on_mixed_keys": sum(v[0] + v[1] for v in mixed),
        "minimum_minor_label_rows": sum(min(v[0], v[1]) for v in mixed),
        "mixed_keys_with_distinct_raw_requests": sum(len(v[2]) > 1 for v in mixed),
    }


def analyze(train, train_sha, output):
    train, output = Path(train), Path(output)
    if output.exists() or file_sha256(train) != train_sha:
        raise PipelineError("Collision audit input changed or output exists")
    parquet = pq.ParquetFile(train)
    if parquet.schema_arrow.names != list(FIELDS) or parquet.metadata.num_rows != 1_924_461:
        raise PipelineError("WAF train schema changed")
    raw_masks = {}
    for row in rows(parquet):
        label = row[5]
        if label not in LABELS or not isinstance(row[0], str) or not isinstance(row[1], str):
            continue
        if not row[0] or not row[1] or len(row[1]) > 8192:
            continue
        key = _key(row[:5])
        raw_masks[key] = raw_masks.get(key, 0) | 1 << LABELS[label]
    conflicts = {key for key, value in raw_masks.items() if value == 3}
    if len(raw_masks) != 1_612_017 or len(conflicts) != 192:
        raise PipelineError("Raw identity counts differ from pinned WAF audit")
    spec = bounded_spec()
    seen = set()
    raw_keys, labels, numeric, symbols, rich_symbols, field_keys = [], [], [], [], [], []
    for row in rows(parquet):
        if row[5] not in LABELS or not isinstance(row[0], str) or not isinstance(row[1], str):
            continue
        if not row[0] or not row[1] or len(row[1]) > 8192:
            continue
        raw = _key(row[:5])
        if raw in conflicts or raw in seen or int.from_bytes(raw[:4], "big") % 16:
            continue
        seen.add(raw)
        try:
            numbers = encode_request(spec, project_request(row[1], row[0])["numbers"])
            symbolic, _ = symbolic_request(row[0], row[1], row[3], row[4])
            rich_symbolic, _ = rich_request(row[0], row[1], row[3], row[4])
        except (PipelineError, ValueError, OverflowError):
            continue
        raw_keys.append(raw)
        labels.append(LABELS[row[5]])
        numeric.append(numbers)
        symbols.append(symbolic)
        rich_symbols.append(rich_symbolic)
        field_keys.append(tuple(_key([value]) for value in row[:5]))
    if len(raw_keys) != 101_098:
        raise PipelineError("Selected WAF cohort changed")
    numeric = np.asarray(numeric, np.float32)
    vectorizer = HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=512,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    content = vectorizer.transform(symbols).toarray().astype(np.float32)
    rich_content = vectorizer.transform(rich_symbols).toarray().astype(np.float32)
    symbolic_keys = [_key([value]) for value in symbols]
    rich_symbolic_keys = [_key([value]) for value in rich_symbols]
    numeric_keys = [hashlib.sha256(value.tobytes()).digest() for value in numeric]
    symbolic_numeric_keys = [
        hashlib.sha256(a + b).digest() for a, b in zip(symbolic_keys, numeric_keys, strict=True)
    ]
    final_keys = [
        hashlib.sha256(np.concatenate((a, b)).tobytes()).digest()
        for a, b in zip(numeric, content, strict=True)
    ]
    rich_symbolic_numeric_keys = [
        hashlib.sha256(a + b).digest()
        for a, b in zip(rich_symbolic_keys, numeric_keys, strict=True)
    ]
    rich_final_keys = [
        hashlib.sha256(np.concatenate((a, b)).tobytes()).digest()
        for a, b in zip(numeric, rich_content, strict=True)
    ]
    final_groups = defaultdict(list)
    for i, key in enumerate(final_keys):
        final_groups[key].append(i)
    varied_fields = Counter()
    final_mixed = 0
    for indices in final_groups.values():
        if len({labels[i] for i in indices}) != 2:
            continue
        final_mixed += 1
        for j, name in enumerate(("method", "url", "protocol", "headers", "body")):
            varied_fields[name] += len({field_keys[i][j] for i in indices}) > 1
    result = {
        "format_version": 1,
        "scope": "WAF train exact-nonconflicting SHA-mod16 sample; prior v2 development cohort, diagnostic only",
        "input_sha256": train_sha,
        "script_sha256": file_sha256(__file__),
        "safe_content_sha256": file_sha256(
            Path(__file__).resolve().parents[1] / "src/idps_ai/features/safe_content.py"
        ),
        "raw_exact_unique_representations_full_train": len(raw_masks),
        "raw_exact_mixed_label_representations_full_train": len(conflicts),
        "sampled_nonconflicting_raw_representations": len(raw_keys),
        "stages": {
            "numeric76": _summary(numeric_keys, labels, raw_keys),
            "safe_symbolic_text": _summary(symbolic_keys, labels, raw_keys),
            "safe_symbolic_plus_numeric76_before_hashing": _summary(
                symbolic_numeric_keys, labels, raw_keys
            ),
            "final_float32_numeric76_plus_hashed_content512": _summary(
                final_keys, labels, raw_keys
            ),
            "rich_symbolic_text": _summary(rich_symbolic_keys, labels, raw_keys),
            "rich_symbolic_plus_numeric76_before_hashing": _summary(
                rich_symbolic_numeric_keys, labels, raw_keys
            ),
            "rich_float32_numeric76_plus_hashed_content512": _summary(
                rich_final_keys, labels, raw_keys
            ),
        },
        "final_mixed_views_with_field_variation": dict(varied_fields),
        "final_mixed_views_checked": final_mixed,
        "interpretation": "Raw conflicts and lossy view conflicts are distinct; field variation does not prove publisher labels correct or infer malicious intent",
        "plaintext_output": False,
        "test_or_heldout_opened": False,
    }
    result["report_sha256"] = digest(result)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, result)
    output.chmod(0o600)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = analyze(args.train, args.sha256, args.output)
    print({"sampled": result["sampled_nonconflicting_raw_representations"], "report": args.output})

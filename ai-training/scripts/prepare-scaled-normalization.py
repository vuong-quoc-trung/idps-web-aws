#!/usr/bin/env python3
"""Replay pinned publisher TRAIN curation; recover v2 views and matched normalized views.

No publisher eval/test/heldout or sealed lab files are opened. No model scores.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.normalization_ablation import from_symbols
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "ai-training/.artifacts"
RAW = ART / "autonomous_research_20261104/waf_v2/train.parquet"
README = RAW.with_name("README.md")
TENSOR = ART / "request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz"
RAW_SHA = "3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6"
TENSOR_SHA = "279dca7d03b38bb2092bf775762bfe68904eea131e0d1145a564de0f98441049"
FIELDS = ["method", "url", "protocol", "headers", "body", "label"]


def rows():
    for batch in pq.ParquetFile(RAW).iter_batches(
        batch_size=4096, columns=FIELDS, use_threads=False
    ):
        yield from zip(*(batch.column(k).to_pylist() for k in FIELDS), strict=True)


def near_mask(reference, queries, progress):
    """Certified candidate superset using a coordinate projection contraction.

    Unit vectors with cosine>=.995 have Euclidean distance<=.100001. A coordinate
    subset cannot increase distance; exact full dot confirms every candidate.
    """
    if not len(reference):
        return np.zeros(len(queries), bool), 0
    axes = np.argsort(np.var(reference, axis=0))[-32:]
    tree = cKDTree(np.asarray(reference[:, axes], np.float64))
    mask = np.zeros(len(queries), bool)
    checked = 0
    for i, q in enumerate(queries):
        candidates = tree.query_ball_point(q[axes].astype(np.float64), r=0.10002, workers=1)
        for k in range(0, len(candidates), 1024):
            idx = candidates[k : k + 1024]
            checked += len(idx)
            similarity = np.asarray(reference[idx], np.float64) @ q.astype(np.float64)
            if np.any(similarity >= 0.995 - 1e-7):
                mask[i] = True
                break
        if i % 1000 == 0:
            atomic_json(
                progress,
                {
                    "query": i,
                    "total": len(queries),
                    "near_excluded": int(mask.sum()),
                    "full_pairs_checked": checked,
                },
            )
    return mask, checked


def prepare(output):
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    started = time.time()
    protocol = {
        "schema_version": "scaled-normalization-preparation-1",
        "source": "puyang2025/waf_data_v2@b035dc17f875f1f732c10654709abed66a4e9742 publisher TRAIN only",
        "license": "MIT publisher declaration in pinned card; raw inputs remain private",
        "raw_sha256": RAW_SHA,
        "tensor_sha256": TENSOR_SHA,
        "source_sha256": file_sha256(__file__),
        "encoder_sha256": file_sha256(
            ROOT / "ai-training/src/idps_ai/features/normalization_ablation.py"
        ),
        "selection": "Replay raw exact-conflict exclusion and original modulo4 residues2/3; recover first eligible raw representative of each frozen selected view; original roles never reassigned",
        "near_rule": "content cosine>=.995 minus1e-7 tolerance, BOTH representations; exact projected KD radius superset then full512 dot. TRAIN fixed except view conflicts/duplicates; CAL excludes TRAIN-near; DEV excludes TRAIN or originalCAL-near; no score-based changes",
        "within_role_views": "Quarantine mixed publisher-label challenger views for BOTH arms; dedupe same challenger view canonically first in original role for BOTH arms",
        "minimums": {
            "TRAIN_rows": 50000,
            "CAL_normal": 100,
            "CAL_anomalous": 100,
            "DEV_normal": 100,
            "DEV_anomalous": 100,
        },
        "label_task": "Publisher NORMAL/ANOMALOUS only; no attack-intent relabel or independentGT claim",
        "Oracle_cohorts": "Do not mix incompatible supervision; reserve their fixed TRAIN diagnostics/CAL thresholds/exposed DEV for separate Oracle-stratum analysis",
        "sealed_prospective_access": False,
        "model_scores_computed": 0,
    }
    protocol["protocol_sha256"] = digest(protocol)
    atomic_json(output / "preparation-protocol.json", protocol)
    assert file_sha256(RAW) == RAW_SHA and file_sha256(TENSOR) == TENSOR_SHA
    assert (
        file_sha256(README) == "86278f3ec7f420fb40a9318e3dec59ec58e0af1dfb3f52133e1cada5112691bb"
        and "license: mit" in README.read_text()
    )
    with np.load(TENSOR, allow_pickle=False) as d:
        numeric = d["numeric"].copy()
        original = d["content"].copy()
        labels = d["label"].copy()
        role = d["role"].copy()
        groups = d["group"].copy()
        views = d["view"].copy()
    assert int((role == 0).sum()) == 120435 and len(role) == 160796
    lookup = {v.decode(): i for i, v in enumerate(views)}
    selected_groups = set(groups.tolist())
    masks = {}
    for ordinal, row in enumerate(rows()):
        label = {"normal": 0, "anomalous": 1}.get(row[5])
        if (
            label is None
            or not isinstance(row[0], str)
            or not isinstance(row[1], str)
            or not row[0]
            or not row[1]
            or len(row[1]) > 8192
        ):
            continue
        key = hashlib.sha256(canonical_bytes(row[:5])).digest()
        masks[key] = masks.get(key, 0) | (1 << label)
        if ordinal % 100000 == 0:
            atomic_json(
                output / "progress.json",
                {
                    "phase": "RAW_CONFLICT_AUDIT",
                    "raw_rows": ordinal,
                    "elapsed": time.time() - started,
                },
            )
    conflicts = {k for k, v in masks.items() if v == 3}
    assert len(conflicts) == 192
    atomic_json(
        output / "raw-conflict-audit.json",
        {
            "raw_sha256": RAW_SHA,
            "unique_raw": len(masks),
            "conflicting_keys": [k.hex() for k in sorted(conflicts)],
        },
    )
    del masks
    candidate = np.zeros_like(original)
    found = np.zeros(len(role), bool)
    source_rows = np.full(len(role), -1, np.int64)
    raw_keys = np.zeros(len(role), dtype="S64")
    pending = []

    def flush():
        if not pending:
            return
        shared, split = from_symbols([r[2] for r in pending])
        for (ordinal, row, text, values, key, group), s, c in zip(
            pending, shared, split, strict=True
        ):
            view = hashlib.sha256(np.concatenate([values, s]).tobytes()).hexdigest()
            idx = lookup.get(view)
            if idx is None or found[idx]:
                continue
            assert (
                np.array_equal(s, original[idx])
                and np.array_equal(values, numeric[idx])
                and group == groups[idx]
            )
            assert labels[idx] == {"normal": 0, "anomalous": 1}[row[5]]
            found[idx] = True
            candidate[idx] = c
            source_rows[idx] = ordinal
            raw_keys[idx] = key.hex().encode()
        pending.clear()

    for ordinal, row in enumerate(rows()):
        if (
            row[5] not in ["normal", "anomalous"]
            or not isinstance(row[0], str)
            or not isinstance(row[1], str)
            or not row[0]
            or not row[1]
            or len(row[1]) > 8192
        ):
            continue
        key = hashlib.sha256(canonical_bytes(row[:5])).digest()
        if key in conflicts or int.from_bytes(key[:4], "big") % 4 not in (2, 3):
            continue
        try:
            safe, _ = symbolic_request(row[0], row[1], row[3], row[4])
            group = hashlib.sha256(safe.encode()).hexdigest().encode()
            if group not in selected_groups:
                continue
            values = encode_request(bounded_spec(), project_request(row[1], row[0])["numbers"])
            text, _ = rich_request_v2(row[0], row[1], row[3], row[4])
        except (ValueError, OverflowError):
            continue
        pending.append((ordinal, row, text, values, key, group))
        if len(pending) >= 128:
            flush()
        if ordinal % 10000 == 0:
            atomic_json(
                output / "progress.json",
                {
                    "phase": "RECONSTRUCT_SELECTED_VIEWS",
                    "raw_rows": ordinal,
                    "matched": int(found.sum()),
                    "required": len(found),
                    "elapsed": time.time() - started,
                },
            )
    flush()
    assert found.all(), f"Not all frozen views recovered: {found.sum()}/{len(found)}"
    atomic_json(
        output / "reconstruction.json",
        {
            "status": "PASS",
            "recovered": int(found.sum()),
            "original_control_bitwise_equal": True,
            "raw_conflicts": len(conflicts),
            "elapsed": time.time() - started,
        },
    )
    # Save the reconstruction before the bounded near audit, so a failure is recoverable.
    np.savez(
        output / "reconstruction.npz",
        numeric=numeric,
        control=original,
        challenger=candidate,
        label=labels,
        role=role,
        group=groups,
        view=views,
        source_row=source_rows,
        raw_key=raw_keys,
    )
    cv = [
        hashlib.sha256(np.concatenate([n, c]).tobytes()).hexdigest()
        for n, c in zip(numeric, candidate, strict=True)
    ]
    view_labels = {}
    for v, y in zip(cv, labels, strict=True):
        view_labels[v] = view_labels.get(v, 0) | (1 << int(y))
    mixed = {v for v, y in view_labels.items() if y == 3}
    eligible = np.array([v not in mixed for v in cv])
    dedup = Counter()
    for r in (0, 1, 2):
        seen = set()
        for i in np.flatnonzero(role == r):
            if cv[i] in seen:
                eligible[i] = False
                dedup[str(r)] += 1
            seen.add(cv[i])
    train = np.flatnonzero((role == 0) & eligible)
    cal = np.flatnonzero((role == 1) & eligible)
    dev = np.flatnonzero((role == 2) & eligible)
    near_totals = {}
    for name, content in [("shared", original), ("separate", candidate)]:
        for target, idx, refs in [
            ("CAL_train", cal, train),
            ("DEV_train", dev, train),
            ("DEV_cal", dev, np.flatnonzero(role == 1)),
        ]:
            mask, checked = near_mask(content[refs], content[idx], output / "near-progress.json")
            eligible[idx[mask]] = False
            near_totals[name + ":" + target] = {
                "query_rows": len(idx),
                "excluded": int(mask.sum()),
                "full_pairs_checked": checked,
            }
    coverage = {}
    for r, name in [(0, "TRAIN"), (1, "CALIBRATION"), (2, "DEVELOPMENT")]:
        idx = np.flatnonzero((role == r) & eligible)
        np.savez(
            output / (name.lower() + ".npz"),
            control=np.concatenate([numeric[idx], original[idx]], axis=1),
            challenger=np.concatenate([numeric[idx], candidate[idx]], axis=1),
            y=labels[idx],
            groups=groups[idx],
            view=views[idx],
            source_row=source_rows[idx],
        )
        coverage[name] = {
            "rows": len(idx),
            "publisher_NORMAL": int((labels[idx] == 0).sum()),
            "publisher_ANOMALOUS": int((labels[idx] == 1).sum()),
            "groups": len(set(groups[idx])),
        }
    passed = coverage["TRAIN"]["rows"] >= 50000 and all(
        coverage[k][label] >= 100
        for k in ["CALIBRATION", "DEVELOPMENT"]
        for label in ["publisher_NORMAL", "publisher_ANOMALOUS"]
    )
    report = {
        "schema_version": "scaled-normalization-corpus-1",
        "status": "PASS" if passed else "BLOCKED_INSUFFICIENT_NEAR_DISJOINT_COVERAGE",
        "original_role_counts": {str(i): int((role == i).sum()) for i in (0, 1, 2)},
        "coverage": coverage,
        "matched_control_bitwise_reconstruction": True,
        "reconstructed_raw_requests": len(found),
        "mixed_challenger_views_quarantined": len(mixed),
        "same_view_duplicates_by_role": dict(dedup),
        "near_checks": near_totals,
        "role_reassigned": False,
        "protocol_sha256": protocol["protocol_sha256"],
        "license": "Pinned publisher MIT declaration; no source/capture/GT independence certified",
        "model_scores_computed": 0,
        "sealed_prospective_opened": False,
        "source_fitting": "Publisher anomaly classification only, no Oracle labels pooled",
        "elapsed_seconds": time.time() - started,
        "files_sha256": {p.name: file_sha256(p) for p in output.glob("*.npz")},
    }
    report["dataset_fingerprint"] = digest(report)
    atomic_json(output / "corpus-report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    with threadpool_limits(limits=1):
        prepare(a.output.resolve())

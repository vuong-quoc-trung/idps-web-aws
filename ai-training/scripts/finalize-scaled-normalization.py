#!/usr/bin/env python3
"""Finalize cached reconstruction with certified PCA-indexed cosine quarantine.

PCA is only a search acceleration. Full512-dimensional cosine and threshold are
unchanged; projection cannot increase distance, so no near pair is missed.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from sklearn.utils.extmath import randomized_svd
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256


def near_mask(reference, queries, progress):
    if not len(reference) or not len(queries):
        return np.zeros(len(queries), bool), 0
    dimensions = min(16, len(reference), reference.shape[1])
    _, _, v = randomized_svd(
        reference - reference.mean(axis=0), n_components=dimensions, n_iter=2, random_state=20261107
    )
    q, _ = np.linalg.qr(v.T.astype(np.float64))
    assert np.allclose(q.T @ q, np.eye(dimensions), atol=1e-12)
    tree = cKDTree(reference @ q)
    mask = np.zeros(len(queries), bool)
    pairs = 0
    for i, row in enumerate(queries):
        candidates = tree.query_ball_point(row.astype(np.float64) @ q, r=0.10002, workers=1)
        for k in range(0, len(candidates), 1024):
            idx = candidates[k : k + 1024]
            pairs += len(idx)
            if np.any(
                np.asarray(reference[idx], np.float64) @ row.astype(np.float64) >= 0.995 - 1e-7
            ):
                mask[i] = True
                break
        if i % 1000 == 0:
            atomic_json(
                progress,
                {
                    "query": i,
                    "total": len(queries),
                    "excluded": int(mask.sum()),
                    "full_pairs_checked": pairs,
                },
            )
    return mask, pairs


def finalize(cache, output):
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    started = time.time()
    original = json.loads((cache / "reconstruction.json").read_text())
    assert original["status"] == "PASS" and original["recovered"] == 160796
    protocol = json.loads((cache / "preparation-protocol.json").read_text())
    update = {
        "source_sha256": file_sha256(__file__),
        "cached_reconstruction_sha256": file_sha256(cache / "reconstruction.npz"),
        "original_protocol_sha256": protocol["protocol_sha256"],
        "change": "Computational acceleration only: orthonormal PCA16 search basis instead of coordinate32, same complete cosine>=.995 rule and radius. Short-circuit rows already excluded by another representation; same union quarantine.",
        "label_safety": "Mixed labels quarantined within each immutable role only; CAL/DEV labels cannot change TRAIN eligibility",
        "minimums": protocol["minimums"],
        "near_threshold": 0.995,
        "dot_tolerance": 1e-7,
        "projected_radius": 0.10002,
        "no_model_scores": True,
        "no_prospective_access": True,
    }
    atomic_json(output / "finalization-protocol.json", update)
    with np.load(cache / "reconstruction.npz", allow_pickle=False) as d:
        numeric = d["numeric"]
        shared = d["control"]
        separate = d["challenger"]
        labels = d["label"]
        role = d["role"]
        groups = d["group"]
        views = d["view"]
        source_rows = d["source_row"]
    cv = [
        hashlib.sha256(np.concatenate([n, c]).tobytes()).hexdigest()
        for n, c in zip(numeric, separate, strict=True)
    ]
    eligible = np.ones(len(role), bool)
    mixed_counts = {}
    dedup = Counter()
    for r in (0, 1, 2):
        byview = {}
        for i in np.flatnonzero(role == r):
            byview[cv[i]] = byview.get(cv[i], 0) | (1 << int(labels[i]))
        mixed = {v for v, y in byview.items() if y == 3}
        mixed_counts[str(r)] = len(mixed)
        seen = set()
        for i in np.flatnonzero(role == r):
            if cv[i] in mixed:
                eligible[i] = False
            if cv[i] in seen:
                eligible[i] = False
                dedup[str(r)] += 1
            seen.add(cv[i])
    train = np.flatnonzero((role == 0) & eligible)
    near = {}
    for name, content in [("shared", shared), ("separate", separate)]:
        for label, r, refs in [
            ("CAL_train", 1, train),
            ("DEV_train", 2, train),
            ("DEV_originalCAL", 2, np.flatnonzero(role == 1)),
        ]:
            idx = np.flatnonzero((role == r) & eligible)
            atomic_json(
                output / "phase.json", {"phase": name + ":" + label, "queries_remaining": len(idx)}
            )
            mask, pairs = near_mask(content[refs], content[idx], output / "near-progress.json")
            eligible[idx[mask]] = False
            near[name + ":" + label] = {
                "query_rows_remaining": len(idx),
                "excluded": int(mask.sum()),
                "full_pairs_checked": pairs,
            }
    coverage = {}
    for r, name in [(0, "TRAIN"), (1, "CALIBRATION"), (2, "DEVELOPMENT")]:
        idx = np.flatnonzero((role == r) & eligible)
        np.savez(
            output / (name.lower() + ".npz"),
            control=np.concatenate([numeric[idx], shared[idx]], axis=1),
            challenger=np.concatenate([numeric[idx], separate[idx]], axis=1),
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
        "schema_version": "scaled-normalization-corpus-2",
        "status": "PASS" if passed else "BLOCKED_INSUFFICIENT_NEAR_DISJOINT_COVERAGE",
        "original_role_counts": {str(i): int((role == i).sum()) for i in (0, 1, 2)},
        "coverage": coverage,
        "matched_control_bitwise_reconstruction": True,
        "reconstructed_raw_requests": 160796,
        "mixed_challenger_views_within_role_quarantined": mixed_counts,
        "same_view_duplicates_by_role": dict(dedup),
        "near_checks": near,
        "TRAIN_selection_uses_CAL_DEV_labels": False,
        "role_reassigned": False,
        "protocol_sha256": protocol["protocol_sha256"],
        "finalization_protocol_sha256": file_sha256(output / "finalization-protocol.json"),
        "cached_reconstruction_sha256": update["cached_reconstruction_sha256"],
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
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    with threadpool_limits(limits=1):
        finalize(a.cache.resolve(), a.output.resolve())

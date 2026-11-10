#!/usr/bin/env python3
"""Finalize/rebuild committed observations, never call source ingestion."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import PipelineError, atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.data.resumable_near import audit, original_pairs, pack_vectors
from idps_ai.data.student_training import StudentIndex


def load(path):
    return json.loads(Path(path).read_text())


def binding_and_refs(root, output):
    checksum = hashlib.sha256()
    refs = {}
    count = 0
    with sqlite3.connect(f"file:{output}/index.sqlite?mode=ro", uri=True) as db:
        for i, rj, mj in db.execute(
            "SELECT r.i,r.j,student.j FROM r JOIN student USING(i) ORDER BY r.i"
        ):
            checksum.update(canonical_bytes([i, rj, mj]) + b"\n")
            ref = json.loads(mj)["feature_ref"]
            if ref:
                refs.setdefault(ref["shard"], []).append((count, ref["slot"]))
                count += 1
    shas = {name: file_sha256(output / name) for name in sorted(refs)}
    state = {
        "original_plan_fingerprint": load(root / "plan.json")["fingerprint"],
        "normalized_metadata_sha256": checksum.hexdigest(),
        "feature_shards": shas,
        "feature_rows": count,
    }
    return digest(state), refs, state


def prepare_cache(root, output):
    binding, refs, source = binding_and_refs(root, output)
    directory = output / "near-resumable-v1"
    if not (directory / "vectors-manifest.json").exists():
        contents = np.empty((source["feature_rows"], 512), dtype=np.float32)
        for name, places in refs.items():
            with np.load(output / name, allow_pickle=False) as z:
                x = z["x"]
            if (
                x.ndim != 2
                or x.shape[1] != 588
                or x.dtype != np.float32
                or not np.isfinite(x).all()
            ):
                raise PipelineError("Invalid source shard; no audit cache written")
            for target, slot in places:
                contents[target] = x[slot, 76:]
        pack_vectors(directory, contents, binding)
    atomic_json(directory / "source-binding.json", source)
    return directory, binding


def finish(root, output):
    directory, binding = prepare_cache(root, output)
    result = audit(directory, binding)
    assert result["complete"]
    marker = output / "near-audit.json"
    report = {
        "metric": "existingcontentcosine>=0.995with1e-7tolerance",
        "frame_rows": result["original_rows"],
        "intra_frame_pairs": result["pairs"],
        "coverage": "EXHAUSTIVE_BLOCKED_COMMON_CONTRACT",
        "index_saturation": 0,
        "physical_duplicate_claim": False,
        "protected_common_v2": "checkedbeforeteacher",
        "legacy_incompatibleencoder_near": "PARTIAL; allknownlegacyexacttemplatesexcluded",
        "unknown_global_raw_lineage": "PARTIAL",
        "all_new_roles": "TRAIN_STAGING_EXPOSED; no newevaluation split",
        "audit_algorithm": result["algorithm"],
        "unique_content_vectors": result["unique_vectors"],
        "compressed_vector_fingerprint": result["vector_fingerprint"],
    }
    if marker.exists() and load(marker) != report:
        raise PipelineError("Existing near report differs; preserve both attempts")
    atomic_json(marker, report)
    index = StudentIndex(output, load(root / "plan.json"))
    assert index.cursor == 100000
    try:
        summary = index.finish(report, load(root / "plan.json")["teacher"])
    finally:
        index.close()
    n = 0
    for line in (output / "training-index.jsonl").open():
        row = json.loads(line)
        assert row["features"] is not None and not row["optimization_consumed"]
        n += 1
    assert n == summary["counts"]["DEDUPLICATED_TRAINING_EXAMPLES"]
    return summary


def clone_derivative(root, output):
    """Independent exact-graph/ledger rebuild, no raw parser/teacher re-ingestion."""
    source = root / "materialized"
    target = StudentIndex(output, load(root / "plan.json"))
    db = sqlite3.connect(f"file:{source}/index.sqlite?mode=ro", uri=True)
    try:
        start = target.cursor

        def entries():
            query = "SELECT r.i,r.j,student.j,blocked.why FROM r JOIN student USING(i) LEFT JOIN blocked USING(i) WHERE r.i>=? ORDER BY r.i"
            for i, rj, mj, blocked in db.execute(query, (start,)):
                if blocked is not None:
                    target.db.execute("INSERT OR IGNORE INTO blocked VALUES(?,?)", (i, blocked))
                yield json.loads(rj), json.loads(mj)

        target.append_student(entries())
        assert target.cursor == load(root / "plan.json")["candidate_positions"]
    finally:
        target.close()
        db.close()
    # Independent byte copies, not hard links to mutable original files.
    (output / "features").mkdir(exist_ok=True)
    for old in sorted((source / "features").glob("*.npz")):
        new = output / "features" / old.name
        if not new.exists():
            temp = new.with_suffix(".copying")
            shutil.copyfile(old, temp)
            temp.replace(new)
        if file_sha256(old) != file_sha256(new):
            raise PipelineError("Rebuild feature copy mismatch")


def benchmark(root, attempt):
    # Deterministic already-exposed prefix; no scores, labels or source selection changed.
    contents = []
    total = 0
    for p in sorted((root / "materialized/features").glob("*.npz")):
        with np.load(p, allow_pickle=False) as z:
            x = z["x"][:, 76:]
        take = min(len(x), 4096 - total)
        contents.append(x[:take])
        total += take
        if total == 4096:
            break
    content = np.concatenate(contents)
    before = time.perf_counter()
    expected = original_pairs(content)
    old_seconds = time.perf_counter() - before
    path = attempt / "benchmark-near"
    pack_vectors(path, content, "bounded4096-exposed-prefix")
    before = time.perf_counter()
    actual = audit(path, "bounded4096-exposed-prefix")
    new_seconds = time.perf_counter() - before
    assert expected == actual["pairs"]
    report = {
        "state": "PASS",
        "rows": len(content),
        "unique_vectors": actual["unique_vectors"],
        "original_pairs": expected,
        "weighted_pairs": actual["pairs"],
        "old_wall_seconds": old_seconds,
        "new_audit_wall_seconds": new_seconds,
        "cache_build_in_new_time": False,
        "same_metric": True,
        "quadratic_scope": "uniquevectorsworstcase; exact allpairs coverage, no approximateLSH/pruning",
        "rebuild_scope": "normalized metadata/features finalization rebuild; raw feature extraction is NOT repeated",
    }
    atomic_json(attempt / "benchmark.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--attempt", type=Path)
    p.add_argument("--action", choices=["finish", "clone", "benchmark"], required=True)
    a = p.parse_args()
    with threadpool_limits(limits=1):
        if a.action == "finish":
            finish(a.root, a.output)
        elif a.action == "clone":
            clone_derivative(a.root, a.output)
        else:
            benchmark(a.root, a.attempt)

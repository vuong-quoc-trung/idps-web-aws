#!/usr/bin/env python3
"""One supervised, resumable200K derivative; no optimization or live deployment.

Reuse original ingestion, SQLite graph and independent adaptive supervisor. The
original100K files/code remain immutable. Every long phase runs inside the same
quota-limited worker; only its supervisor starts a separate safety watchdog.
"""

import argparse
import importlib.util
import itertools
import json
import os
import shutil
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.data.local_release import (
    requalified_reasons,
    role_for_component,
    verify_windows,
)
from idps_ai.data.resumable_near import audit
from idps_ai.data.student_training import StudentIndex, protected_near
from idps_ai.features.rich_content import rich_request
from idps_ai.features.safe_content import symbolic_request
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.checkpoint import RunLock, load_checkpoint

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"
PILOT = (
    REPO
    / "ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1"
)
CONFIG = REPO / "ai-training/configs/research/local-release-200k-20261110.json"


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), Path(__file__).with_name(name)
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def readonly(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def code_hashes():
    names = [
        Path(__file__),
        CONFIG,
        REPO / "ai-training/src/idps_ai/data/local_release.py",
        REPO / "ai-training/src/idps_ai/data/student_training.py",
        REPO / "ai-training/src/idps_ai/data/scaling_admission.py",
        REPO / "ai-training/src/idps_ai/data/resumable_near.py",
        REPO / "ai-training/src/idps_ai/training/adaptive_thermal.py",
        REPO / "ai-training/src/idps_ai/training/heartbeat.py",
        Path(__file__).with_name("student-data-pipeline.py"),
        Path(__file__).with_name("student-data-recovery.py"),
        Path(__file__).with_name("adaptive-thermal-guard.py"),
    ]
    return {str(p.relative_to(REPO)): file_sha256(p) for p in names}


def initialize(root):
    assert not root.exists(), "Fresh run only; never overwrite"
    cfg = load(CONFIG)
    verify_windows()
    assert load(OLD / "completion.json")["state"] == "COMPLETED"
    assert load(PILOT / "training-completion.json")["state"] == "COMPLETED"
    hw = hardware_snapshot()
    s = SensorReader(hw).read(time.monotonic())
    assert s["temperature_C"] < 75 and not s["hardware_emergency"]
    p = module("student-data-pipeline.py")
    parquet = pq.ParquetFile(p.WAF / "train.parquet")
    assert parquet.metadata.num_rows == 1924461
    oldplan = load(OLD / "plan.json")
    root.mkdir(parents=True, mode=0o700)
    shutil.copyfile(OLD / "identity.key", root / "identity.key")
    (root / "identity.key").chmod(0o600)
    plan = {
        "run_id": root.name,
        "version": "local-release200k-v1",
        "candidate_positions": 200000,
        "new_positions": 100000,
        "old_dataset_fingerprint": load(OLD / "completion.json")["summary"]["fingerprint"],
        "old_plan_sha256": file_sha256(OLD / "plan.json"),
        "old_source_bindings": oldplan["source_hashes"],
        "old_ledger_sha256": file_sha256(OLD / "materialized/ledger.jsonl"),
        "old_shard_sha256": load(OLD / "attempts/recovery-a2/integrity.json")["shard_hashes"],
        "pilot_split_sha256": file_sha256(PILOT / "data/split.json"),
        "pilot_data_sha256": load(PILOT / "plan.json")["data_files"],
        "key_fingerprint": file_sha256(root / "identity.key"),
        "code_hashes": code_hashes(),
        "configuration": cfg,
        "new_windows": verify_windows(),
        "teacher": oldplan["teacher"],
        "feature_contract": oldplan["feature_contract"],
        "training": "NOT_AUTHORIZED",
        "sealed_access": False,
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    attempt = root / "attempts/data-v1"
    attempt.mkdir(parents=True)
    atomic_json(attempt / "hardware.json", hw)
    atomic_json(
        attempt / "recovery-plan.json",
        {
            "original_run_id": root.name,
            "preflight": False,
            "warning_C": 85,
            "throttle_C": 90,
            "strong_throttle_C": 93,
            "cooldown_seconds": 15,
            "maximum_cooldown_seconds": 300,
            "effective_emergency_C": hw["effective_emergency_C"],
            "runtime_seconds": 21600,
            "fingerprint": plan["fingerprint"],
        },
    )
    atomic_json(root / "status.json", {"state": "PREPARED", "run_id": root.name})


def verify(root, attempt=None):
    plan = load(root / "plan.json")
    c = dict(plan)
    assert c.pop("fingerprint") == digest(c) and plan["code_hashes"] == code_hashes()
    assert file_sha256(root / "identity.key") == plan["key_fingerprint"]
    assert file_sha256(OLD / "plan.json") == plan["old_plan_sha256"]
    assert file_sha256(OLD / "materialized/ledger.jsonl") == plan["old_ledger_sha256"]
    assert file_sha256(PILOT / "data/split.json") == plan["pilot_split_sha256"]
    return load(attempt / "recovery-plan.json") if attempt else plan


def raw_windows(windows):
    p = module("student-data-pipeline.py")
    parquet = pq.ParquetFile(p.WAF / "train.parquet")
    bases = [0, parquet.metadata.row_group(0).num_rows]
    for a, b in windows:
        group = int(a >= bases[1])
        seen = bases[group]
        for batch in parquet.iter_batches(batch_size=256, row_groups=[group], use_threads=False):
            stop = seen + batch.num_rows
            if stop > a:
                lo, hi = max(a, seen) - seen, min(b, stop) - seen
                for j, r in enumerate(batch.slice(lo, max(0, hi - lo)).to_pylist(), max(a, seen)):
                    yield j, r
            seen = stop
            if seen >= b:
                break


def feature_matrix(folder, rows):
    result = np.empty((len(rows), 588), np.float32)
    places = {}
    for j, m in enumerate(rows):
        ref = m["feature_ref"]
        places.setdefault(ref["shard"], []).append((j, ref["slot"]))
    for name, slots in places.items():
        with np.load(folder / name, allow_pickle=False) as z:
            x = z["x"]
            assert x.shape[1] == 588 and x.dtype == np.float32 and np.isfinite(x).all()
            for j, slot in slots:
                result[j] = x[slot]
    return result


def protection(root, plan, hb):
    p = module("student-data-pipeline.py")
    dest = root / "protection-build"
    marker = root / "protection-ready.json"
    if marker.exists():
        for f, h in load(marker)["files"].items():
            assert file_sha256(root / f) == h
        return
    hb.write(phase="ROLE_AWARE_PROTECTION")
    idx = StudentIndex(dest, plan)
    legacy = []
    train_keys, heldout = set(), set()
    for folder, name, islegacy in p.LEGACY:
        report = load(REPO / folder / "report.json")
        assert file_sha256(REPO / folder / name) == report["data_file_sha256"]
        with np.load(REPO / folder / name, allow_pickle=False) as z:
            roles, groups, views = z["role"], z["group"], z["view"]
            mask = roles != 0
            heldout.update(v.decode() for v in groups[mask])
            if islegacy:
                train_keys.update(v.decode() for v in groups[~mask])
                legacy.append(np.unique(z["content"][mask], axis=0))
            idx.db.executemany(
                "INSERT OR IGNORE INTO protected_group VALUES(?)",
                ((v.decode(),) for v in groups[mask]),
            )
            idx.db.executemany(
                "INSERT OR IGNORE INTO protected_view VALUES(?)",
                ((v.decode(),) for v in views[mask]),
            )
    with readonly(OLD / "protection-build/index.sqlite") as db:
        for table in ["protected_route", "old_train_group"]:
            idx.db.executemany(
                f"INSERT OR IGNORE INTO {table} VALUES(?)", db.execute(f"SELECT k FROM {table}")
            )
    idx.db.commit()
    idx.close()
    with np.load(OLD / "protected-vectors.npz", allow_pickle=False) as z:
        full, runtime = z["full"].copy(), z["runtime"].copy()
    oldrows = [json.loads(line) for line in (OLD / "materialized/ledger.jsonl").open()]
    protected_ids = {v["row"] for v in load(PILOT / "data/split.json") if v["role"] != "TRAIN"}
    heldrows = [m for m in oldrows if m["row"] in protected_ids]
    # Existing pilot CAL/EVAL remain protected even though their aggregate results
    # were exposed. No old heldout sample is reclaimed for the final model.
    hx = feature_matrix(OLD / "materialized", heldrows)
    p.npz_atomic(
        root / "protected-vectors.npz",
        full=np.unique(np.concatenate([full, hx[:, 76:]]), axis=0),
        runtime=runtime,
    )
    p.npz_atomic(root / "legacy-heldout.npz", safe=legacy[0], rich=legacy[1])
    key = (root / "identity.key").read_bytes()
    with readonly(OLD / "materialized/index.sqlite") as db:
        normalized = {i: json.loads(rj) for i, rj in db.execute("SELECT i,j FROM r")}
    pilot_groups = sorted({g for i in protected_ids for g in normalized[i]["groups"]})
    pilot_views = sorted({normalized[i]["view_key"] for i in protected_ids})
    train_only = {p.mac(key, "safe-template", v) for v in train_keys - heldout}
    heldout_keys = {p.mac(key, "safe-template", v) for v in heldout}
    flags = {}
    marked = []
    for m in oldrows:
        g = set(normalized[m["row"]]["groups"])
        f = flags.setdefault(m["component"], False)
        flags[m["component"]] = (
            f or bool(g & heldout_keys) or "PROTECTED_NEAR_COMMON_CONTRACT" in m["reasons"]
        )
        if g & train_only and m["decision"] != "TRAINING_ELIGIBLE":
            marked.append(m)
    candidates = [m["row"] for m in marked if not flags[m["component"]]]
    assert len(candidates) == 27235, (
        "Diagnostic candidate set changed; stop rather than force counts"
    )
    atomic_json(root / "requalification-candidates.json", candidates)
    atomic_json(
        root / "pilot-protection.json",
        {"groups": pilot_groups, "views": pilot_views, "rows": sorted(protected_ids)},
    )
    atomic_json(
        root / "protection-ready.json",
        {
            "candidates": len(candidates),
            "legacy_encoders": ["safe_content", "rich_content_v1"],
            "heldout_counts": [len(x) for x in legacy],
            "pilot_CAL_EVAL_rows": len(protected_ids),
            "files": {
                str(f.relative_to(root)): file_sha256(f)
                for f in [
                    dest / "index.sqlite",
                    root / "protected-vectors.npz",
                    root / "legacy-heldout.npz",
                    root / "requalification-candidates.json",
                    root / "pilot-protection.json",
                ]
            },
            "sealed_access": False,
        },
    )


class LegacyCheck:
    def __init__(self, root):
        self.root = root
        self.vectorizer = HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )
        with np.load(root / "legacy-heldout.npz", allow_pickle=False) as z:
            self.references = [z["safe"].copy(), z["rich"].copy()]

    def check(self, requests):
        hits = np.zeros(len(requests), bool)
        # Separate original encoder contracts, never compare different spaces.
        for encode, references in zip(
            [symbolic_request, rich_request], self.references, strict=True
        ):
            texts, slots = [], []
            for i, r in enumerate(requests):
                try:
                    texts.append(encode(r["method"], r["url"], r["headers"], r["body"])[0])
                    slots.append(i)
                except (PipelineError, ValueError, TypeError, KeyError, OverflowError):
                    hits[i] = True  # Unverifiable representation stays quarantined.
            if texts:
                x = self.vectorizer.transform(texts).toarray().astype(np.float32)
                hits[slots] |= protected_near(x, references)
        return hits


def legacy_review(root, hb):
    marker = root / "legacy-review-complete.json"
    if marker.exists():
        assert file_sha256(root / "legacy-review.sqlite") == load(marker)["sha256"]
        return
    candidates = set(load(root / "requalification-candidates.json"))
    with readonly(OLD / "materialized/index.sqlite") as db:
        positions = dict(db.execute("SELECT n,i FROM r WHERE s='waf'"))
    selected_positions = {pos: i for pos, i in positions.items() if i in candidates}
    db = sqlite3.connect(root / "legacy-review.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS checked(i INTEGER PRIMARY KEY,hit INTEGER)")
    done = {i for (i,) in db.execute("SELECT i FROM checked")}
    checker = LegacyCheck(root)
    p = module("student-data-pipeline.py")
    # Raw source is read only for provenance-bound legacy projection, not old
    # re-ingestion or new observation counting. Frozen588 shards are reused.
    stream = (
        (positions[pos], r)
        for pos, r in raw_windows([(0, 49964), (1048576, 1098539)])
        if pos in selected_positions and positions[pos] not in done
    )
    while batch := list(itertools.islice(stream, 64)):
        hits = checker.check(
            [
                p.validate_http({k: r[k] for k in ["method", "url", "headers", "body"]})
                for _, r in batch
            ]
        )
        db.executemany(
            "INSERT INTO checked VALUES(?,?)",
            [(i, int(hit)) for (i, _), hit in zip(batch, hits, strict=True)],
        )
        db.commit()
        hb.write(
            phase="LEGACY_REQUALIFICATION",
            checked=db.execute("SELECT count(*) FROM checked").fetchone()[0],
            planned=27235,
        )
    assert db.execute("SELECT count(*) FROM checked").fetchone()[0] == 27235
    counts = dict(db.execute("SELECT hit,count(*) FROM checked GROUP BY hit"))
    db.close()
    atomic_json(
        marker,
        {
            "checked": 27235,
            "legacy_near_hits": counts.get(1, 0),
            "sha256": file_sha256(root / "legacy-review.sqlite"),
            "independent_review": "PENDING",
        },
    )


def clone_old(root, plan, hb):
    idx = StudentIndex(root / "materialized", plan)
    start = idx.cursor
    if start >= 100000:
        idx.close()
        return
    p = module("student-data-pipeline.py")
    key = (root / "identity.key").read_bytes()
    old = readonly(OLD / "materialized/index.sqlite")
    prot = readonly(root / "protection-build/index.sqlite")
    review = readonly(root / "legacy-review.sqlite")
    hits = dict(review.execute("SELECT i,hit FROM checked"))
    review.close()
    pilot = load(root / "pilot-protection.json")
    pg, pv = set(pilot["groups"]), set(pilot["views"])
    with np.load(root / "protected-vectors.npz", allow_pickle=False) as z:
        refs = z["full"].copy()
    # Map candidate views to stored vectors without changing extraction semantics.
    candidates = [
        json.loads(line)
        for line in (OLD / "materialized/ledger.jsonl").open()
        if json.loads(line)["row"] in hits
    ]
    cx = feature_matrix(OLD / "materialized", candidates)
    current_near = {}
    for a in range(0, len(cx), 64):
        flags = protected_near(cx[a : a + 64, 76:], refs)
        current_near.update(
            {m["row"]: bool(v) for m, v in zip(candidates[a : a + 64], flags, strict=True)}
        )
    del cx
    files = {}
    for f in sorted((OLD / "materialized/features").glob("*.npz")):
        new = root / "materialized/features" / f.name
        new.parent.mkdir(parents=True, exist_ok=True)
        sha = file_sha256(f)
        assert sha == plan["old_shard_sha256"]["features/" + f.name]
        if not new.exists():
            shutil.copyfile(f, new.with_suffix(".copying"))
            new.with_suffix(".copying").replace(new)
        assert file_sha256(new) == sha
        files[str(new.relative_to(root))] = sha
    atomic_json(root / "reused-shards.json", files)

    def entries():
        for i, rj, mj in old.execute(
            "SELECT r.i,r.j,student.j FROM r JOIN student USING(i) WHERE i>=? ORDER BY i", (start,)
        ):
            n, m = json.loads(rj), json.loads(mj)
            direct = False
            if i in hits:
                g = n["groups"][0]
                # This is an opaque key. Compare by re-HMACing the known SHA keys,
                # never interpret a private group as a raw template hash.
                protected_groups = group_hmacs
                direct = g in protected_groups or n["view_key"] in view_hmacs
                # Existing route protection is retained by keeping all other
                # original flags; original matched-route candidates cannot have a
                # known source/template-only proof, so retain them conservatively.
                direct |= i in route_unknown
            held = bool(set(n["groups"]) & pg) or n["view_key"] in pv or current_near.get(i, False)
            n["reasons"] = requalified_reasons(
                n["reasons"],
                candidate=i in hits,
                exact_protected=direct,
                legacy_near=bool(hits.get(i, 0)),
                new_heldout=held,
            )
            if any(v.startswith("PROTECTED") for v in n["reasons"]):
                idx.db.execute(
                    "INSERT OR REPLACE INTO blocked VALUES(?,?)", (i, "PROTECTED_EXISTING_ROLE")
                )
            if i % 256 == 0:
                hb.write(phase="REUSE_OLD_METADATA", reused_positions=i)
            yield n, m

    group_hmacs = {
        p.mac(key, "safe-template", k) for (k,) in prot.execute("SELECT k FROM protected_group")
    }
    view_hmacs = {
        p.mac(key, "full588view", k) for (k,) in prot.execute("SELECT k FROM protected_view")
    }
    # Old normalized records do not retain route hashes. No route match can be
    # removed on missing evidence; inspect source only for these finite candidates.
    route_unknown = set(hits)
    routes = {k for (k,) in prot.execute("SELECT k FROM protected_route")}
    from urllib.parse import urlsplit

    positions = dict(old.execute("SELECT n,i FROM r WHERE s='waf'"))
    for pos, r in raw_windows([(0, 49964), (1048576, 1098539)]):
        i = positions[pos]
        if i in hits and p.mac(key, "route", [r["method"], urlsplit(r["url"]).path]) not in routes:
            route_unknown.discard(i)
    idx.append_student(entries())
    assert idx.cursor == 100000
    idx.close()
    old.close()
    prot.close()


def ingest_new(root, plan, hb):
    p = module("student-data-pipeline.py")
    checker = LegacyCheck(root)
    pilot = load(root / "pilot-protection.json")
    pg, pv = set(pilot["groups"]), set(pilot["views"])
    extra = {}

    def frames(_root, start, stop):
        stream = itertools.islice(raw_windows(verify_windows()), start, stop)
        while batch := list(itertools.islice(stream, 256)):
            valid = [
                p.validate_http({k: r[k] for k in ["method", "url", "headers", "body"]})
                for _, r in batch
            ]
            flags = checker.check(valid)
            extra.clear()
            extra.update({pos: bool(v) for (pos, _), v in zip(batch, flags, strict=True)})
            yield from (("waf", pos, r) for pos, r in batch)

    class CheckedIndex(StudentIndex):
        def append_student(self, entries):
            start = self.cursor

            def checked():
                for offset, (n, m) in enumerate(entries):
                    if m["target"] is None:
                        n["reasons"].append("NO_PUBLISHER_TARGET")
                    if extra[n["source_row"]]:
                        n["reasons"].append("PROTECTED_LEGACY_HELDOUT_NEAR")
                    if set(n["groups"]) & pg or n["view_key"] in pv:
                        n["reasons"].append("PROTECTED_COMPLETED_PILOT_HOLDOUT")
                    if any(v.startswith("PROTECTED") for v in n["reasons"]):
                        self.db.execute(
                            "INSERT OR REPLACE INTO blocked VALUES(?,?)",
                            (start + offset, "PROTECTED_EXISTING_ROLE"),
                        )
                    yield n, m

            super().append_student(checked())
            hb.write(phase="INGEST_ADDITIONAL_ONLY", additional_positions=self.cursor)

    p.verify = lambda _root: plan
    p.frames = frames
    p.StudentIndex = CheckedIndex
    p.ingest(root, root / "additional", 100000)


def merge_new(root, plan, hb):
    idx = StudentIndex(root / "materialized", plan)
    start = idx.cursor
    assert 100000 <= start <= 200000
    old = readonly(root / "additional/index.sqlite")
    assert old.execute("SELECT count(*) FROM r").fetchone()[0] == 100000
    remap = {}
    for src in sorted((root / "additional/features").glob("*.npz")):
        a, b = map(int, src.stem.split("-"))
        name = f"features/{a + 100000:09}-{b + 100000:09}.npz"
        dst = root / "materialized" / name
        if not dst.exists():
            shutil.copyfile(src, dst.with_suffix(".copying"))
            dst.with_suffix(".copying").replace(dst)
        assert file_sha256(src) == file_sha256(dst)
        remap["features/" + src.name] = name

    def entries():
        query = "SELECT r.i,r.j,student.j,blocked.why FROM r JOIN student USING(i) LEFT JOIN blocked USING(i) WHERE r.i>=? ORDER BY r.i"
        for i, rj, mj, blocked in old.execute(query, (start - 100000,)):
            n, m = json.loads(rj), json.loads(mj)
            if m["feature_ref"]:
                m["feature_ref"]["shard"] = remap[m["feature_ref"]["shard"]]
            if blocked:
                idx.db.execute("INSERT OR REPLACE INTO blocked VALUES(?,?)", (i + 100000, blocked))
            if i % 256 == 0:
                hb.write(phase="MERGE_METADATA", union_positions=i + 100000)
            yield n, m

    idx.append_student(entries())
    assert idx.cursor == 200000
    idx.close()
    old.close()


def finalize(root, plan, hb):
    f = module("student-finalize.py")
    output = root / "materialized"
    hb.write(phase="UNION_EXACT_NEAR_AUDIT")
    directory, binding = f.prepare_cache(root, output)
    near = audit(directory, binding)
    assert near["complete"]
    report = {
        "algorithm": near["algorithm"],
        "pairs": near["pairs"],
        "unique_vectors": near["unique_vectors"],
        "rows": near["original_rows"],
        "legacy_near": "same-original-encoder heldouts checked",
        "global_raw_campaign_lineage": "PARTIAL",
        "physical_request_claim": False,
    }
    idx = StudentIndex(output, plan)
    summary = idx.finish(report, plan["teacher"])
    assert idx.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert idx.db.execute("SELECT count(*) FROM r").fetchone()[0] == 200000
    assert (
        idx.db.execute("SELECT count(*) FROM (SELECT s,n FROM r GROUP BY s,n)").fetchone()[0]
        == 200000
    )
    idx.close()
    # Re-run deterministic metadata finalization (not a second raw ingestion).
    idx = StudentIndex(output, plan)
    again = idx.finish(report, plan["teacher"])
    idx.close()
    assert summary == again
    make_training_config(root, summary, hb)
    candidates = set(load(root / "requalification-candidates.json"))
    recovered = []
    retained_old, new_accepted = 0, 0
    with (root / "legacy-disposition.jsonl").open("w") as report:
        for m in map(json.loads, (output / "ledger.jsonl").open()):
            if m["decision"] == "TRAINING_ELIGIBLE":
                if m["row"] in candidates:
                    recovered.append(m["row"])
                if m["row"] < 100000:
                    retained_old += 1
                else:
                    new_accepted += 1
            if m["row"] in candidates:
                report.write(
                    json.dumps(
                        {
                            "row": m["row"],
                            "decision": m["decision"],
                            "reasons": m["reasons"],
                            "target": m["target"],
                            "tier": m["tier"],
                        }
                    )
                    + "\n"
                )
    atomic_json(
        root / "release-accounting.json",
        {
            "source_positions": 200000,
            "new_positions": 100000,
            "old_positions_reused": 100000,
            "old_source_reingestion": 0,
            "legacy_candidates_reviewed": 27235,
            "recovered_candidate_records": len(recovered),
            "eligible_old_records_after_protection": retained_old,
            "eligible_new_records": new_accepted,
            "source_tiers": summary["source_primary_tiers"],
            "accepted_tiers": summary["accepted_primary_tiers"],
            "accepted_views": summary["unique_feature_views_accepted"],
            "publisher_classes": summary["class_distribution_by_task"],
            "independent_human_review": "PENDING",
            "new_observations_gap_to_200K": 0,
            "verified_physical_training_requests": 0,
        },
    )
    oldindex = load(OLD / "materialized/summary.json")
    assert oldindex["fingerprint"] == plan["old_dataset_fingerprint"]
    assert file_sha256(OLD / "materialized/ledger.jsonl") == plan["old_ledger_sha256"]
    atomic_json(
        root / "completion.json",
        {
            "state": "COMPLETED",
            "summary": summary,
            "training": "NOT_STARTED",
            "new_positions": 100000,
            "old_positions_reused": 100000,
            "deterministic_finalization": True,
            "sealed_access": False,
            "final_config": "final-training-config.json",
        },
    )


def make_training_config(root, summary, hb):
    rows = [
        m
        for m in map(json.loads, (root / "materialized/ledger.jsonl").open())
        if m["decision"] == "TRAINING_ELIGIBLE"
    ]
    hb.write(phase="LOCK_FINAL_SPLIT", accepted_records=len(rows))
    x = feature_matrix(root / "materialized", rows)
    # Close existing exact components plus every eligible common-contract near
    # edge before assigning new roles. Bound dot-product blocks; never a dense NxN.
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        parent[max(a, b)] = min(a, b)

    components = {}
    for i, m in enumerate(rows):
        if m["component"] in components:
            union(i, components[m["component"]])
        else:
            components[m["component"]] = i
    # Identical content rows need one dot product per value, with all original
    # numeric/lineage members joined to its representative first.
    content, representatives, inverse = np.unique(
        x[:, 76:], axis=0, return_index=True, return_inverse=True
    )
    norms = np.einsum("ij,ij->i", content.astype(np.float64), content.astype(np.float64))
    for i, value in enumerate(inverse):
        if norms[value] >= 0.995 - 1e-7:
            union(i, int(representatives[value]))
    content = content.astype(np.float64)
    for a in range(0, len(content), 64):
        for b in range(a, len(content), 2048):
            scores = content[a : a + 64] @ content[b : b + 2048].T
            for i, j in zip(*np.where(scores >= 0.995 - 1e-7), strict=True):
                union(int(representatives[a + int(i)]), int(representatives[b + int(j)]))
        hb.write(
            phase="LOCK_ELIGIBLE_NEAR_GROUPS",
            near_anchor=min(a + 64, len(content)),
            eligible_records=len(x),
        )
    grouped = {}
    for i, m in enumerate(rows):
        grouped.setdefault(find(i), []).append(i)
    role = {}
    for g, slots in grouped.items():
        r = role_for_component(
            min(rows[i]["row"] for i in slots), any(rows[i]["row"] < 100000 for i in slots)
        )
        for i in slots:
            role[i] = (r, g)
    canonical = {}
    for i, m in enumerate(rows):
        if m["view_key"] in canonical:
            first = canonical[m["view_key"]]
            assert m["target"] == rows[first]["target"] and role[i] == role[first]
        else:
            canonical[m["view_key"]] = i
    manifest = []
    counts = {}
    folder = root / "final-data"
    folder.mkdir(exist_ok=True)
    p = module("student-data-pipeline.py")
    for r in ["TRAIN", "CALIBRATION", "EVALUATION"]:
        ids = [i for i in canonical.values() if role[i][0] == r]
        counts[r] = {
            "examples": len(ids),
            "classes": dict(Counter(str(rows[i]["target"]) for i in ids)),
            "groups": len({role[i][1] for i in ids}),
        }
        p.npz_atomic(
            folder / (r.lower() + ".npz"),
            x=x[ids],
            y=np.array([rows[i]["target"] for i in ids], np.int64),
            groups=np.array([role[i][1] for i in ids], np.int64),
            rows=np.array([rows[i]["row"] for i in ids], np.int64),
        )
        manifest.extend(
            {"row": rows[i]["row"], "role": r, "group": role[i][1], "target": rows[i]["target"]}
            for i in ids
        )
    atomic_json(folder / "split.json", manifest)
    cfg = load(CONFIG)["final_training"]
    n = counts["TRAIN"]["examples"]
    ready = n >= 500 and all(
        min(int(c["classes"].get("0", 0)), int(c["classes"].get("1", 0))) >= 50
        for c in counts.values()
    )
    cfg.update(
        {
            "dataset_version": root.name,
            "dataset_fingerprint": summary["fingerprint"],
            "split_fingerprint": digest(manifest),
            "training_examples": n,
            "split_counts": counts,
            "canonical_views": len(canonical),
            "planned_steps": 10 * ((n + 63) // 64),
            "data_files": {p.name: file_sha256(p) for p in folder.iterdir()},
            "training_readiness": "PASS" if ready else "BLOCKED_SPLIT_COVERAGE",
            "authorization": "NOT_STARTED_REQUIRES_NEXT_USER_REQUEST",
        }
    )
    cfg["fingerprint"] = digest(cfg)
    atomic_json(root / "final-training-config.json", cfg)


def smoke(root, hb):
    marker = root / "local-offline-smoke.json"
    if marker.exists():
        return
    hb.write(phase="SUPPORTED_OFFLINE_SMOKE")
    p = module("student-data-pipeline.py")
    t = p.teacher()
    pos, raw = next(raw_windows([(49964, 49965)]))
    request = p.validate_http({k: raw[k] for k in ["method", "url", "headers", "body"]})
    record = {
        "schema_version": "research-mvp-1",
        "record_id": "local-release-source-replay-1",
        "http_request": request,
    }
    result = t.predict(record)
    assert result["enforcement_actions"] == 0 and result["record_id"] == record["record_id"]
    try:
        t.predict({"schema_version": "research-mvp-1", "record_id": "local-release-missing-1"})
    except PipelineError:
        missing = "REJECTED_REQUIRED_FEATURES_MISSING_NO_SCORE"
    else:
        raise AssertionError("Missing request representation must not be scored")
    # Offline publisher score has its own checkpoint and semantic namespace.
    from idps_ai.features.request_preprocessing import encode_request
    from idps_ai.features.request_view import project_request
    from idps_ai.features.rich_content_v2 import rich_request_v2

    numeric = encode_request(
        t.numeric_spec, project_request(request["url"], request["method"])["numbers"]
    )
    text, _ = rich_request_v2(
        request["method"], request["url"], request["headers"], request["body"]
    )
    vector = np.concatenate([numeric, t.vectorizer.transform([text]).toarray()[0]]).astype(
        np.float32
    )[None]
    candidate = load_checkpoint(PILOT / "model")
    assert candidate.model.steps == 420
    publisher_score = float(candidate.model.predict(vector)[0][0])
    atomic_json(
        marker,
        {
            "state": "PASS",
            "scope": "OFFLINE_PUBLISHER_SOURCE_REPLAY_ONLY",
            "source_position": pos,
            "record_id": record["record_id"],
            "frozen_request_result": result,
            "publisher_anomaly": {
                "model": PILOT.name,
                "score": publisher_score,
                "task": "publisher_anomaly",
                "deployed": False,
            },
            "missing_features": missing,
            "live_HTTP_DB_UI_acceptance": "NOT_RUN",
            "rules_authority": "UNCHANGED_NO_ENFORCEMENT_PATH",
            "raw_HTTP_saved": False,
        },
    )


def worker(root, attempt):
    plan = verify(root)
    r = module("student-data-recovery.py")
    with RunLock(OLD.parent / "student-pipeline-global"), RunLock(root / "orchestrator.lock"):
        hb = r.WorkerHeartbeat(attempt)
        hb.write()
        thread = threading.Thread(target=hb.loop, daemon=True)
        thread.start()
        try:
            until = time.monotonic() + 20
            while not (attempt / "start.allowed").exists():
                assert time.monotonic() < until, "Guard readiness timeout"
                time.sleep(0.1)
            hb.write(phase="SOURCE_BINDINGS")
            for name, sha in plan["old_source_bindings"].items():
                assert file_sha256(REPO / name) == sha, "Source binding changed"
            smoke(root, hb)
            protection(root, plan, hb)
            legacy_review(root, hb)
            clone_old(root, plan, hb)
            ingest_new(root, plan, hb)
            merge_new(root, plan, hb)
            finalize(root, plan, hb)
            hb.write(state="COMPLETED", phase="FINAL_CONFIG_READY_NO_TRAINING")
            atomic_json(attempt / "worker-done.json", {"state": "COMPLETED"})
        except BaseException as exc:
            hb.write(state="FAILED", error_type=type(exc).__name__)
            raise
        finally:
            hb.done.set()
            thread.join()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--attempt", type=Path)
    ap.add_argument("--action", choices=["init", "supervise", "worker"], required=True)
    a = ap.parse_args()
    os.umask(0o077)
    root = a.root.resolve()
    attempt = a.attempt.resolve() if a.attempt else root / "attempts/data-v1"
    with threadpool_limits(limits=1):
        if a.action == "init":
            initialize(root)
        elif a.action == "worker":
            worker(root, attempt)
        else:
            recovery = module("student-data-recovery.py")
            # Reuse the proven supervisor unchanged; redirect only its worker
            # entrypoint and versioned binding validator for this new job.
            recovery.__file__ = __file__
            recovery.verify_binding = verify
            recovery.supervise(root, attempt)

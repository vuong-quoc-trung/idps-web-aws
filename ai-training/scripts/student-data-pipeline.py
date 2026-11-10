#!/usr/bin/env python3
"""One versioned100K student staging run, frozen teacher only, no optimization."""

import argparse
import hashlib
import hmac
import importlib.util
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

from idps_ai.common import (
    atomic_json,
    canonical_bytes,
    digest,
    file_sha256,
    fsync_dir,
)
from idps_ai.data.student_training import (
    StudentIndex,
    apply_proposal,
    protected_near,
    publisher_target,
    teacher_proposal,
)
from idps_ai.features.request_preprocessing import encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request
from idps_ai.mvp_inference import ResearchMVP, validate_http
from idps_ai.training.checkpoint import RunLock

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "ai-training/configs/research/student-training-v1.json"
WAF = ROOT / "ai-training/.artifacts/autonomous_research_20261104/waf_v2"
FIRST = ROOT / ".local-dev/first-party-source-20261110"
LEGACY = [
    (
        "ai-training/.artifacts/autonomous_http_intelligence_20261104/waf-content-v2",
        "numeric-only.npz",
        True,
    ),
    (
        "ai-training/.artifacts/autonomous_content_intelligence_20261104/waf-rich-v1",
        "rich-content.npz",
        True,
    ),
    (
        "ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2",
        "rich-content.npz",
        False,
    ),
]
BATCH = 256


def load(p):
    return json.loads(Path(p).read_text())


def mac(key, purpose, value):
    return hmac.new(key, canonical_bytes([purpose, value]), hashlib.sha256).hexdigest()


def view(x):
    return hashlib.sha256(np.asarray(x, np.float32).tobytes()).hexdigest()


def npz_atomic(path, **arrays):
    temp = path.with_suffix(".writing")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with temp.open("wb") as out:
        np.savez_compressed(out, **arrays)
        out.flush()
        os.fsync(out.fileno())
    if path.exists():
        assert file_sha256(temp) == file_sha256(path), (
            "Existing shard differs; preserve diagnostics"
        )
        temp.unlink()
    else:
        temp.replace(path)
        fsync_dir(path.parent)


@lru_cache(maxsize=1)
def header_adapter():
    # Reuse existing parser for publisher's space-separated headers. Do not
    # assume a serialization of all headers is a runtime three-header projection.
    spec = importlib.util.spec_from_file_location(
        "scaling_adapter", Path(__file__).with_name("scale-http-admission.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.allowed_headers


def selected_headers(value):
    return header_adapter()(value)


def teacher():
    t = ResearchMVP("request-v2", cpus=1)
    for p in t.v2_model.parameters.values():
        p.setflags(write=False)
    return t


def teacher_binding(t):
    return {
        "checkpoint_manifest": t.v2_manifest_sha,
        "threshold": t.v2_threshold,
        "model": "Frozen Request v2 step3072",
        "parameters": 50696,
        "encoder": "rich_content_v2+bounded-request-v1",
        "probability_calibrated": False,
    }


def source_hashes():
    paths = [
        POLICY,
        WAF / "train.parquet",
        WAF / "README.md",
        FIRST / "collector-intake-pending.jsonl",
        FIRST / "discovery-final.json",
    ]
    for folder, name, _ in LEGACY:
        paths.extend([ROOT / folder / name, ROOT / folder / "report.json"])
    release = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2"
    paths.extend([release / "materialization-report.json", release / "records.jsonl"])
    paths.extend(release / (role + ".npz") for role in ["train", "calibration", "development"])
    paths.append(
        ROOT / "ai-training/.artifacts/request_v3_body_eval_20261108/cohort-r2/features-private.npz"
    )
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in paths}


def code_paths():
    return [
        "ai-training/scripts/student-data-pipeline.py",
        "ai-training/scripts/scale-http-admission.py",
        "ai-training/scripts/student-data-supervisor.py",
        "ai-training/src/idps_ai/data/student_training.py",
        "ai-training/src/idps_ai/data/scaling_admission.py",
        "ai-training/src/idps_ai/mvp_inference.py",
        "ai-training/src/idps_ai/features/rich_content_v2.py",
        "ai-training/src/idps_ai/features/rich_content.py",
        "ai-training/src/idps_ai/features/request_preprocessing.py",
        "ai-training/src/idps_ai/features/request_view.py",
        "ai-training/scripts/scaled-active-supervisor.py",
        "ai-training/scripts/integration-guard.py",
    ]


def prepare(root, recovery_from=None):
    assert not root.exists(), "Choose fresh run directory; never overwrite"
    assert "license: mit" in (WAF / "README.md").read_text()
    assert file_sha256(WAF / "train.parquet") == load(POLICY)["sources"]["waf"]["train_sha256"]
    root.mkdir(parents=True, mode=0o700)
    (root / "identity.key").write_bytes(os.urandom(32))
    (root / "identity.key").chmod(0o600)
    t = teacher()
    tb = teacher_binding(t)
    plan = {
        "version": "student-100k-pilot-1",
        "run_id": root.name,
        "policy_sha256": file_sha256(POLICY),
        "policy": load(POLICY),
        "source_hashes": source_hashes(),
        "code_hashes": {p: file_sha256(ROOT / p) for p in code_paths()},
        "key_fingerprint": file_sha256(root / "identity.key"),
        "teacher": tb,
        "candidate_positions": 100000,
        "feature_contract": "student-http588-rich-v2-publisher-v1",
        "batch_size": BATCH,
        "resume_boundaries": [512, 4096, 100000],
        "model_training": "NOT_STARTED",
        "sealed_opened": False,
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    # One reconciliation pass only. Keep original73UNKNOWN receipts immutable.
    original = FIRST / "collector-intake-pending.jsonl"
    if recovery_from is None:
        rows = [json.loads(line) for line in original.open()]
        assert len(rows) == 73 and len({r["native_request_id"] for r in rows}) == 73
        recovery = []
        for r in rows:
            # Existing export has no request-bound semanticOracle/reviewer reference.
            supported = r.get("oracle_or_reviewer_reference") is not None
            assert not supported, (
                "New semantic evidence found: require reviewed profile revision, no silent relabel"
            )
            recovery.append(
                {
                    "native_request_id": r["native_request_id"],
                    "source_id": r["source_id"],
                    "intent": "UNKNOWN_INTENT",
                    "outcome": "UNKNOWN_OUTCOME",
                    "tier": "UNLABELED",
                    "original_engineering_phase": r["engineering_phase"],
                    "method": r["observed"]["method"],
                    "route_key_private": r["observed"]["route"],
                    "reason": "NO_RETAINED_REQUEST_BOUND_SEMANTIC_ORACLE",
                    "source_receipt_unchanged": True,
                    "body_event_available": r["feature_observation"]["body_event_available"],
                }
            )
        atomic_json(
            root / "first-party-recovery.json",
            {
                "reconciled_once": True,
                "records": recovery,
                "recovered_GOLD": 0,
                "original_sha256": file_sha256(original),
                "new_HTTP": 0,
            },
        )
    else:
        prior = load(recovery_from / "first-party-recovery.json")
        assert prior["original_sha256"] == file_sha256(original) and prior["reconciled_once"]
        shutil.copyfile(
            recovery_from / "first-party-recovery.json", root / "first-party-recovery.json"
        )
        atomic_json(
            root / "preparation-recovery.json",
            {
                "reason": "PRIOR_PREPARATION_THERMAL_STOPPED_BEFORE_ANY_WAF_CANDIDATES",
                "prior_run": recovery_from.name,
                "same_single_reconciliation_reused": True,
                "original_receipts_unchanged": True,
                "candidate_positions_processed_in_prior_run": 0,
            },
        )
    protected(root, t)
    atomic_json(
        root / "status.json",
        {
            "state": "PREPARED",
            "run_id": root.name,
            "plan_fingerprint": plan["fingerprint"],
            "last_heartbeat": time.time(),
            "training": "NOT_STARTED",
        },
    )
    print(
        json.dumps(
            {
                "state": "PREPARED",
                "run_id": root.name,
                "plan_fingerprint": plan["fingerprint"],
                "recovered_GOLD": 0,
            }
        )
    )


def protected(root, t):
    """Known exposed roles only; no sealed or publisher heldout files accessed."""
    index = StudentIndex(root / "protection-build", load(root / "plan.json"))
    full = []
    runtime = []
    for folder, name, all_protected in LEGACY:
        report = load(ROOT / folder / "report.json")
        assert file_sha256(ROOT / folder / name) == report["data_file_sha256"]
        with np.load(ROOT / folder / name, allow_pickle=False) as z:
            groups = z["group"]
            roles = z["role"]
            views = z["view"]
            mask = np.ones(len(roles), bool) if all_protected else roles != 0
            for g, v in zip(groups[mask], views[mask], strict=True):
                index.db.execute("INSERT OR IGNORE INTO protected_group VALUES(?)", (g.decode(),))
                index.db.execute("INSERT OR IGNORE INTO protected_view VALUES(?)", (v.decode(),))
            if not all_protected:
                for g in groups[roles == 0]:
                    index.db.execute(
                        "INSERT OR IGNORE INTO old_train_group VALUES(?)", (g.decode(),)
                    )
                full.append(z["content"][mask].copy())
    release = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2"
    records = [json.loads(line) for line in (release / "records.jsonl").open()]
    key = (root / "identity.key").read_bytes()
    for r in records:
        index.db.execute(
            "INSERT OR IGNORE INTO protected_route VALUES(?)",
            (mac(key, "route", [r["method"], r["endpoint_template"]]),),
        )
    for r in load(root / "first-party-recovery.json")["records"]:
        index.db.execute(
            "INSERT OR IGNORE INTO protected_route VALUES(?)",
            (mac(key, "route", [r["method"], r["route_key_private"]]),),
        )
    for role in ["train", "calibration", "development"]:
        with np.load(release / (role + ".npz"), allow_pickle=False) as z:
            runtime.append(z["frozen_runtime"][:, 76:].copy())
    with np.load(
        ROOT
        / "ai-training/.artifacts/request_v3_body_eval_20261108/cohort-r2/features-private.npz",
        allow_pickle=False,
    ) as z:
        runtime.append(z["frozen"][:, 76:].copy())
    index.db.commit()
    index.close()
    npz_atomic(
        root / "protected-vectors.npz",
        full=np.unique(np.concatenate(full), axis=0),
        runtime=np.unique(np.concatenate(runtime), axis=0),
    )
    atomic_json(
        root / "protection.json",
        {
            "known_v2_protected_content_rows": len(np.unique(np.concatenate(full), axis=0)),
            "legacy_exact_templates": "allv1samples excluded; their incompatibleencodernearcoverage remainsPARTIAL",
            "same_profile_near": "exhaustive blocked FP64 cosine, no cappedLSH",
            "cross_corpus_global_raw_lineage": "PARTIAL; no independent eval claim",
            "sealed_access": False,
            "vector_sha256": file_sha256(root / "protected-vectors.npz"),
        },
    )


def verify(root):
    plan = load(root / "plan.json")
    p = dict(plan)
    fp = p.pop("fingerprint")
    assert digest(p) == fp
    assert (
        file_sha256(POLICY) == plan["policy_sha256"]
        and file_sha256(root / "identity.key") == plan["key_fingerprint"]
    )
    for path, sha in plan["code_hashes"].items():
        assert file_sha256(ROOT / path) == sha, "Code binding changed"
    # Source bytes are checked at every process start, not just size/mtime.
    assert source_hashes() == plan["source_hashes"], "Source fingerprint changed"
    assert (
        file_sha256(root / "protected-vectors.npz")
        == load(root / "protection.json")["vector_sha256"]
    )
    return plan


def waf_rows(start):
    parquet = pq.ParquetFile(WAF / "train.parquet")
    assert parquet.num_row_groups == 2 and parquet.metadata.num_rows == 1924461
    base = 0
    offset = 0
    for group, limit in [(0, 49964), (1, 49963)]:
        low = max(0, start - offset)
        if low >= limit:
            offset += limit
            base += parquet.metadata.row_group(group).num_rows
            continue
        seen = 0
        for batch in parquet.iter_batches(batch_size=BATCH, row_groups=[group], use_threads=False):
            for r in batch.slice(0, min(batch.num_rows, limit - seen)).to_pylist():
                local = seen
                seen += 1
                if local < low:
                    continue
                yield base + local, r
            if seen >= limit:
                break
        assert seen >= limit
        offset += limit
        base += parquet.metadata.row_group(group).num_rows


def frames(root, start, stop):
    if start < 73:
        for i, r in enumerate(load(root / "first-party-recovery.json")["records"]):
            if i >= start and i < stop:
                yield "first-party", i, r
    if stop > 73:
        yield from (
            ("waf", i, r)
            for i, r in itertools.islice(
                waf_rows(max(0, start - 73)), max(0, stop - max(73, start))
            )
        )


def normalized(key, source, pos):
    return {
        "source": source,
        "source_row": pos,
        "request_key": None,
        "representation_key": None,
        "view_key": None,
        "groups": [],
        "workflow_key": None,
        "role": "EXTERNAL_STAGING_EXPOSED",
        "tier": "E",
        "label": None,
        "label_task": "publisher_anomaly",
        "identity_verified": False,
        "label_verified": False,
        "feature_valid": False,
        "body_state": "MISSING",
        "headers_available": False,
        "lineage_verified": False,
        "privacy_valid": True,
        "inherited_eligible": True,
        "reasons": [],
        "near_hash": None,
        "timestamp": None,
        "family": "unspecified",
        "method": "OTHER",
    }


def ingest(root, output, stop):
    plan = verify(root)
    key = (root / "identity.key").read_bytes()
    t = teacher()
    tb = teacher_binding(t)
    assert tb == plan["teacher"]
    with RunLock(output / "ingest.lock"):
        index = StudentIndex(output, plan)
        start = index.cursor
        assert 0 <= start <= stop <= 100000
        # Copy only immutable metadata indexes, never an old mutable admission DB.
        if not (output / "protection-copied.json").exists():
            import sqlite3

            old = sqlite3.connect(
                "file:" + str(root / "protection-build/index.sqlite") + "?mode=ro", uri=True
            )
            for table in [
                "protected_group",
                "protected_view",
                "old_train_group",
                "protected_route",
            ]:
                index.db.executemany(
                    f"INSERT OR IGNORE INTO {table} VALUES(?)",
                    old.execute(f"SELECT k FROM {table}"),
                )
            index.db.commit()
            old.close()
            atomic_json(output / "protection-copied.json", {"plan": plan["fingerprint"]})
        with np.load(root / "protected-vectors.npz", allow_pickle=False) as z:
            prot = z["full"].astype(np.float64)
            protruntime = z["runtime"].astype(np.float64)
        stream = frames(root, start, stop)
        while True:
            batch = list(itertools.islice(stream, BATCH))
            if not batch:
                break
            begin = index.cursor
            end = begin + len(batch)
            entries = []
            xrows = []
            locations = []
            companion = []
            for j, (source, pos, r) in enumerate(batch):
                n = normalized(key, source, pos)
                m = {
                    "tier": "UNLABELED",
                    "original_label": None,
                    "target": None,
                    "target_task": "publisher_anomaly",
                    "intent": "UNKNOWN_INTENT",
                    "outcome": "UNKNOWN_OUTCOME",
                    "parsed": True,
                    "body_observation": "NOT_COLLECTED",
                    "headers_observation": "NOT_COLLECTED",
                    "feature_ref": None,
                    "feature_contract": plan["feature_contract"],
                    "physical_identity": "UNVERIFIED",
                    "teacher_pretrain_template_overlap": False,
                    "pseudo": teacher_proposal(
                        None,
                        None,
                        teacher=tb,
                        expected_teacher=tb,
                        threshold=tb["threshold"],
                        allowed=False,
                    ),
                }
                if source == "first-party":
                    n["request_key"] = mac(key, "native-firstparty", r["native_request_id"])
                    n["identity_verified"] = True
                    n["groups"] = [mac(key, "capture", "body-live-20261108-acceptance-v1")]
                    n["reasons"] = ["REFERENCE_ONLY_EXPOSED", "NO_COMPLETE_588_SOURCE_INPUTS"]
                    m["physical_identity"] = "NATIVE_GATEWAY_RECEIPT"
                else:
                    label = publisher_target(r["label"])
                    m.update(label)
                    n["tier"] = "C" if label["target"] is not None else "E"
                    n["label"] = label["target"]
                    m["body_observation"] = (
                        "MISSING"
                        if r["body"] is None
                        else "EMPTY"
                        if r["body"] == ""
                        else "PUBLISHER_PRESENT_WIRE_COMPLETENESS_UNVERIFIED"
                    )
                    n["body_state"] = (
                        "MISSING"
                        if r["body"] is None
                        else "EMPTY"
                        if r["body"] == ""
                        else "PUBLISHER_PRESENT"
                    )
                    n["representation_key"] = mac(
                        key,
                        "complete-publisher-request",
                        [r[k] for k in ["method", "url", "protocol", "headers", "body"]],
                    )
                    n["headers_available"] = r["headers"] is not None
                    m["headers_observation"] = (
                        "MISSING"
                        if r["headers"] is None
                        else "EMPTY"
                        if r["headers"] == ""
                        else "PUBLISHER_PRESENT"
                    )
                    try:
                        req = validate_http({k: r[k] for k in ["method", "url", "headers", "body"]})
                        n["method"] = req["method"]
                        numeric = encode_request(
                            t.numeric_spec, project_request(req["url"], req["method"])["numbers"]
                        )
                        text, _ = rich_request_v2(
                            req["method"], req["url"], req["headers"], req["body"]
                        )
                        content = t.vectorizer.transform([text]).toarray().astype(np.float32)[0]
                        x = np.concatenate([numeric, content]).astype(np.float32)
                        assert x.shape == (588,) and np.isfinite(x).all()
                        runtime = {**req, "headers": selected_headers(req["headers"]), "body": None}
                        rt, _ = rich_request_v2(
                            runtime["method"], runtime["url"], runtime["headers"], None
                        )
                        rc = t.vectorizer.transform([rt]).toarray().astype(np.float32)[0]
                        safe, _ = symbolic_request(
                            req["method"], req["url"], req["headers"], req["body"]
                        )
                        g = hashlib.sha256(safe.encode()).hexdigest()
                        v = view(x)
                        route = mac(key, "route", [req["method"], urlsplit(req["url"]).path])
                        n["view_key"] = mac(key, "full588view", v)
                        n["groups"] = [mac(key, "safe-template", g)]
                        n["workflow_key"] = n["groups"][0]
                        n["feature_valid"] = True
                        known = (
                            index.db.execute(
                                "SELECT 1 FROM protected_group WHERE k=?", (g,)
                            ).fetchone()
                            or index.db.execute(
                                "SELECT 1 FROM protected_view WHERE k=?", (v,)
                            ).fetchone()
                            or index.db.execute(
                                "SELECT 1 FROM protected_route WHERE k=?", (route,)
                            ).fetchone()
                        )
                        m["teacher_pretrain_template_overlap"] = bool(
                            index.db.execute(
                                "SELECT 1 FROM old_train_group WHERE k=?", (g,)
                            ).fetchone()
                        )
                        if known:
                            n["reasons"].append("PROTECTED_EXISTING_TEMPLATE_VIEW_OR_ROUTE")
                        m["feature_ref"] = {
                            "shard": f"features/{begin:09}-{end:09}.npz",
                            "slot": len(xrows),
                        }
                        xrows.append(x)
                        locations.append(j)
                        companion.append(rc)
                    except (ValueError, TypeError, KeyError, OverflowError):
                        m["parsed"] = False
                        n["reasons"].append("INVALID_OR_UNSUPPORTED_HTTP_CONTRACT")
                entries.append([n, m])
            xs = np.asarray(xrows, np.float32).reshape(-1, 588)
            if len(xs):
                hit = protected_near(xs[:, 76:], prot) | protected_near(
                    np.asarray(companion, np.float32), protruntime
                )
                allowed = []
                for slot, j in enumerate(locations):
                    n, m = entries[j]
                    if hit[slot]:
                        n["reasons"].append("PROTECTED_NEAR_COMMON_CONTRACT")
                    if not n["reasons"]:
                        allowed.append((slot, j))
                if allowed:
                    scores = t.v2_model.predict(xs[[slot for slot, j in allowed]])[0]
                    for score, (slot, j) in zip(scores, allowed, strict=True):
                        m = entries[j][1]
                        entries[j][1] = apply_proposal(
                            m,
                            teacher_proposal(
                                float(score),
                                m["target"],
                                teacher=tb,
                                expected_teacher=tb,
                                threshold=tb["threshold"],
                            ),
                        )
                npz_atomic(output / f"features/{begin:09}-{end:09}.npz", x=xs)

            def pending():
                for offset, (n, m) in enumerate(entries):
                    if any(reason.startswith("PROTECTED") for reason in n["reasons"]):
                        index.db.execute(
                            "INSERT OR REPLACE INTO blocked VALUES(?,?)",
                            (begin + offset, "PROTECTED_EXISTING_ROLE"),
                        )
                    yield n, m

            index.append_student(pending())
            assert index.cursor == end
            if index.cursor % BATCH == 0:
                print(json.dumps({"phase": "INGEST", "rows_committed": index.cursor}), flush=True)
        assert index.cursor == stop and t.v2_model.steps == 3072
        index.close()
        print(json.dumps({"phase": "INGESTED", "rows": stop, "training_updates": 0}), flush=True)


def finish(root, output):
    plan = verify(root)
    index = StudentIndex(output, plan)
    assert index.cursor == 100000
    marker = output / "near-audit.json"
    if not marker.exists():
        # Fixed100K dense numeric memmap. Bounded rows/bytes, no all-pairs matrix.
        shape = (100000, 512)
        path = output / "content-audit.npy"
        mm = np.lib.format.open_memmap(path, mode="w+", dtype=np.float64, shape=shape)
        valid = []
        for i, sj in index.db.execute("SELECT i,j FROM student ORDER BY i"):
            m = json.loads(sj)
            ref = m["feature_ref"]
            if ref is not None:
                valid.append(i)
        # Load each shard once; unused positions are excluded, not fake features.
        for shard in sorted((output / "features").glob("*.npz")):
            with np.load(shard, allow_pickle=False) as z:
                x = z["x"]
            begin = int(shard.stem.split("-")[0])
            end = int(shard.stem.split("-")[1])
            for i, sj in index.db.execute(
                "SELECT i,j FROM student WHERE i>=? AND i<? ORDER BY i", (begin, end)
            ):
                m = json.loads(sj)
                ref = m["feature_ref"]
                if ref:
                    mm[i] = x[ref["slot"], 76:]
        mm.flush()
        pairs = 0
        # Exact metric over all valid rows, including exclusions; count only uppertriangle.
        for start in range(0, len(valid), 64):
            ids = np.asarray(valid[start : start + 64])
            q = mm[ids]
            for other in range(start, len(valid), 2048):
                js = np.asarray(valid[other : other + 2048])
                similar = q @ mm[js].T
                pairs += int(np.sum((similar >= 0.995 - 1e-7) & (ids[:, None] < js[None, :])))
            atomic_json(
                output / "near-progress.json",
                {
                    "state": "RUNNING",
                    "anchor_rows": min(start + 64, len(valid)),
                    "valid_rows": len(valid),
                },
            )
        del mm
        atomic_json(
            marker,
            {
                "metric": "existingcontentcosine>=0.995with1e-7tolerance",
                "frame_rows": len(valid),
                "intra_frame_pairs": pairs,
                "coverage": "EXHAUSTIVE_BLOCKED_COMMON_CONTRACT",
                "index_saturation": 0,
                "physical_duplicate_claim": False,
                "protected_common_v2": "checkedbeforeteacher",
                "legacy_incompatibleencoder_near": "PARTIAL; allknownlegacyexacttemplatesexcluded",
                "unknown_global_raw_lineage": "PARTIAL",
                "all_new_roles": "TRAIN_STAGING_EXPOSED; no newevaluation split",
            },
        )
    summary = index.finish(load(marker), plan["teacher"])
    index.close()
    # Every training row must point to real compatible storage; no absent-row padding.
    count = 0
    for line in (output / "training-index.jsonl").open():
        r = json.loads(line)
        assert r["features"] is not None and not r["optimization_consumed"]
        count += 1
    assert count == summary["counts"]["DEDUPLICATED_TRAINING_EXAMPLES"]
    return summary


class Heartbeat:
    def __init__(self, root):
        self.root = root
        self.current = {"state": "RUNNING", "phase": "STARTING"}
        self.lock = threading.Lock()
        self.stop = threading.Event()

    def write(self, **values):
        with self.lock:
            self.current.update(values)
            atomic_json(
                self.root / "status.json",
                {
                    **self.current,
                    "run_id": self.root.name,
                    "last_heartbeat": time.time(),
                    "model_training": "NOT_STARTED",
                },
            )

    def loop(self):
        while not self.stop.wait(1):
            self.write()


def worker(root):
    plan = verify(root)
    began = time.time()
    with RunLock(root.parent / "student-pipeline-global"), RunLock(root / "orchestrator.lock"):
        hb = Heartbeat(root)
        hb.write()
        thread = threading.Thread(target=hb.loop, daemon=True)
        thread.start()
        try:
            command = [sys.executable, str(Path(__file__)), "--root", str(root)]
            for name, stop in [
                ("materialized", 4096),
                ("materialized", 100000),
                ("rebuild", 100000),
            ]:
                output = root / name
                hb.write(phase="INGEST_" + name, planned_rows=stop)
                subprocess.run(
                    [*command, "--action", "ingest", "--output", str(output), "--stop", str(stop)],
                    check=True,
                )
                if stop == 100000:
                    hb.write(phase="FINALIZE_" + name)
                    subprocess.run(
                        [*command, "--action", "finish", "--output", str(output)], check=True
                    )
            a = load(root / "materialized/summary.json")
            b = load(root / "rebuild/summary.json")
            assert a == b, "Semantic rebuild differs"
            for name in ["ledger.jsonl", "training-index.jsonl"]:
                assert file_sha256(root / "materialized" / name) == file_sha256(
                    root / "rebuild" / name
                ), "Ledger rebuild differs"
            one = sorted((root / "materialized/features").glob("*.npz"))
            two = sorted((root / "rebuild/features").glob("*.npz"))
            assert len(one) == len(two)
            assert all(
                x.name == y.name and file_sha256(x) == file_sha256(y)
                for x, y in zip(one, two, strict=True)
            ), "Feature shard rebuild differs"
            assert source_hashes() == plan["source_hashes"]
            assert teacher_binding(teacher()) == plan["teacher"]
            report = {
                "state": "COMPLETED",
                "run_id": root.name,
                "plan_fingerprint": plan["fingerprint"],
                "summary": a,
                "actual_cross_process_resume": True,
                "deterministic_rebuild": True,
                "feature_shards_byte_identical": True,
                "model_training": "NOT_STARTED",
                "same_candidate_positions": 100000,
                "source_row_ingestions_including_rebuild": 200000,
                "eval_or_sealed_data_used_for_label_tuning": False,
                "new_groundtruth_from_teacher": 0,
                "engineering": {
                    "worker_seconds_including_rebuild": time.time() - began,
                    "candidate_positions_per_worker_second_including_rebuild": 100000
                    / (time.time() - began),
                    "artifact_bytes": sum(p.stat().st_size for p in root.rglob("*") if p.is_file()),
                    "resource_report": "resource/resource-report.json",
                    "resource_samples": "resource/samples.jsonl",
                    "privacy": "ALLOWLIST_METADATA_AND_FROZEN_PRIVACY_PROJECTION; local only",
                },
            }
            atomic_json(root / "completion.json", report)
            hb.stop.set()
            thread.join()
            hb.write(
                state="COMPLETED",
                phase="VERIFIED",
                counts=a["counts"],
                dataset_fingerprint=a["fingerprint"],
            )
        except BaseException as e:
            hb.stop.set()
            thread.join()
            hb.write(state="FAILED", phase="FAILED", error_type=type(e).__name__)
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--action", choices=["prepare", "ingest", "finish", "worker"], required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--recovery-from", type=Path)
    p.add_argument("--stop", type=int, default=100000)
    a = p.parse_args()
    os.umask(0o077)
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[:8]))
    with threadpool_limits(limits=1):
        if a.action == "prepare":
            prepare(a.root.resolve(), a.recovery_from)
        elif a.action == "ingest":
            a.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            ingest(a.root.resolve(), a.output.resolve(), a.stop)
        elif a.action == "finish":
            finish(a.root.resolve(), a.output.resolve())
        else:
            worker(a.root.resolve())

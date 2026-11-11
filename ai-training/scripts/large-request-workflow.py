#!/usr/bin/env python3
"""Finite, resume-safe large-request qualification. Failed data gates stop ML.

This workflow never treats a source census as a qualified training release. It
stops before optimization if request identity, unique features, label lineage or
evaluation protection is not evidenced. No shared Web/service files are edited.
"""

import argparse
import ast
import ctypes
import hashlib
import http.client
import importlib.util
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psutil
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import symbolic_request
from idps_ai.research.large_request import LargeRequest, parameter_count
from idps_ai.training.adaptive_thermal import hardware_snapshot
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.heartbeat import process_identity

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "ai-training/configs/research/large-request-1m-v1.json"
HYBRID = REPO / ".local-dev/hybrid-acceptance-20261110-r1"
PHASES = [
    "INVENTORY_AND_PRESERVATION",
    "DATA_ACQUISITION",
    "SYNTHETIC_REQUEST_GENERATION",
    "DATA_VALIDATION_AND_DEDUP",
    "VERIFY_1M_REQUESTS_AND_TRAIN_EXAMPLES",
    "FREEZE_DATASET_AND_SPLITS",
    "BUILD_AND_VERIFY_10M_MODEL",
    "TRAINING_PREFLIGHT",
    "REAL_10M_TRAINING",
    "FINAL_CHECKPOINT",
    "LOCKED_MODEL_EVALUATION",
    "LIVE_INFERENCE_COMPATIBILITY",
    "STAGED_LOCAL_AI_INTEGRATION",
    "HYBRID_POLICY_INTEGRATION",
    "LOCAL_END_TO_END_TESTING",
    "FINAL_ACCEPTANCE",
    "TERMINAL_STATUS",
]
PURPOSES = [
    "kiểm tra và bảo toàn assets",
    "kiểm kê chính xác corpus WAF TRAIN",
    "đo dữ liệu mới từ HTTP thực thi trong namespace riêng",
    "kiểm tra receipts, features, trùng và provenance",
    "xác định đủ hai mục tiêu 1 triệu hay còn thiếu bằng chứng",
]


def load(p):
    return json.loads(Path(p).read_text())


def configuration_path(root):
    pointer = root / "active-revision.json"
    return root / load(pointer)["config"] if pointer.exists() else root / "locked-config.json"


def authorization_path(root):
    pointer = root / "active-revision.json"
    return (
        root / load(pointer)["authorization"] if pointer.exists() else root / "authorization.json"
    )


def bound_paths():
    return [
        Path(__file__),
        REPO / "ai-training/scripts/integration-guard.py",
        REPO / "ai-training/scripts/rolling-resource-policy.py",
        *[
            REPO / "ai-training/src/idps_ai" / n
            for n in [
                "research/large_request.py",
                "research/large_pipeline.py",
                "training/data_quota_ramp.py",
                "training/models.py",
                "training/tabular.py",
                "training/checkpoint.py",
                "features/request_preprocessing.py",
                "features/request_view.py",
                "features/rich_content.py",
                "features/rich_content_v2.py",
                "features/safe_content.py",
            ]
        ],
    ]


def reconfigure(root):
    previous = load(root / "supervisor.json")
    assert process_identity(previous["pid"]) != previous.get("start_ticks"), (
        "Healthy job must not be interrupted"
    )
    revision = root / "revisions/target-1m-20261110-a1"
    proof = load(revision / "checkpoint-verification.json")
    assert proof["state"] == "VERIFIED"
    snapshot = revision / "qualification-snapshot.sqlite"
    assert file_sha256(snapshot) == proof["snapshot_sha256"]
    db = open_index(root)
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    current = dict(db.execute("SELECT k,n FROM progress"))
    assert all(current.get(k) == v for k, v in proof["source_cursor"].items())
    assert db.execute("SELECT count(*) FROM views").fetchone()[0] == proof["receipts"]
    chain = hashlib.sha256()
    for view, blob, receipt, rhash in db.execute(
        "SELECT h,feature,receipt,request_hash FROM views ORDER BY h"
    ):
        assert hashlib.sha256(blob).hexdigest() == view
        chain.update((view + rhash + receipt).encode())
    assert chain.hexdigest() == proof["receipt_content_fingerprint"]
    with sqlite3.connect("file:" + str(snapshot) + "?mode=ro", uri=True) as saved:
        for table, order in [("views", "h"), ("template_roles", "h")]:
            for actual, previous_row in zip(
                db.execute(f"SELECT * FROM {table} ORDER BY {order}"),
                saved.execute(f"SELECT * FROM {table} ORDER BY {order}"),
                strict=True,
            ):
                assert actual == previous_row, "Checkpoint label/role/receipt metadata changed"

    # Check exactly the generator/feature function ASTs; unrelated orchestration
    # changes cannot silently change resumed input positions.
    def functions(path):
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ["scenario", "features"]
        }

    assert functions(revision / "previous-workflow.py") == functions(Path(__file__))
    old = load(root / "locked-config.json")
    new = load(CONFIG)
    for name, sha in load(root / "authorization.json")["code_hashes"].items():
        if name != str(Path(__file__).relative_to(REPO)):
            assert file_sha256(REPO / name) == sha, "Original model/feature dependency changed"
    assert (
        old["synthetic"]["version"] == new["synthetic"]["version"]
        and old["synthetic"]["seed"] == new["synthetic"]["seed"]
    )
    assert old["model"] == new["model"] and new["model"]["expected_parameters"] == 10065928
    oldstatus = load(revision / "previous-worker-status.json")
    elapsed = max(0, oldstatus["heartbeat"] - oldstatus["phase_started"])
    advance(db, "capture_elapsed_ms", int(elapsed * 1000))
    db.commit()
    db.close()
    atomic_json(revision / "config.json", new)
    auth = {
        "config_sha256": file_sha256(revision / "config.json"),
        "source_config_sha256": file_sha256(CONFIG),
        "previous_authorization_sha256": file_sha256(root / "authorization.json"),
        "checkpoint_snapshot_sha256": proof["snapshot_sha256"],
        "approved_target": 1000000,
        "model_unchanged": True,
        "generator_AST_unchanged": True,
        "code_hashes": {str(p.relative_to(REPO)): file_sha256(p) for p in bound_paths()},
        "previous_attempts_per_second": oldstatus["throughput_per_second"],
        "previous_receipts_per_second_phase_average": proof["receipts"] / elapsed,
        "previous_rate_basis_seconds": elapsed,
        "authorized_recovery": True,
        "created": time.time(),
    }
    atomic_json(revision / "authorization.json", auth)
    atomic_json(
        root / "active-revision.json",
        {
            "config": str((revision / "config.json").relative_to(root)),
            "authorization": str((revision / "authorization.json").relative_to(root)),
            "target_distinct_requests": 1000000,
            "target_TRAIN_examples": 1000000,
        },
    )
    return auth


def guard_dir(root):
    p = root / "active-guard.json"
    return root / load(p)["path"] if p.exists() else root / "guard"


def module(p):
    s = importlib.util.spec_from_file_location("large_guard", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def open_index(root):
    db = sqlite3.connect(root / "qualification.sqlite", timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS progress(k TEXT PRIMARY KEY,n INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS public_requests(h TEXT PRIMARY KEY,labels INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS views(h TEXT PRIMARY KEY,role TEXT NOT NULL,template TEXT NOT NULL,
        feature BLOB NOT NULL,request_hash TEXT NOT NULL UNIQUE,receipt TEXT NOT NULL,
        tier TEXT NOT NULL,target INTEGER NOT NULL,conflict INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS template_roles(h TEXT PRIMARY KEY,role TEXT NOT NULL,conflict INTEGER NOT NULL DEFAULT 0);
      CREATE INDEX IF NOT EXISTS views_role_conflict ON views(role,conflict);
    """)
    return db


def cursor(db, key):
    row = db.execute("SELECT n FROM progress WHERE k=?", (key,)).fetchone()
    return row[0] if row else 0


def advance(db, key, n):
    db.execute(
        "INSERT INTO progress VALUES(?,?) ON CONFLICT(k) DO UPDATE SET n=excluded.n", (key, n)
    )


def parent_death_signal():
    # The existing guard handles SIGTERM and kills only its guarded cgroup.
    # If the outside supervisor dies, do not leave a detached orphan guard.
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        os._exit(125)
    if os.getppid() != parent:
        os._exit(125)


def verified_existing_training():
    run = (
        REPO
        / "ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1"
    )
    report = load(run / "validation.json")
    assert report["state"] == "PASS" and report["privacy"].startswith("PASS")
    assert report["training_examples"] == report["split_counts"]["TRAIN"]["examples"]
    return report["training_examples"]


def reuse_census(root, cfg, status):
    status.write(
        phase=PHASES[1], completed=0, total=1, operation="REUSE_SOURCE_HASH_BOUND_COMPLETE_CENSUS"
    )
    p = REPO / cfg["source"]["verified_census_path"]
    assert file_sha256(p) == cfg["source"]["verified_census_sha256"]
    old = load(p)
    assert old["input_sha256"]["train"] == cfg["source"]["sha256"]
    assert old["counts"]["publisher_rows"] == cfg["source"]["rows"]
    result = {
        "source_positions": old["counts"]["publisher_rows"],
        "distinct_publisher_representations": old["exact_request_representations"],
        "conflicting_publisher_representations": old["exact_request_label_conflicts"],
        "physical_identity": "UNVERIFIED",
        "eligible_TRAIN_examples": 0,
        "feature_materialization": "NOT_YET_QUALIFIED",
        "task": "publisher_anomaly",
        "tier": "SILVER",
        "reused_verified_census_sha256": file_sha256(p),
        "fresh_source_sha256_checked": True,
        "new_ingestion_positions": 0,
        "scope": "capacity only; existing cohorts/roles unmodified",
    }
    atomic_json(root / "public-census.json", result)
    status.write(completed=1, public_corpus_observations=result["source_positions"])
    return result


class Status:
    def __init__(self, root):
        self.root, self.done, self.lock = root, threading.Event(), threading.RLock()
        self.v = {
            "run_id": root.name,
            "state": "RUNNING",
            "pid": os.getpid(),
            "start_ticks": process_identity(os.getpid()),
            "phase": PHASES[0],
            "training": "NOT_STARTED",
            "optimizer_updates": 0,
            "training_loss": None,
            "actual_trainable_parameters": None,
            "planned_parameters": parameter_count(),
            "unique_TRAIN_examples": 0,
            "verified_distinct_HTTP_requests": 0,
            "checkpoint": str(root / "qualification.sqlite"),
            "sealed_access": False,
        }
        if (root / "architecture-proof.json").exists():
            self.v["actual_trainable_parameters"] = load(root / "architecture-proof.json")[
                "trainable_parameters"
            ]
        if (root / "existing-training.json").exists():
            self.v["unique_TRAIN_examples"] = load(root / "existing-training.json")[
                "TRAIN_examples"
            ]
        self.v["data_target"] = load(configuration_path(root))["targets"]["distinct_requests"]
        self.v["TRAIN_target"] = load(configuration_path(root))["targets"]["unique_TRAIN_examples"]
        self.v["receipt_errors"] = 0
        if (root / "qualification.sqlite").exists():
            with sqlite3.connect(
                "file:" + str(root / "qualification.sqlite") + "?mode=ro", uri=True
            ) as db:
                self.v["verified_distinct_HTTP_requests"] = db.execute(
                    "SELECT count(*) FROM views"
                ).fetchone()[0]
                self.v["campaign_position"] = cursor(db, "synthetic_position")
        self.samples = []
        self.last_eta_quota = None
        self.last_announcement = 0
        self.phase = None
        self.write(phase=PHASES[0], completed=0, total=1)
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def write(self, **values):
        with self.lock:
            changed = "phase" in values and values["phase"] != self.phase
            if changed:
                self.phase = values["phase"]
                self.samples = []
                self.v["phase_started"] = time.time()
                index = PHASES.index(self.phase)
                self.v["job_purpose"] = (
                    PURPOSES[index] if index < len(PURPOSES) else "ghi trạng thái kết thúc"
                )
                purposes = {
                    "TRAINING_PREFLIGHT": "kiểm tra batch dữ liệu thật, checkpoint và exact resume",
                    "REAL_10M_TRAINING": "huấn luyện model 10.065.928 tham số trên TRAIN đã khóa",
                    "LOCKED_MODEL_EVALUATION": "đánh giá model với threshold chỉ từ CAL",
                    "LIVE_INFERENCE_COMPATIBILITY": "kiểm tra adapter và hợp đồng inference local",
                }
                self.v["job_purpose"] = purposes.get(self.phase, self.v["job_purpose"])
                self.v["next_automatic_action"] = (
                    (PHASES[index + 1] + " nếu gate PASS; dừng nếu FAIL")
                    if index < len(PHASES) - 1
                    else "STOP"
                )
            self.v.update(values)
            if self.v.get("phase") == "SYNTHETIC_REQUEST_GENERATION":
                self.v["campaign_position"] = self.v.get("completed", 0)
            now = time.time()
            resource = guard_dir(self.root) / "resource-status.json"
            observed = load(resource) if resource.exists() else {}
            quota = observed.get("quota_percent_one_cpu")
            if quota != self.last_eta_quota:
                self.samples = []
                self.last_eta_quota = quota
            self.v["ETA_quota_percent_one_core"] = quota
            self.samples.append((now, self.v.get("completed", 0)))
            self.samples = [r for r in self.samples if now - r[0] <= 300]
            dt = now - self.samples[0][0]
            dn = self.v.get("completed", 0) - self.samples[0][1]
            rate = (
                dn / dt
                if dt >= 60 and dn > 0 and self.phase in [*PHASES[2:4], "REAL_10M_TRAINING"]
                else None
            )
            estimates = None
            if rate:
                middle = min(self.samples, key=lambda s: abs(s[0] - (now - dt / 2)))
                windows = [
                    (middle[1] - self.samples[0][1], middle[0] - self.samples[0][0]),
                    (self.v.get("completed", 0) - middle[1], now - middle[0]),
                ]
                rates = [n / s for n, s in windows if s > 0 and n > 0]
                if len(rates) == 2:
                    remaining = max(0, self.v.get("total", 0) - self.v.get("completed", 0))
                    estimates = [remaining / max(rates), remaining / min(rates)]
            self.v.update(
                heartbeat=now,
                throughput_per_second=rate,
                ETA_seconds_interval=estimates,
                ETA_window_seconds=dt if rate else None,
                ETA_scope="CURRENT_PHASE_ONLY; wall time includes throttling/cooldown",
                ETA_basis="observed throughput in two halves of rolling window; not a confidence interval or end-to-end promise",
                worker_RSS_bytes=psutil.Process().memory_info().rss,
            )
            atomic_json(self.root / "worker-status.json", self.v)
            if changed or now - self.last_announcement >= 60:
                self.announce()

    def announce(self):
        number = PHASES.index(self.v["phase"])
        purpose = self.v.get(
            "job_purpose", PURPOSES[number] if number < len(PURPOSES) else "ghi trạng thái kết thúc"
        )
        guard_path = guard_dir(self.root) / "resource-status.json"
        guard = load(guard_path) if guard_path.exists() else {}
        eta = self.v.get("ETA_seconds_interval")
        eta_text = (
            f"{eta[0] / 60:.1f}–{eta[1] / 60:.1f} phút; cửa sổ {self.v.get('ETA_window_seconds', 0):.0f}s, chỉ giai đoạn này"
            if eta
            else "CHƯA ĐỦ DỮ LIỆU ĐỂ ƯỚC TÍNH"
        )
        value = (
            f"Tôi đang chạy job {self.v['phase']} nhằm mục đích {purpose}.\n"
            f"Giai đoạn hiện tại: {self.v['phase']}.\n"
            f"Tiến độ: {self.v.get('completed', 0)}/{self.v.get('total', 0)}.\n"
            f"Ước tính còn khoảng: {eta_text}.\n"
            f"CPU host: {guard.get('host_cpu_utilization_percent')}%; quota {guard.get('quota_percent_one_cpu')}% một core.\n"
            f"RAM khả dụng: {guard.get('mem_available_bytes')}; Nhiệt độ: {guard.get('thermal', {}).get('current_c')}°C.\n"
            f"RAM worker: {self.v.get('worker_RSS_bytes')}.\n"
            f"Sau khi hoàn thành: {self.v.get('next_automatic_action')}.\n"
            f"Trạng thái: {self.v['state']}.\n"
            f"Run ID: {self.root.name}.\nStatus: {self.root / 'worker-status.json'}.\n"
        )
        ramp_path = guard_dir(self.root) / "cpu-ramp.json"
        if ramp_path.exists():
            ramp = load(ramp_path)
            window = ramp.get("last_window") or (ramp.get("history") or [{}])[-1]
            value += f"Tốc độ candidates/receipts/eligible mỗi giây: {window.get('candidates_per_second')}/{window.get('receipts_per_second')}/{window.get('eligible_per_second')}.\n"
            value += f"Nhiệt trung bình/đỉnh cửa sổ: {window.get('average_temperature')}/{window.get('maximum_temperature')}°C.\n"
        if self.phase == "REAL_10M_TRAINING":
            value = "TÔI ĐANG TRAIN MODEL AI-IDPS 10 TRIỆU THAM SỐ.\n" + value
            value += f"Model: request-swiglu-10m-multitask-v1; tham số: {self.v.get('actual_trainable_parameters')}.\nTraining examples: {self.v.get('unique_TRAIN_examples')}.\nEpoch: {self.v.get('epoch')}/{self.v.get('epochs')}.\nOptimizer updates: {self.v.get('optimizer_updates')}/{self.v.get('total')}.\nLoss: {self.v.get('training_loss')}.\nCheckpoint: {self.v.get('checkpoint')}.\n"
        with (self.root / "progress-vi.log").open("a") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n" + value + "\n")
        self.last_announcement = time.time()

    def loop(self):
        while not self.done.wait(0.5):
            self.write()

    def close(self):
        self.done.set()
        self.thread.join(timeout=3)


def check_disk(root, cfg):
    if shutil.disk_usage(root).free < cfg["resources"]["disk_reserve_GiB"] * 2**30:
        raise RuntimeError("DISK_RESERVE_EXHAUSTED")
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if size > cfg["resources"]["disk_budget_GiB"] * 2**30:
        raise RuntimeError("LOCKED_DISK_BUDGET_EXHAUSTED")


def architecture_probe(root, status):
    """Contract verification only; random vectors, not the authorized ML run."""
    status.write(completed=1, total=4, operation="10M_SHAPE_AND_GRADIENT_CONTRACT_PROBE")
    model = LargeRequest()
    n = sum(v.size for v in model.parameters.values())
    assert 9500000 <= n <= 10500000 and n == parameter_count()
    x = np.random.default_rng(17).random((8, 588), dtype=np.float32)
    y = np.array([[0, 1], [1, 0], [-1, 1], [1, -1], [0, 0], [1, 1], [-1, -1], [0, 1]], np.int64)
    loss, gradients = model.loss_and_gradients(x, y)
    assert np.isfinite(loss)
    assert all(np.isfinite(g).all() and np.any(g != 0) for g in gradients.values())
    assert np.all(np.any(gradients["Win"] != 0, axis=1)), "Dormant input rows"
    status.write(completed=2, actual_trainable_parameters=n, probe_loss=loss)
    model.train_batch(x, y, 0.0003)
    state = {
        "probe_only": True,
        "config_sha256": file_sha256(CONFIG),
        "RNG": np.random.default_rng(17).bit_generator.state,
        "scheduler": {"kind": "constant", "step": model.steps},
    }
    checkpoint = save_checkpoint(
        root / "architecture-probe", model, state, np.arange(8, dtype=np.int64)
    )
    loaded = load_checkpoint(root / "architecture-probe")
    recovered = LargeRequest.from_arrays(loaded.state["model"], loaded.model.arrays())
    assert recovered.steps == model.steps == 1
    assert all(np.array_equal(v, recovered.arrays()[k]) for k, v in model.arrays().items())
    model.train_batch(x, y, 0.0003)
    recovered.train_batch(x, y, 0.0003)
    assert all(np.array_equal(v, recovered.arrays()[k]) for k, v in model.arrays().items())
    assert all(np.isfinite(v).all() for v in model.score_heads(x).values())
    atomic_json(
        root / "architecture-proof.json",
        {
            "state": "PASS",
            "parameters": n,
            "trainable_parameters": n,
            "active_gradient_tensors": len(gradients),
            "all_input_rows_active": True,
            "exact_next_update_resume": True,
            "probe_optimizer_updates": 2,
            "actual_data_training_updates": 0,
            "checkpoint": str(checkpoint),
            "scope": "random tensor execution test, not trained model quality",
        },
    )
    status.write(
        completed=3, actual_trainable_parameters=n, operation="ARCHITECTURE_PROBE_VERIFIED"
    )


def census(root, cfg, status):
    status.write(phase=PHASES[1], completed=0, total=cfg["source"]["rows"])
    db = open_index(root)
    position = cursor(db, "public_position")
    seen = 0
    for batch in pq.ParquetFile(REPO / cfg["source"]["path"]).iter_batches(
        batch_size=1024, use_threads=False
    ):
        end = seen + batch.num_rows
        if end <= position:
            seen = end
            continue
        for row in batch.slice(max(0, position - seen)).to_pylist():
            # Hash every publisher field relevant to HTTP identity, not just URL.
            if row["label"] not in ["normal", "anomalous"]:
                raise RuntimeError("Unexpected publisher label; no implicit benign")
            h = digest([row.get(k) for k in ["method", "url", "protocol", "headers", "body"]])
            label = 1 if row["label"] == "normal" else 2
            db.execute(
                "INSERT INTO public_requests VALUES(?,?) ON CONFLICT(h) DO UPDATE SET labels=labels|excluded.labels",
                (h, label),
            )
        seen = end
        advance(db, "public_position", seen)
        db.commit()
        status.write(completed=seen)
        if seen % (1024 * 64) == 0:
            check_disk(root, cfg)
    assert seen == cfg["source"]["rows"]
    unique, conflict = db.execute("SELECT count(*),sum(labels=3) FROM public_requests").fetchone()
    db.close()
    report = {
        "source_positions": seen,
        "distinct_publisher_representations": unique,
        "conflicting_publisher_representations": conflict,
        "physical_identity": "UNVERIFIED",
        "eligible_TRAIN_examples": 0,
        "feature_materialization": "NOT_YET_QUALIFIED",
        "purpose": "capacity census, not admission or physical requests",
        "task": "publisher_anomaly",
        "tier": "SILVER",
    }
    atomic_json(root / "public-census.json", report)
    return report


def scenario(i):
    """Interleave a finite semantic grammar; no random IDs/padding/timestamps.

    Fields, operators, grouping and thresholds change the evaluated catalogue
    query. Literal changes that the privacy encoder erases earn no extra views.
    """
    n = (i * 104729 + 17) % 1048576
    threshold, n = n % 32, n // 32
    pattern, n = n % 32, n // 32
    depth, n = n % 8 + 1, n // 8
    verb, n = n % 4, n // 4
    workflow = n % 32
    method = ["GET", "POST", "PUT", "PATCH"][verb]
    fields = ["price", "quantity", "rating", "stock"]
    operators = [">", "<", "=", "!="]
    terms = [
        f"{fields[(pattern + j) % 4]}{operators[(pattern // 4 + j) % 4]}{(threshold + 1) * (j + 1)}"
        for j in range(depth)
    ]
    expression = (" AND " if pattern % 2 else " OR ").join(terms)
    attack = pattern >= 24
    if attack:
        expression += ["' OR 1=1--", "<svg onload=alert(1)>", ";id", "../../etc/passwd"][
            pattern % 4
        ]
    path = (
        "/lab/catalog/"
        + str(workflow)
        + "?"
        + urllib.parse.urlencode({"filter": expression, "limit": (threshold + 1) * 2})
    )
    body = (
        None
        if method == "GET"
        else json.dumps({"filter": expression, "limit": (threshold + 1) * 2}, separators=(",", ":"))
    )
    headers = {
        "User-Agent": "AI-IDPS-authorized-catalog-lab",
        "Accept": "application/json",
        "Content-Type": "" if body is None else "application/json",
    }
    if body is not None and pattern % 2:
        body = urllib.parse.urlencode({"filter": expression, "limit": (threshold + 1) * 2})
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    role = "CALIBRATION" if workflow % 10 == 0 else "EVALUATION" if workflow % 10 == 1 else "TRAIN"
    return (
        {"method": method, "url": path, "headers": headers, "body": body},
        role,
        int(attack),
        workflow,
    )


class Lab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        # This server validates/evaluates our bounded DSL. It never runs shell,
        # SQL, JS or a filesystem operation chosen by request data. The fixed
        # receipt journal below is the only request-handler filesystem write.
        import re

        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        expression = q.get("filter", [""])[0]
        valid = bool(
            re.fullmatch(
                r"(?:price|quantity|rating|stock)[!<>=]{1,2}[0-9]+(?:(?: AND | OR )(?:price|quantity|rating|stock)[!<>=]{1,2}[0-9]+)*",
                expression,
            )
        )
        if body:
            try:
                supplied = (
                    json.loads(body)
                    if self.headers.get("Content-Type") == "application/json"
                    else {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
                )
                valid = (
                    valid
                    and supplied["filter"] == expression
                    and int(supplied["limit"]) == int(q["limit"][0])
                )
            except (ValueError, KeyError, UnicodeDecodeError, TypeError):
                valid = False
        selected = 0
        if valid:
            terms = re.findall(r"(price|quantity|rating|stock)(!=|=|<|>)([0-9]+)", expression)
            for row in range(32):
                values = {
                    "price": row * 3,
                    "quantity": row + 1,
                    "rating": row % 5,
                    "stock": row * 2,
                }
                checks = [
                    {
                        "=": values[f] == int(v),
                        "!=": values[f] != int(v),
                        ">": values[f] > int(v),
                        "<": values[f] < int(v),
                    }[op]
                    for f, op, v in terms
                ]
                selected += int(all(checks) if " AND " in expression else any(checks))
        # Identity is generated by the server, and never used for input uniqueness.
        value = {
            "server_request_id": uuid.uuid4().hex,
            "method": self.command,
            "path_sha256": hashlib.sha256(self.path.encode()).hexdigest(),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "oracle": "VALID_FILTER_EVALUATED" if valid else "FILTER_REJECTED",
            "rows_selected": selected,
            "exploit_success": "NOT_TESTED",
            "request_hash": digest(
                {
                    "method": self.command,
                    "url": self.path,
                    "headers": {
                        k: self.headers.get(k, "") for k in ["User-Agent", "Accept", "Content-Type"]
                    },
                    "body": None if self.command == "GET" else body.decode(),
                }
            ),
            "HTTP_status": 200 if valid else 422,
        }
        # Persist the real receipt before returning it. A killed client can
        # recover it without executing the same logical request again.
        with self.server.receipt_journal.open("ab") as journal:
            journal.write(canonical_bytes(value) + b"\n")
            journal.flush()
            os.fsync(journal.fileno())
        data = canonical_bytes(value)
        self.send_response(200 if valid else 422)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = handle_request


def features(request, vectorizer):
    text = "\r\n".join(k + ": " + v for k, v in request["headers"].items() if v)
    symbolic, _ = rich_request_v2(request["method"], request["url"], text, None)
    numbers = project_request(request["url"], request["method"])["numbers"]
    x = np.r_[
        encode_request(bounded_spec(), numbers), vectorizer.transform([symbolic]).toarray()[0]
    ].astype(np.float32)
    assert x.shape == (588,) and np.isfinite(x).all()
    # Canonical symbolic template deliberately forgets private literal values.
    safe, _ = symbolic_request(request["method"], request["url"], text, None)
    return x, digest(safe)


def capture(root, cfg):
    assert Path("/proc/self/uid_map").read_text().split()[1] != "0"
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True, capture_output=True)
    status = Status(root)
    limit = cfg["synthetic"]["maximum_candidates"]
    db = open_index(root)
    committed_receipts = db.execute("SELECT count(*) FROM views").fetchone()[0]
    staging_train = db.execute(
        "SELECT count(*) FROM views WHERE role='TRAIN' AND conflict=0"
    ).fetchone()[0]
    status.write(
        phase=PHASES[2],
        completed=cursor(db, "synthetic_position"),
        total=limit,
        verified_distinct_HTTP_requests=committed_receipts,
        receipt_errors=0,
    )
    server = HTTPServer(("127.0.0.1", 0), Lab)
    server.receipt_journal = root / "server-receipts.jsonl"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    vectorizer = HashingVectorizer(
        n_features=512,
        analyzer="char",
        ngram_range=(3, 5),
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    start = time.monotonic()
    prior_elapsed = cursor(db, "capture_elapsed_ms") / 1000
    feature_cpu = http_wall = 0.0
    duplicates = 0
    reason = "GRAMMAR_EXHAUSTED"
    recovered = {}
    if server.receipt_journal.exists():
        with server.receipt_journal.open("rb") as journal:
            for line in journal:
                if not line.endswith(b"\n"):
                    break
                receipt = json.loads(line)
                if not db.execute(
                    "SELECT 1 FROM views WHERE request_hash=?", (receipt["request_hash"],)
                ).fetchone():
                    recovered[receipt["request_hash"]] = receipt
    try:
        for i in range(cursor(db, "synthetic_position"), limit):
            request, role, intent, workflow = scenario(i)
            feature_start = time.process_time()
            x, template = features(request, vectorizer)
            feature_cpu += time.process_time() - feature_start
            view = hashlib.sha256(x.tobytes()).hexdigest()
            old = db.execute("SELECT role,target,conflict FROM views WHERE h=?", (view,)).fetchone()
            if old:
                duplicates += 1
                if old[0] != role or old[1] != intent:
                    if old[0] == "TRAIN" and old[2] == 0:
                        staging_train -= 1
                    db.execute("UPDATE views SET conflict=1 WHERE h=?", (view,))
            else:
                http_start = time.monotonic()
                rawbody = (request["body"] or "").encode()
                receipt = recovered.pop(digest(request), None)
                if receipt is None:
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=10
                    )
                    connection.request(
                        request["method"], request["url"], body=rawbody, headers=request["headers"]
                    )
                    response = connection.getresponse()
                    receipt = json.loads(response.read())
                    connection.close()
                    assert receipt["HTTP_status"] == response.status
                else:
                    receipt["recovered_from_durable_server_journal"] = True
                http_wall += time.monotonic() - http_start
                assert receipt["request_hash"] == digest(request)
                assert receipt["method"] == request["method"]
                assert receipt["path_sha256"] == hashlib.sha256(request["url"].encode()).hexdigest()
                assert receipt["body_sha256"] == hashlib.sha256(rawbody).hexdigest()
                assert receipt["HTTP_status"] == (422 if intent else 200)
                receipt.update(
                    HTTP_status=receipt["HTTP_status"],
                    workflow_group=workflow,
                    intent_basis="SYNTHETIC_DESIGN_NOT_EXPLOIT_OUTCOME",
                )
                reqhash = digest(request)
                db.execute(
                    "INSERT INTO views(h,role,template,feature,request_hash,receipt,tier,target) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        view,
                        role,
                        template,
                        x.tobytes(),
                        reqhash,
                        json.dumps(receipt),
                        "BRONZE",
                        intent,
                    ),
                )
                duplicates = 0
                committed_receipts += 1
                if role == "TRAIN":
                    staging_train += 1
            db.execute(
                "INSERT INTO template_roles VALUES(?,?,0) ON CONFLICT(h) DO UPDATE SET conflict=CASE WHEN role<>excluded.role THEN 1 ELSE conflict END",
                (template, role),
            )
            advance(db, "synthetic_position", i + 1)
            if not old:
                advance(
                    db, "capture_elapsed_ms", int((prior_elapsed + time.monotonic() - start) * 1000)
                )
                db.commit()  # receipt + exact next candidate position in one durable transaction
            if (i + 1) % 128 == 0:
                advance(
                    db, "capture_elapsed_ms", int((prior_elapsed + time.monotonic() - start) * 1000)
                )
                db.commit()
                n = committed_receipts
                status.write(
                    completed=i + 1,
                    verified_distinct_HTTP_requests=n,
                    new_staging_TRAIN_views=staging_train,
                    feature_cpu_seconds=feature_cpu,
                    http_wall_seconds=http_wall,
                    receipt_errors=0,
                )
                check_disk(root, cfg)
                if n >= cfg["synthetic"]["maximum_executed"]:
                    reason = "EXECUTION_BUDGET_EXHAUSTED"
                    break
                if prior_elapsed + time.monotonic() - start >= cfg["synthetic"]["maximum_seconds"]:
                    reason = "TIME_BUDGET_EXHAUSTED"
                    break
                if duplicates >= cfg["synthetic"]["maximum_consecutive_duplicate_views"]:
                    reason = "LOCKED_REPRESENTATION_YIELD_STOP"
                    break
        db.commit()
        atomic_json(
            root / "capture-complete.json",
            {
                "state": "COMPLETED",
                "reason": reason,
                "candidates": cursor(db, "synthetic_position"),
                "namespace_only": True,
                "verified_receipts": db.execute("SELECT count(*) FROM views").fetchone()[0],
                "scope": "finite catalog expression grammar, not natural Web generalization",
            },
        )
    finally:
        db.close()
        server.shutdown()
        status.close()


def validate_and_decide(root, cfg, status):
    from idps_ai.research.large_pipeline import continue_after_capture

    return continue_after_capture(
        root,
        cfg,
        status,
        SimpleNamespace(REPO=REPO, features=features, open_index=open_index, check_disk=check_disk),
    )


def worker(root):
    cfg = load(configuration_path(root))
    assert file_sha256(configuration_path(root)) == load(authorization_path(root))["config_sha256"]
    for name, sha in load(authorization_path(root))["code_hashes"].items():
        assert file_sha256(REPO / name) == sha, "Code binding changed"
    assert file_sha256(REPO / cfg["source"]["path"]) == cfg["source"]["sha256"]
    with RunLock(root / "worker-lock"), threadpool_limits(1):
        status = Status(root)
        try:
            atomic_json(
                root / "existing-training.json",
                {
                    "TRAIN_examples": verified_existing_training(),
                    "scope": "previous immutable200K release, not new data",
                },
            )
            if not (root / "architecture-proof.json").exists():
                architecture_probe(root, status)
            status.write(
                actual_trainable_parameters=load(root / "architecture-proof.json")[
                    "trainable_parameters"
                ]
            )
            if not (root / "inventory.json").exists():
                assert file_sha256(REPO / cfg["source"]["path"]) == cfg["source"]["sha256"]
                assert (
                    pq.ParquetFile(REPO / cfg["source"]["path"]).metadata.num_rows
                    == cfg["source"]["rows"]
                )
                snapshot = module(REPO / "scripts/local-v1-acceptance.py").protected_snapshot()
                atomic_json(
                    root / "inventory.json",
                    {
                        "frozen_files": snapshot,
                        "source_sha256": cfg["source"]["sha256"],
                        "hybrid_previous_result": load(HYBRID / "supervisor.json"),
                        "model_parameter_formula": parameter_count(),
                        "source_roles_unchanged": True,
                    },
                )
            if not (root / "public-census.json").exists():
                reuse_census(root, cfg, status)
            if not (root / "capture-complete.json").exists():
                with sqlite3.connect(
                    "file:" + str(root / "qualification.sqlite") + "?mode=ro", uri=True
                ) as db:
                    position = cursor(db, "synthetic_position")
                status.write(
                    phase=PHASES[2],
                    completed=position,
                    total=cfg["synthetic"]["maximum_candidates"],
                )
                status.close()
                with (root / "capture.log").open("ab") as log:
                    subprocess.run(
                        [
                            "unshare",
                            "-Urn",
                            sys.executable,
                            str(Path(__file__)),
                            "capture",
                            "--run",
                            str(root),
                        ],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                        timeout=cfg["synthetic"]["maximum_seconds"] + 120,
                    )
                status = Status(root)
            validate_and_decide(root, cfg, status)
        except BaseException as exc:
            status.write(
                state="FAILED",
                blocker=type(exc).__name__ + ":" + str(exc),
                next_automatic_action="STOP",
            )
            atomic_json(
                root / "worker-failure.json",
                {"type": type(exc).__name__, "reason": str(exc), "phase": status.v["phase"]},
            )
            raise
        finally:
            status.close()


def launch(root, resume=False):
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:8])
    if resume:
        previous = load(root / "supervisor.json")
        assert previous["state"] not in ["BLOCKED", "COMPLETED"], (
            "Terminal data gates cannot be bypassed by resume"
        )
        assert process_identity(previous["pid"]) != previous.get("start_ticks"), (
            "Supervisor still alive"
        )
        auth = load(authorization_path(root))
        assert auth["config_sha256"] == file_sha256(configuration_path(root))
        for name, sha in auth["code_hashes"].items():
            assert file_sha256(REPO / name) == sha, "Resume code changed"
        atomic_json(root / ("previous-supervisor-" + str(time.time_ns()) + ".json"), previous)
        for name in ["terminal-status.json", "worker-status.json"]:
            if (root / name).exists():
                atomic_json(
                    root / ("previous-" + str(time.time_ns()) + "-" + name), load(root / name)
                )
    else:
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(
        root / "launcher-owner.json",
        {"pid": os.getpid(), "start_ticks": process_identity(os.getpid())},
    )
    cfg = load(configuration_path(root)) if resume else load(CONFIG)
    if not resume:
        atomic_json(root / "locked-config.json", cfg)
        atomic_json(
            root / "authorization.json",
            {
                "config_sha256": file_sha256(CONFIG),
                "created": time.time(),
                "scope": "one bounded qualification workflow; data failure stops all subsequent phases",
                "code_hashes": {
                    str(p.relative_to(REPO)): file_sha256(p)
                    for p in [
                        Path(__file__),
                        REPO / "ai-training/src/idps_ai/research/large_request.py",
                        *[
                            REPO / "ai-training/src/idps_ai" / name
                            for name in [
                                "training/models.py",
                                "training/tabular.py",
                                "training/checkpoint.py",
                                "features/request_preprocessing.py",
                                "features/request_view.py",
                                "features/rich_content_v2.py",
                                "features/rich_content.py",
                                "features/safe_content.py",
                            ]
                        ],
                    ]
                },
            },
        )
    hw = hardware_snapshot()
    if not resume:
        atomic_json(root / "hardware.json", hw)
    else:
        atomic_json(root / ("hardware-resume-" + str(time.time_ns()) + ".json"), hw)
    cutoff = min(85, hw["effective_emergency_C"])
    # Reuse tested cgroup+independent watchdog; no global thermal changes.
    with RunLock(REPO / ".local-dev/large-request-workflow-lock"):
        supervisor = {
            "state": "RUNNING",
            "pid": os.getpid(),
            "start_ticks": process_identity(os.getpid()),
            "heartbeat": time.time(),
            "run_id": root.name,
        }
        atomic_json(root / "supervisor.json", supervisor)
        previous = load(HYBRID / "supervisor.json")
        if previous["state"] == "RUNNING" and process_identity(previous["pid"]):
            raise RuntimeError("Conflicting Hybrid job remains alive; preserve it")
        guard = root / ("guard-" + str(time.time_ns()))
        atomic_json(root / "active-guard.json", {"path": guard.name})
        atomic_json(
            root / "cpu-ramp-plan.json",
            {
                "steps": [5, 10, 20, 30, 50],
                "window_seconds": 60,
                "worker_status": str(root / "worker-status.json"),
            },
        )
        command = [
            sys.executable,
            str(REPO / "ai-training/scripts/integration-guard.py"),
            "--output",
            str(guard),
            "--scope",
            "--policy",
            "rolling",
            "--quota",
            "5",
            "--memory-gib",
            "12",
            "--cutoff",
            str(cutoff),
            "--tasks-max",
            "128",
            "--max-seconds",
            str(cfg["resources"]["maximum_workflow_seconds"]),
            "--data-quota-plan",
            str(root / "cpu-ramp-plan.json"),
            "--",
            sys.executable,
            str(Path(__file__)),
            "worker",
            "--run",
            str(root),
        ]
        p = subprocess.Popen(command, cwd=REPO, preexec_fn=parent_death_signal)
        try:
            while p.poll() is None:
                supervisor.update(heartbeat=time.time(), guard_pid=p.pid)
                try:
                    children = psutil.Process(p.pid).children()
                except psutil.Error:
                    children = []
                for process in children:
                    try:
                        if "watchdog" in process.cmdline():
                            supervisor.update(
                                watchdog_pid=process.pid,
                                watchdog_start_ticks=process_identity(process.pid),
                            )
                    except psutil.Error:
                        pass
                atomic_json(root / "supervisor.json", supervisor)
                time.sleep(0.5)
            terminal = (
                load(root / "terminal-status.json")
                if (root / "terminal-status.json").exists()
                else {
                    "state": "FAILED",
                    "blockers": ["WORKER_OR_RESOURCE_GATE_FAILED"],
                    "local_release": "BLOCKED",
                }
            )
            if p.returncode:
                terminal.update(
                    state="FAILED",
                    resource_gate="FAILED",
                    guard_returncode=p.returncode,
                    next_automatic_action="STOP",
                )
                terminal.update(
                    training="NOT_STARTED",
                    optimizer_updates=0,
                    model_integration="NOT_STARTED",
                    manual_firewall="NOT_RUN",
                    dataset_status="NOT_QUALIFIED",
                    sealed_access=False,
                )
                training_pointer = root / "large-training-v1/latest.json"
                if training_pointer.exists():
                    terminal.update(
                        training="INTERRUPTED",
                        optimizer_updates=load(training_pointer)["global_step"],
                        checkpoint=str(training_pointer),
                    )
                if (root / "architecture-proof.json").exists():
                    terminal["model_architecture_proof"] = load(root / "architecture-proof.json")
                if (root / "worker-status.json").exists():
                    terminal["last_worker_status"] = load(root / "worker-status.json")
                if (guard / "resource-status.json").exists():
                    terminal["resource_status"] = load(guard / "resource-status.json")
            terminal.update(supervisor_pid=os.getpid(), completed=time.time())
            atomic_json(root / "terminal-status.json", terminal)
            supervisor.update(state=terminal["state"], heartbeat=time.time())
            atomic_json(root / "supervisor.json", supervisor)
            with (root / "progress-vi.log").open("a") as f:
                f.write(
                    "\nWorkflow kết thúc: "
                    + terminal["state"]
                    + ". Training chưa bắt đầu; không tự restart. Xem terminal-status.json.\n"
                )
        finally:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=15)


def show(root):
    worker = load(root / "worker-status.json") if (root / "worker-status.json").exists() else {}
    supervisor = load(root / "supervisor.json") if (root / "supervisor.json").exists() else {}
    guard = (
        load(guard_dir(root) / "resource-status.json")
        if (guard_dir(root) / "resource-status.json").exists()
        else {}
    )
    print(
        f"Run ID: {root.name}\nGiai đoạn: {worker.get('phase', 'KHỞI TẠO')}\nTrạng thái: {supervisor.get('state', 'CHƯA CHẠY')}"
    )
    cfg = load(configuration_path(root))
    print(
        f"DATA_TARGET = {cfg['targets']['distinct_requests']}; TRAIN_TARGET = {cfg['targets']['unique_TRAIN_examples']}"
    )
    readiness = root / "release-v1/readiness.json"
    if readiness.exists():
        release = load(readiness)
        print(
            f"TRAIN release mới: {release['unique_TRAIN_examples']}; requests eligible: {release['distinct_eligible_request_representations']}; gate: {release['state']}"
        )
    else:
        print(
            f"TRAIN release mới: CHƯA QUALIFIED; staging views: {worker.get('new_staging_TRAIN_views', 0)}; baseline cũ15.890 không cộng thêm"
        )
    ramp_path = guard_dir(root) / "cpu-ramp.json"
    if ramp_path.exists():
        ramp = load(ramp_path)
        window = ramp.get("last_window") or (ramp.get("history") or [{}])[-1]
        print(
            f"Ramp: {ramp['state']}; ceiling {ramp['ceiling_percent_one_core']}% một core (actual quota bên dưới)"
        )
        print(
            f"Candidates/s: {window.get('candidates_per_second')}; receipts/s: {window.get('receipts_per_second')}; eligible/s: {window.get('eligible_per_second')}; cửa sổ {window.get('window_seconds')}s"
        )
        print(
            f"Nhiệt trung bình/đỉnh cửa sổ: {window.get('average_temperature')}/{window.get('maximum_temperature')}°C"
        )
    print(
        f"Nhiệt trung bình đang chạy: {guard.get('thermal', {}).get('active_time_weighted_c')}; đỉnh monitor: {guard.get('maximum_temperature_C')}"
    )
    watchdog = supervisor.get("watchdog_pid")
    watchdog_alive = bool(
        watchdog and process_identity(watchdog) == supervisor.get("watchdog_start_ticks")
    )
    print(f"Watchdog độc lập: {'ACTIVE' if watchdog_alive else 'STOPPED'}; PID: {watchdog}")
    n, total = worker.get("completed", 0), worker.get("total", 0)
    print(f"Tiến độ: {n}/{total}; còn {max(0, total - n)} (giai đoạn hiện tại)")
    eta = worker.get("ETA_seconds_interval")
    print(
        "Ước tính còn: "
        + (
            f"{eta[0] / 60:.1f}–{eta[1] / 60:.1f} phút; cửa sổ {worker['ETA_window_seconds']:.0f}s"
            if eta
            else "CHƯA ĐỦ DỮ LIỆU ĐỂ ƯỚC TÍNH"
        )
    )
    print(
        f"Tham số dự kiến: {worker.get('planned_parameters', parameter_count())}; thực tế xác minh: {worker.get('actual_trainable_parameters')}"
    )
    print(
        f"Requests có receipts mới: {worker.get('verified_distinct_HTTP_requests', 0)}; TRAIN hợp lệ đã kiểm chứng trước: 15890; không cộng census vào TRAIN"
    )
    print(f"Updates: {worker.get('optimizer_updates', 0)}; loss: {worker.get('training_loss')}")
    print(
        f"CPU host: {guard.get('host_cpu_utilization_percent')}%; quota một core: {guard.get('quota_percent_one_cpu')}%; RAM khả dụng: {guard.get('mem_available_bytes')}; nhiệt: {guard.get('thermal', {}).get('current_c')}°C"
    )
    for name, info in [("Supervisor", supervisor), ("Worker", worker)]:
        alive = bool(info.get("pid") and process_identity(info["pid"]) == info.get("start_ticks"))
        print(
            f"{name}: {'ACTIVE' if alive else 'STOPPED'}; heartbeat age: {round(time.time() - info.get('heartbeat', 0), 1)}s"
        )
    print(
        f"Watchdog/resource: {guard.get('status', 'NOT_STARTED')}; checkpoint: {worker.get('checkpoint', root / 'qualification.sqlite')}\nBlocker: {worker.get('blocker', 'chưa có kết luận')}\nTiếp theo: {worker.get('next_automatic_action', 'capture → kiểm định → gate1M; dừng nếu FAIL')}\nLog: {root / 'progress-vi.log'}"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action", choices=["launch", "resume", "reconfigure", "worker", "capture", "status"]
    )
    p.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    root = args.run.resolve()
    if args.action != "status" and (root / "POSTPONED.json").exists():
        raise SystemExit("POSTPONED: preserve receipts/checkpoints; future explicit user authorization and reviewed resume migration required")
    if args.action in ["launch", "resume"]:

        def interrupt(*args):
            raise InterruptedError("Supervisor interrupted; guarded cgroup stopped")

        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        try:
            launch(root, args.action == "resume")
        except BaseException as exc:
            owner = root / "launcher-owner.json"
            if owner.exists() and load(owner).get("pid") == os.getpid():
                failure = {
                    "state": "FAILED",
                    "type": type(exc).__name__,
                    "reason": str(exc),
                    "training": "NOT_STARTED",
                    "local_release": "BLOCKED",
                    "next_automatic_action": "STOP",
                }
                atomic_json(root / "terminal-status.json", failure)
                atomic_json(
                    root / "supervisor.json",
                    dict(
                        failure,
                        pid=os.getpid(),
                        start_ticks=process_identity(os.getpid()),
                        heartbeat=time.time(),
                    ),
                )
            raise
    elif args.action == "worker":
        worker(root)
    elif args.action == "capture":
        with threadpool_limits(1):
            capture(root, load(configuration_path(root)))
    elif args.action == "reconfigure":
        print(json.dumps(reconfigure(root), indent=2))
    else:
        show(root)

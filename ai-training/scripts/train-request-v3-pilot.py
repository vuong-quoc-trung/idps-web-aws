#!/usr/bin/env python3
"""One finite actual-TRAIN pilot; no CAL/DEV arrays loaded and no promotion."""

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import psutil
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import vector_hash
from idps_ai.features import request_v3
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.models import Model

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "ai-training/configs/research/request-v3-grounded-pilot-20261108.json"
FROZEN = ROOT / "ai-training/.artifacts/request_intelligence_v2_20261104/run/model"


def load(path):
    return json.loads(Path(path).read_text())


def canonical_indices(x, y, eligible, ids):
    seen, result = {}, []
    for i in sorted(np.flatnonzero(eligible), key=lambda i: str(ids[i])):
        key = vector_hash(x[i])
        if key in seen:
            assert y[i] == y[seen[key]], "Mixed labels in admitted TRAIN view"
        else:
            assert y[i] in (0, 1)
            seen[key] = i
            result.append(int(i))
    return np.array(result, np.int64)


def order_for_epoch(rng, groups):
    """Interleave recorded lineage groups; each canonical view exactly once."""
    by_group = defaultdict(list)
    for i, g in enumerate(groups):
        by_group[g].append(i)
    group_order = list(rng.permutation(sorted(by_group)))
    queues = {g: list(rng.permutation(by_group[g])) for g in group_order}
    out = []
    while any(queues.values()):
        for g in group_order:
            if queues[g]:
                out.append(queues[g].pop())
    assert sorted(out) == list(range(len(groups)))
    return np.array(out, np.int64)


def inputs():
    cfg = load(CONFIG)
    assert cfg["fingerprint"] == digest({k: v for k, v in cfg.items() if k != "fingerprint"})
    assert cfg["architecture"]["layer_dims"] == [634, 64, 64, 64, 64, 8]
    assert cfg["feature_contract_fingerprint"] == request_v3.fingerprint()
    assert cfg["architecture"]["objective"] == {
        "kind": "partial_binary_v1",
        "smoothing": 0.005,
        "family_weight": 0.0,
    }
    for p, sha in cfg["source_sha256"].items():
        assert file_sha256(ROOT / p) == sha
    data = ROOT / cfg["dataset_release"]
    assert file_sha256(data / "dataset-release.json") == cfg["dataset_release_manifest_sha256"]
    manifest = load(data / "dataset-release.json")
    assert manifest["dataset_fingerprint"] == cfg["dataset_fingerprint"]
    # Byte hashing other roles is integrity verification, not gradient/statistic use.
    for p, sha in manifest["files_sha256"].items():
        assert file_sha256(data / p) == sha
    rows = [json.loads(s) for s in (data / "records.jsonl").read_text().splitlines()]
    rows = [r for r in rows if r["original_role"] == "TRAIN"]
    with np.load(data / "train.npz", allow_pickle=False) as z:
        assert [r["sample_id"] for r in rows] == list(z["ids"])
        ix = canonical_indices(z["x"], z["binary_y"], z["eligible"], z["ids"])
        x, y = z["x"][ix].copy(), z["binary_y"][ix].copy()
    assert x.shape == (42, 634) and x.dtype == np.float32 and np.isfinite(x).all()
    # Reuse the same recorded session/campaign connected-component definition.
    spec = importlib.util.spec_from_file_location(
        "audit", Path(__file__).with_name("materialize-request-v3.py")
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    roots = audit.lineage_roots(rows)
    groups = [str(roots[int(i)]) for i in ix]
    return cfg, x, y, [rows[int(i)] for i in ix], groups


def prepare(run):
    cfg, x, y, rows, groups = inputs()
    assert not run.exists()
    run.mkdir(mode=0o700, parents=True)
    frozen = load_checkpoint(FROZEN)
    model = Model(634, 64, "deep_mlp", 17, objective=cfg["architecture"]["objective"])
    model.parameters = request_v3.expanded_parameters(frozen.model.parameters)
    assert model.layer_dims == cfg["architecture"]["layer_dims"]
    assert sum(v.size for v in model.parameters.values()) == 53640
    assert model.steps == 0 and all(not np.any(a) for d in [model.m, model.v] for a in d.values())
    assert model.metadata()["partial_optimizer"]["weight_decay"] == 0.0001
    assert np.allclose(model.forward(x)[1], frozen.model.forward(x[:, :588])[1], atol=1e-7, rtol=0)
    loss, grad = model.loss_and_gradients(
        x[:16], np.where(y[:16] == 0, 0, -1), binary_targets=y[:16]
    )
    assert np.isfinite(loss) and all(np.isfinite(v).all() for v in grad.values())
    assert model.forward(x[:16])[1].shape == (16, 8)
    budget = cfg["future_budget"]
    steps = min(
        budget["max_optimizer_steps"],
        budget["max_epochs"] * math.ceil(len(x) / budget["batch_size"]),
    )
    assert steps == 60
    plan = {
        "run_id": run.name,
        "dataset_fingerprint": cfg["dataset_fingerprint"],
        "design_fingerprint": cfg["fingerprint"],
        "feature_contract_fingerprint": request_v3.fingerprint(),
        "feature_version": request_v3.VERSION,
        "config_sha256": file_sha256(CONFIG),
        "runner_sha256": file_sha256(__file__),
        "model_source_sha256": cfg["source_sha256"],
        "frozen_generation": str(frozen.path.relative_to(ROOT)),
        "frozen_manifest_sha256": file_sha256(frozen.path / "manifest.json"),
        "frozen_arrays_sha256": file_sha256(frozen.path / "arrays.npz"),
        "architecture": model.metadata(),
        "parameters": 53640,
        "seed": 17,
        "batch_size": 16,
        "learning_rate": 0.0001,
        "weight_decay": 0.0001,
        "max_epochs": 20,
        "max_steps": 128,
        "planned_steps": steps,
        "sampler": "lineage round-robin without replacement; each canonical view once/epoch; recorded groups remain TRAIN only",
        "canonical_TRAIN_rows": 42,
        "eligible_TRAIN_rows": 48,
        "lineage_components": len(set(groups)),
        "lineage_canonical_counts": dict(Counter(groups)),
        "sampler_fingerprint": digest({"ids": [r["sample_id"] for r in rows], "groups": groups}),
        "preflight": {
            "shape": True,
            "parameter_count": True,
            "warmstart_function_parity": True,
            "fresh_optimizer": True,
            "finite_forward_backward_loss": float(loss),
        },
        "checkpoint_interval": 3,
        "checkpoint_selection": "Final budget only; best.json is library bookkeeping and never evaluation selection",
        "fit_partitions": ["TRAIN"],
        "CAL_DEV_tensor_loads_during_fit": 0,
        "evaluator": str(
            Path(__file__).with_name("evaluate-request-v3-pilot.py").relative_to(ROOT)
        ),
        "evaluator_sha256": file_sha256(Path(__file__).with_name("evaluate-request-v3-pilot.py")),
        "resource_supervisor_sha256": file_sha256(Path(__file__).with_name("integration-guard.py")),
        "threshold_protocol": cfg["evaluation_protocol"]["thresholds"],
        "retention_screen": cfg["evaluation_protocol"]["retention_screen"],
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(run / "plan.json", plan)
    atomic_json(
        run / "status.json",
        {
            "status": "PREPARED",
            "run_id": run.name,
            "current_step": 0,
            "planned_steps": 60,
            "dataset_fingerprint": cfg["dataset_fingerprint"],
            "last_heartbeat": time.time(),
        },
    )
    print(
        json.dumps(
            {"run_id": run.name, "parameters": 53640, "planned_steps": steps, "warmstart": "PASS"}
        )
    )


def train(run, resource, resume=False):
    plan = load(run / "plan.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert (
        file_sha256(__file__) == plan["runner_sha256"]
        and file_sha256(CONFIG) == plan["config_sha256"]
    )
    cfg, x, y, rows, groups = inputs()
    assert cfg["fingerprint"] == plan["design_fingerprint"]
    assert (
        digest({"ids": [r["sample_id"] for r in rows], "groups": groups})
        == plan["sampler_fingerprint"]
    )
    frozen = load_checkpoint(ROOT / plan["frozen_generation"])
    assert (
        file_sha256(frozen.path / "manifest.json") == plan["frozen_manifest_sha256"]
        and file_sha256(frozen.path / "arrays.npz") == plan["frozen_arrays_sha256"]
    )
    rng = np.random.default_rng(17)
    checkpoint = None
    if resume:
        assert load(run.parent / "actual-pilot-started.json")["run_id"] == run.name
        ck = load_checkpoint(run / "model")
        model, state, order = ck.model, ck.state, ck.permutation
        assert not ck.used_previous, (
            "Explicit recovery required if latest corrupt; no silent fallback"
        )
        assert (
            state["plan_fingerprint"] == plan["fingerprint"]
            and state["dataset_fingerprint"] == cfg["dataset_fingerprint"]
        )
        assert (
            state["feature_contract_fingerprint"] == request_v3.fingerprint()
            and state["design_fingerprint"] == cfg["fingerprint"]
        )
        assert state["scheduler"] == {
            "kind": "constant",
            "learning_rate": 0.0001,
            "step": model.steps,
        }
        assert state["objective"] == model.objective == cfg["architecture"]["objective"]
        assert state["planned_steps"] == 60 and state["learning_rate"] == 0.0001
        assert sorted(order.tolist()) == list(range(42)) and 0 < model.steps <= 60
        rng.bit_generator.state = state["RNG"]
        epoch = state["epoch"]
        cursor = state["cursor"]
        checkpoint = ck.path
        journal = [json.loads(s) for s in (run / "loss.jsonl").read_text().splitlines()]
        assert len(journal) == model.steps and journal[-1]["step"] == model.steps, (
            "Uncommitted log rows require explicit recovery reconciliation"
        )
    else:
        assert not (run / "model/latest.json").exists()
        model = Model(634, 64, "deep_mlp", 17, objective=cfg["architecture"]["objective"])
        model.parameters = request_v3.expanded_parameters(frozen.model.parameters)
        epoch = cursor = 0
        order = order_for_epoch(rng, groups)
    family = np.where(y == 0, 0, -1).astype(np.int64)
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(0.2):
            (run / "heartbeat").touch()

    (run / "heartbeat").touch()
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

    def status(value, loss=None, error=None):
        monitor = (
            load(resource / "resource-status.json")
            if (resource / "resource-status.json").exists()
            else {}
        )
        atomic_json(
            run / "status.json",
            {
                "status": value,
                "run_id": run.name,
                "dataset_fingerprint": cfg["dataset_fingerprint"],
                "feature_contract_fingerprint": request_v3.fingerprint(),
                "current_step": model.steps,
                "planned_steps": 60,
                "epoch": epoch,
                "cursor": cursor,
                "training_loss": loss,
                "checkpoint": str(checkpoint) if checkpoint else None,
                "checkpoint_directory": str(run / "model"),
                "log": str(run / "loss.jsonl"),
                "PID": os.getpid(),
                "resource_service": monitor.get("unit"),
                "supervisor_service": os.environ.get("PILOT_SUPERVISOR"),
                "resource_status": str(resource / "resource-status.json"),
                "last_heartbeat": time.time(),
                "RSS_bytes": psutil.Process().memory_info().rss,
                "MemAvailable_bytes": psutil.virtual_memory().available,
                "error": error,
            },
        )

    def save():
        state = {
            "plan_fingerprint": plan["fingerprint"],
            "dataset_fingerprint": cfg["dataset_fingerprint"],
            "design_fingerprint": cfg["fingerprint"],
            "feature_contract_fingerprint": request_v3.fingerprint(),
            "epoch": epoch,
            "cursor": cursor,
            "RNG": rng.bit_generator.state,
            "learning_rate": 0.0001,
            "scheduler": {"kind": "constant", "learning_rate": 0.0001, "step": model.steps},
            "objective": model.objective,
            "planned_steps": 60,
            "source_fingerprints": plan["model_source_sha256"],
            "loss_log_rows": model.steps,
            "scope": "ACTUAL_QUALIFIED_TRAIN_ONLY",
        }
        return save_checkpoint(run / "model", model, state, order)

    try:
        with RunLock(run.parent), RunLock(run), threadpool_limits(limits=1):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                monitor = (
                    load(resource / "resource-status.json")
                    if (resource / "resource-status.json").exists()
                    else {}
                )
                unit = monitor.get("unit")
                watchdog = [
                    p.pid
                    for p in psutil.process_iter(["cmdline"])
                    if unit
                    and all(v in (p.info["cmdline"] or []) for v in ["watchdog", "--unit", unit])
                ]
                if watchdog and monitor.get("status") == "RUNNING":
                    break
                time.sleep(0.05)
            assert watchdog and monitor.get("status") == "RUNNING", (
                "Independent resource watchdog not ready"
            )
            atomic_json(
                run / ("resume-watchdog.json" if resume else "launch-watchdog.json"),
                {
                    "status": "READY",
                    "watchdog_PID": watchdog[0],
                    "training_PID": os.getpid(),
                    "resource_unit": unit,
                    "independent_process": watchdog[0] != os.getpid(),
                },
            )
            if not resume:
                assert not (run.parent / "actual-pilot-started.json").exists(), (
                    "One actual pilot only; explicit same-run resume allowed"
                )
                atomic_json(
                    run.parent / "actual-pilot-started.json",
                    {"run_id": run.name, "plan_fingerprint": plan["fingerprint"]},
                )
            status("RUNNING")
            with (run / "loss.jsonl").open("a" if resume else "x") as log:
                while model.steps < 60 and epoch < 20:
                    ix = order[cursor : cursor + 16]
                    assert len(ix) > 0
                    loss = float(model.train_batch(x[ix], family[ix], 0.0001, binary_targets=y[ix]))
                    assert np.isfinite(loss)
                    cursor += len(ix)
                    log.write(
                        json.dumps(
                            {
                                "step": model.steps,
                                "epoch": epoch,
                                "cursor": cursor,
                                "batch_rows": len(ix),
                                "loss": loss,
                                "timestamp": time.time(),
                            }
                        )
                        + "\n"
                    )
                    log.flush()
                    os.fsync(log.fileno())
                    if cursor == len(order):
                        epoch += 1
                        if epoch < 20:
                            cursor = 0
                            order = order_for_epoch(rng, groups)
                    if model.steps == 1 or model.steps % 3 == 0 or model.steps == 60:
                        checkpoint = save()
                    if model.steps == 1 and not resume:
                        ck = load_checkpoint(run / "model")
                        assert ck.model.steps == 1 and ck.state["cursor"] == 16
                        assert all(
                            np.array_equal(v, ck.model.arrays()[k])
                            for k, v in model.arrays().items()
                        )
                        atomic_json(
                            run / "actual-preflight.json",
                            {
                                "status": "PASS",
                                "actual_step1_committed": True,
                                "forward_backward_optimizer": "PASS",
                                "checkpoint_write_read": "PASS",
                                "fresh_optimizer_step0_then_nonzero_step1": True,
                                "manifest_sha256": file_sha256(ck.path / "manifest.json"),
                                "resource_watchdog_required": True,
                            },
                        )
                        status("RUNNING", loss)
                        # Continue this same run in another process from step1, not restart.
                        break
                    status("RUNNING", loss)
            if model.steps == 1 and not resume:
                pass
            else:
                ck = load_checkpoint(run / "model")
                assert ck.model.steps == 60 and epoch == 20
                assert all(
                    np.array_equal(v, ck.model.arrays()[k]) for k, v in model.arrays().items()
                )
                atomic_json(
                    run / "completion.json",
                    {
                        "status": "COMPLETED",
                        "run_id": run.name,
                        "steps": 60,
                        "epochs": 20,
                        "checkpoint": str(ck.path.relative_to(ROOT)),
                        "manifest_sha256": file_sha256(ck.path / "manifest.json"),
                        "dataset_fingerprint": cfg["dataset_fingerprint"],
                        "plan_fingerprint": plan["fingerprint"],
                        "cross_process_resume_from_actual_step1": True,
                        "final_checkpoint_verified": True,
                        "CAL_DEV_gradients": 0,
                    },
                )
                status("COMPLETED", loss)
    except BaseException as exc:
        status(
            "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED",
            error=type(exc).__name__,
        )
        raise
    finally:
        stop.set()
        thread.join(timeout=1)
    if not resume:
        subprocess.run(
            [
                sys.executable,
                __file__,
                "train",
                "--run",
                str(run),
                "--resource",
                str(resource),
                "--resume",
            ],
            check=True,
        )


def supervise(run, resource):
    plan = load(run / "plan.json")
    assert (
        file_sha256(Path(__file__).with_name("integration-guard.py"))
        == plan["resource_supervisor_sha256"]
    )
    spec = importlib.util.spec_from_file_location(
        "guard", Path(__file__).with_name("integration-guard.py")
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    try:
        guard.run(
            [sys.executable, __file__, "train", "--run", str(run), "--resource", str(resource)],
            resource,
            quota=25,
            max_seconds=300,
            memory_gib=2,
            cutoff=85,
        )
        assert load(run / "completion.json")["final_checkpoint_verified"]
        ck = load_checkpoint(run / "model")
        assert ck.model.steps == 60 and not ck.used_previous
        atomic_json(
            run / "supervisor-result.json",
            {
                "status": "COMPLETED",
                "final_checkpoint_verified": True,
                "service": os.environ.get("PILOT_SUPERVISOR"),
                "checkpoint": str(ck.path),
                "steps": ck.model.steps,
                "finished_at": time.time(),
            },
        )
    except BaseException as exc:
        monitor = (
            load(resource / "resource-status.json")
            if (resource / "resource-status.json").exists()
            else {}
        )
        previous = load(run / "status.json")
        previous.update(
            status=monitor.get("status", "FAILED")
            if monitor.get("status") in ["FAILED", "THERMAL_STOPPED", "INTERRUPTED"]
            else "FAILED",
            error=type(exc).__name__,
            last_heartbeat=time.time(),
        )
        atomic_json(run / "status.json", previous)
        atomic_json(
            run / "supervisor-result.json",
            {
                "status": previous["status"],
                "error": type(exc).__name__,
                "resource_status": str(resource / "resource-status.json"),
            },
        )
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "train", "supervise"])
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--resource", type=Path)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        if a.action == "prepare":
            prepare(a.run.resolve())
        elif a.action == "train":
            train(a.run.resolve(), a.resource.resolve(), a.resume)
        else:
            supervise(a.run.resolve(), a.resource.resolve())

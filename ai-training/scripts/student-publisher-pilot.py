#!/usr/bin/env python3
"""Fixed offline publisher-anomaly pilot; no automatic evaluation or promotion."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil
from threadpoolctl import threadpool_limits

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.checkpoint import RunLock, load_checkpoint
from idps_ai.training.heartbeat import SupervisorHeartbeat
from idps_ai.training.student_publisher import (
    initial_state,
    make_model,
    planned_steps,
    reload,
    save,
    update_once,
)

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "ai-training/configs/research/student-publisher-pilot-20261110.json"
SOURCE = REPO / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"
CHECKED = REPO / ".local-dev/student-pilot-20261110"


def load(p):
    return json.loads(Path(p).read_text())


def resource_module():
    p = Path(__file__).with_name("student-data-recovery.py")
    spec = importlib.util.spec_from_file_location("existing_resource_helpers", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def code_hashes():
    paths = [
        Path(__file__),
        CONFIG,
        REPO / "ai-training/src/idps_ai/training/student_publisher.py",
        REPO / "ai-training/src/idps_ai/training/models.py",
        REPO / "ai-training/src/idps_ai/training/deep.py",
        REPO / "ai-training/src/idps_ai/training/partial.py",
        REPO / "ai-training/src/idps_ai/training/checkpoint.py",
        Path(__file__).with_name("adaptive-thermal-guard.py"),
        Path(__file__).with_name("student-data-recovery.py"),
        REPO / "ai-training/src/idps_ai/training/heartbeat.py",
        REPO / "ai-training/src/idps_ai/training/adaptive_thermal.py",
    ]
    return {str(p.relative_to(REPO)): file_sha256(p) for p in paths}


def bind(plan):
    check = dict(plan)
    fp = check.pop("fingerprint")
    assert digest(check) == fp
    assert plan["code_hashes"] == code_hashes()
    return plan


def initialize(run, mode):
    attempt = run / "attempts" / mode
    assert not attempt.exists(), "Never overwrite a supervised attempt"
    if mode == "prepare":
        assert not run.exists()
        run.mkdir(parents=True, mode=0o700)
    else:
        bind(load(run / "plan.json"))
        assert load(run / "actual-preflight.json")["state"] == "PASS"
        assert load_checkpoint(run / "model").model.steps == 2
    hw = hardware_snapshot()
    sample = SensorReader(hw).read(time.monotonic())
    assert sample["temperature_C"] < 75 and not sample["hardware_emergency"]
    attempt.mkdir(parents=True, mode=0o700)
    atomic_json(attempt / "hardware.json", hw)
    controls = {
        "original_run_id": run.name,
        "preflight": False,
        "warning_C": 85,
        "throttle_C": 90,
        "strong_throttle_C": 93,
        "cooldown_seconds": 15,
        "maximum_cooldown_seconds": 300,
        "effective_emergency_C": hw["effective_emergency_C"],
        "mode": mode,
        "code_hashes": code_hashes(),
        "runtime_seconds": 240 if mode == "prepare" else 7200,
    }
    controls["fingerprint"] = digest(controls)
    atomic_json(attempt / "recovery-plan.json", controls)
    print(json.dumps({"mode": mode, "run_id": run.name, "attempt": str(attempt)}), flush=True)


def prepare(run, attempt, status):
    cfg = load(CONFIG)
    proof = load(CHECKED / "checked.json")
    summary = load(SOURCE / "materialized/summary.json")
    assert summary["fingerprint"] == cfg["dataset_fingerprint"] == proof["dataset_fingerprint"]
    assert load(SOURCE / "attempts/recovery-a2/result.json")["state"] == "COMPLETED"
    assert summary == load(SOURCE / "rebuild/summary.json")
    for name, sha in summary["files"].items():
        assert file_sha256(SOURCE / "materialized" / name) == sha
    with np.load(CHECKED / "ready-private.npz", allow_pickle=False) as z:
        x = z["x"].copy()
        y = z["y"].copy()
        groups = z["groups"].copy()
        roles = z["role"].copy()
        canonical = z["canonical"].copy()
        rows = z["rows"].copy()
    assert x.shape == (3783, 588) and np.isfinite(x).all() and len(canonical) == 3751
    split = {}
    manifest = []
    (run / "data").mkdir()
    for role in ["TRAIN", "CALIBRATION", "EVALUATION"]:
        ix = canonical[roles[canonical] == role]
        classes = np.bincount(y[ix], minlength=2)
        assert min(classes) >= cfg["split"]["minimum_each_class_per_role"]
        if role == "TRAIN":
            assert len(ix) >= cfg["split"]["minimum_canonical_train"]
        split[role] = {
            "examples": int(len(ix)),
            "normal": int(classes[0]),
            "anomalous": int(classes[1]),
            "groups": int(len(set(groups[ix]))),
        }
        np.savez(
            run / "data" / f"{role.lower()}.npz", x=x[ix], y=y[ix], groups=groups[ix], rows=rows[ix]
        )
        for i in ix:
            manifest.append(
                {
                    "row": int(rows[i]),
                    "role": role,
                    "group": int(groups[i]),
                    "target": int(y[i]),
                    "tier": "SILVER",
                }
            )
    # No role reassignment of the source release: only this candidate's internal mapping.
    by_group = {}
    for m in manifest:
        assert by_group.setdefault(m["group"], m["role"]) == m["role"]
    atomic_json(run / "data/split.json", manifest)
    split_fp = digest(manifest)
    source_ledger = {
        int(m["row"]): m
        for m in map(json.loads, (SOURCE / "materialized/ledger.jsonl").open())
        if m["decision"] == "TRAINING_ELIGIBLE"
    }
    assert len(source_ledger) == len(x)
    shard_cache = {}
    for i, source_row in enumerate(rows):
        original = source_ledger[int(source_row)]
        assert original["tier"] == "SILVER" and original["target"] == int(y[i])
        ref = original["feature_ref"]
        if ref["shard"] not in shard_cache:
            with np.load(SOURCE / "materialized" / ref["shard"], allow_pickle=False) as stored:
                shard_cache[ref["shard"]] = stored["x"].copy()
        assert np.array_equal(x[i], shard_cache[ref["shard"]][ref["slot"]])
    del shard_cache
    controls = {}
    for scope in ["TRAIN"]:
        selected = [m for m in manifest if m["role"] == scope]
        for key in ["window", "body"]:
            buckets = {}
            for m in selected:
                src = source_ledger[m["row"]]
                value = (
                    str(int(src["source_row"] >= 1048576))
                    if key == "window"
                    else src["body_observation"]
                )
                counts = buckets.setdefault(value, [0, 0])
                counts[m["target"]] += 1
            controls[key] = buckets
    train = run / "data/train.npz"
    with np.load(train, allow_pickle=False) as z:
        tx = z["x"].copy()
        ty = z["y"].copy()
        tg = z["groups"].copy()
    n = len(ty)
    model = make_model(ty, cfg["training"]["seed"])
    initial_hash = digest(
        {k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in model.parameters.items()}
    )
    plan = {
        "run_id": run.name,
        "task": "publisher_anomaly",
        "dataset_fingerprint": summary["fingerprint"],
        "feature_contract": cfg["feature_contract"],
        "split_fingerprint": split_fp,
        "split_counts": split,
        "dataset_examples": 3783,
        "canonical_views": 3751,
        "training_examples": n,
        "tiers": {"SILVER": n},
        "seed": 17,
        "epochs": 10,
        "batch_size": 64,
        "learning_rate": 0.001,
        "planned_steps": planned_steps(n, 10, 64),
        "checkpoint_interval": 16,
        "architecture": model.metadata(),
        "parameters": 50696,
        "initial_weights_sha": initial_hash,
        "initialization": "fresh random; no warmstart",
        "code_hashes": code_hashes(),
        "data_files": {p.name: file_sha256(p) for p in (run / "data").iterdir() if p.is_file()},
        "verification_evidence_sha256": file_sha256(CHECKED / "checked.json"),
        "verified_tensor_source_sha256": file_sha256(CHECKED / "ready-private.npz"),
        "majority_baseline": {
            "class": int(np.argmax(np.bincount(ty, minlength=2))),
            "anomaly_prior": float(np.mean(ty)),
        },
        "shortcut_baselines_TRAIN_only": controls,
        "evaluation_protocol": cfg["evaluation"],
        "holdout_scope": "internal grouped holdout from exposed staging; source/campaign independence not established",
        "teacher_pretraining_overlap_source_records": int(proof["teacher_pretrain_overlap"]),
        "actual_optimizer_consumption": "canonical TRAIN only; no CAL/EVAL tensor load in train mode",
        "config_sha256": file_sha256(CONFIG),
        "selection": "final budget only; no early stopping or bestcheckpoint selection",
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(run / "plan.json", plan)
    state, order = initial_state(model, tg, plan)
    original = model.parameters["W0"].copy()
    order = update_once(model, state, order, tx, ty, tg, plan)
    save(run, model, state, order)
    assert model.steps == 1 and not np.array_equal(original, model.parameters["W0"])
    restored, rs, ro, checkpoint = reload(run, plan, n)
    assert all(np.array_equal(v, restored.arrays()[k]) for k, v in model.arrays().items())
    assert rs["cursor"] == state["cursor"] and np.array_equal(ro, order)
    # A same-run next-update control proves Adam/RNG/sampling continuation, not a second candidate.
    clone_state = copy.deepcopy(state)
    clone_order = update_once(model, clone_state, order.copy(), tx, ty, tg, plan)
    ro = update_once(restored, rs, ro, tx, ty, tg, plan)
    assert all(np.array_equal(v, restored.arrays()[k]) for k, v in model.arrays().items())
    assert clone_state == {k: rs[k] for k in clone_state} and np.array_equal(clone_order, ro)
    save(run, restored, rs, ro)
    atomic_json(run / "loss-history.json", rs["losses"])
    atomic_json(
        run / "actual-preflight.json",
        {
            "state": "PASS",
            "actual_committed_updates": 2,
            "checkpoint_step1_reload_exact": True,
            "next_update_parameters_Adam_RNG_cursor_exact": True,
            "calibration_evaluation_gradient_rows": 0,
            "training_examples": n,
            "planned_steps": plan["planned_steps"],
            "checkpoint_directory": str(run / "model"),
        },
    )
    status(
        phase="PREPARED_ACTUAL_STEP2",
        optimizer_updates=2,
        planned_steps=plan["planned_steps"],
        checkpoint=str(run / "model/latest.json"),
    )


def train(run, attempt, status):
    plan = bind(load(run / "plan.json"))
    for name, sha in plan["data_files"].items():
        assert file_sha256(run / "data" / name) == sha
    with np.load(run / "data/train.npz", allow_pickle=False) as z:
        x = z["x"]
        y = z["y"]
        groups = z["groups"]
    assert len(x) == plan["training_examples"]
    model, state, order, checkpoint = reload(run, plan, len(x))
    assert model.steps >= 2

    def commit():
        path = save(run, model, state, order)
        atomic_json(run / "loss-history.json", state["losses"])
        return path

    while model.steps < plan["planned_steps"]:
        order = update_once(model, state, order, x, y, groups, plan)
        if model.steps % plan["checkpoint_interval"] == 0 or model.steps == plan["planned_steps"]:
            checkpoint = commit()
        status(
            phase="TRAINING",
            optimizer_updates=int(model.steps),
            planned_steps=plan["planned_steps"],
            epoch=int(state["epoch"]),
            training_loss=state["losses"][-1]["loss"],
            checkpoint=str(checkpoint),
        )
    final = load_checkpoint(run / "model")
    assert final.model.steps == plan["planned_steps"]
    atomic_json(
        run / "training-completion.json",
        {
            "state": "COMPLETED",
            "optimizer_updates": model.steps,
            "planned_steps": plan["planned_steps"],
            "training_examples": plan["training_examples"],
            "dataset_fingerprint": plan["dataset_fingerprint"],
            "plan_fingerprint": plan["fingerprint"],
            "checkpoint": str(final.path),
            "checkpoint_manifest_sha256": file_sha256(final.path / "manifest.json"),
            "evaluation": "NOT_RUN_USER_RETURN_REQUIRED",
            "promotion": False,
        },
    )


def worker(run, attempt, mode):
    cfg = load(attempt / "recovery-plan.json")
    assert cfg["code_hashes"] == code_hashes()
    lock_root = SOURCE.parent / "student-pipeline-global"
    with (
        RunLock(run.parent / "active-publisher-pilot"),
        RunLock(lock_root),
        RunLock(run),
        threadpool_limits(limits=1),
    ):
        lock = threading.Lock()
        done = threading.Event()
        current = {"state": "RUNNING", "phase": "WAITING_GUARD", "pid": os.getpid()}

        def status(**values):
            with lock:
                current.update(values)
                atomic_json(
                    attempt / "worker-status.json", {**current, "last_heartbeat": time.time()}
                )

        def loop():
            while not done.wait(0.5):
                status()

        status()
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        try:
            end = time.monotonic() + 20
            while not (attempt / "start.allowed").exists():
                if time.monotonic() > end:
                    raise PipelineError("Independent watchdog start timeout")
                time.sleep(0.1)
            if mode == "prepare":
                prepare(run, attempt, status)
            else:
                train(run, attempt, status)
            status(state="COMPLETED")
            atomic_json(attempt / "worker-done.json", {"state": "COMPLETED"})
        except BaseException as exc:
            status(state="FAILED", error_type=type(exc).__name__)
            raise
        finally:
            done.set()
            thread.join()


def supervise(run, mode):
    attempt = run / "attempts" / mode
    cfg = load(attempt / "recovery-plan.json")
    assert cfg["code_hashes"] == code_hashes()
    helpers = resource_module()
    g = helpers.guard_module()
    token = str(os.getpid()) + "-" + str(time.time_ns())[-6:]
    work = "idps-student-adaptive-work-pilot-" + token + ".service"
    watch = "idps-student-adaptive-watch-pilot-" + token + ".service"
    h = SupervisorHeartbeat(attempt / "supervisor-heartbeat.json")
    h.start_writer()
    began = time.monotonic()
    terminal = None
    control = None
    last_publish = 0
    try:
        memory = psutil.virtual_memory()
        cap = int(
            min(
                8 * 1024**3,
                memory.available - 4 * 1024**3,
                30_000_000_000 - (memory.total - memory.available) - 4 * 1024**3,
            )
        )
        assert cap >= 1024**3
        helpers.start_service(
            work,
            [
                sys.executable,
                str(Path(__file__)),
                "--run",
                str(run),
                "--mode",
                mode,
                "--action",
                "worker",
            ],
            attempt / "worker.log",
            quota=20,
            memory=cap,
            runtime=cfg["runtime_seconds"] + 10,
            affinity=True,
        )
        control = g.CgroupControl(work)
        atomic_json(
            attempt / "services.json",
            {
                "worker_unit": work,
                "watchdog_unit": watch,
                "supervisor_pid": os.getpid(),
                "worker_cgroup": str(control.path),
                "memory_cap_bytes": cap,
            },
        )
        command = [
            sys.executable,
            str(Path(__file__).with_name("adaptive-thermal-guard.py")),
            "--attempt",
            str(attempt),
            "--unit",
            work,
        ]
        if mode == "prepare":
            command += ["--probe-controls"]
        helpers.start_service(
            watch,
            command,
            attempt / "watchdog.log",
            quota=20,
            memory="256M",
            runtime=cfg["runtime_seconds"] + 20,
        )
        while True:
            h.pulse()
            now = time.monotonic()
            if now - began > cfg["runtime_seconds"]:
                raise PipelineError("Bounded pilot deadline")
            if (attempt / "thermal-terminal.json").exists():
                terminal = load(attempt / "thermal-terminal.json")["state"]
                raise PipelineError("Adaptive safety stop")
            w = g.unit_state(work)
            guard = g.unit_state(watch)
            thermal = (
                load(attempt / "thermal-status.json")
                if (attempt / "thermal-status.json").exists()
                else None
            )
            if thermal:
                if (
                    not -0.001
                    <= (time.monotonic_ns() - thermal["heartbeat_monotonic_ns"]) / 1e9
                    <= 2
                ):
                    raise PipelineError("Independent watchdog heartbeat stale")
                if (attempt / "worker-status.json").exists():
                    (attempt / "start.allowed").touch()
            if (attempt / "worker-done.json").exists():
                if w["ActiveState"] == "failed":
                    raise PipelineError("Worker failed after marker")
                if (
                    w["SubState"] == "exited"
                    and w["ExecMainStatus"] == "0"
                    and (attempt / "thermal-report.json").exists()
                ):
                    assert load(attempt / "thermal-report.json")["state"] == "COMPLETED"
                    if mode == "prepare":
                        assert load(attempt / "control-probe.json")["state"] == "PASS"
                    terminal = "COMPLETED"
                    break
            else:
                if w["ActiveState"] == "failed" or w["SubState"] == "exited":
                    raise PipelineError("Worker exited before completion")
                if guard["ActiveState"] != "active" or guard["SubState"] != "running":
                    raise PipelineError("Independent watchdog service lost")
            if now - last_publish >= 0.25:
                status = (
                    load(attempt / "worker-status.json")
                    if (attempt / "worker-status.json").exists()
                    else {}
                )
                value = {
                    **status,
                    "state": "THERMAL_COOLDOWN" if thermal and thermal["paused"] else "RUNNING",
                    "run_id": run.name,
                    "mode": mode,
                    "last_heartbeat": time.time(),
                    "thermal": thermal,
                }
                atomic_json(attempt / "status.json", value)
                atomic_json(run / "status.json", value)
                last_publish = now
            time.sleep(0.1)
    except BaseException as exc:
        terminal = terminal or "FAILED"
        atomic_json(
            attempt / "failure.json",
            {"state": terminal, "error_type": type(exc).__name__, "reason": str(exc)},
        )
        raise
    finally:
        if terminal != "COMPLETED" and control is not None:
            control.stop()
        g.ctl("stop", watch, check=False)
        g.ctl("stop", work, check=False)
        h.close()
        result = {
            "state": terminal,
            "run_id": run.name,
            "mode": mode,
            "seconds": time.monotonic() - began,
            "evaluation": "NOT_RUN",
            "last_heartbeat": time.time(),
        }
        atomic_json(attempt / "result.json", result)
        atomic_json(attempt / "status.json", result)
        atomic_json(run / "status.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--mode", choices=["prepare", "train"], required=True)
    p.add_argument("--action", choices=["init", "worker", "supervise"], required=True)
    a = p.parse_args()
    os.umask(0o077)
    if a.action == "init":
        initialize(a.run.resolve(), a.mode)
    elif a.action == "worker":
        worker(a.run.resolve(), a.run.resolve() / "attempts" / a.mode, a.mode)
    else:
        supervise(a.run.resolve(), a.mode)

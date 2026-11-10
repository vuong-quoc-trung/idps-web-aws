#!/usr/bin/env python3
"""Authorized one-shot validation→one publisher training run; never evaluate/promote."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.final_release_validation import GateError, require, validate_release
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.checkpoint import RunLock, load_checkpoint
from idps_ai.training.student_publisher import initial_state, make_model, reload, save, update_once

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1"
OLD = REPO / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"
PILOT = (
    REPO
    / "ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1"
)
UNIT = "idps-final-local-publisher-200k-20261110-r1.service"
RUN_ID = "final-local-publisher-200k-20261110-r1"


class TrainingHeartbeat:
    def __init__(self, attempt):
        self.attempt = attempt
        self.value = {"state": "RUNNING", "phase": "WAITING_GUARD", "pid": os.getpid()}
        self.done = threading.Event()
        self.lock = threading.Lock()

    def write(self, **values):
        with self.lock:
            self.value.update(values)
            atomic_json(
                self.attempt / "worker-status.json",
                {
                    **self.value,
                    "last_heartbeat": time.time(),
                    "model_training": "RUNNING"
                    if self.value.get("optimizer_updates", 0)
                    else "NOT_STARTED",
                },
            )

    def loop(self):
        while not self.done.wait(0.5):
            self.write()


def load(p):
    return json.loads(Path(p).read_text())


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), Path(__file__).with_name(name)
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def code_hashes():
    paths = [Path(__file__), REPO / "ai-training/src/idps_ai/data/final_release_validation.py"]
    paths += [REPO / n for n in load(PILOT / "plan.json")["code_hashes"]]
    return {str(p.relative_to(REPO)): file_sha256(p) for p in paths}


def authorize(run):
    require(run.name == RUN_ID and not run.exists(), "ONE_FIXED_FRESH_RUN")
    run.mkdir(parents=True, mode=0o700)
    auth = {
        "authorization": "2026-11-10 explicit user one automatic data→training transition",
        "run_id": RUN_ID,
        "service": UNIT,
        "maximum_experiments": 1,
        "source_run": SOURCE.name,
        "final_config_sha256": file_sha256(SOURCE / "final-training-config.json"),
        "source_plan_sha256": file_sha256(SOURCE / "plan.json"),
        "code_hashes": code_hashes(),
        "evaluation_authorized": False,
        "promotion_authorized": False,
        "sealed_access": False,
    }
    auth["fingerprint"] = digest(auth)
    atomic_json(run / "authorization.json", auth)
    atomic_json(
        run / "handoff-status.json", {"state": "ARMED", "training": "NOT_STARTED", "run_id": RUN_ID}
    )


def bind_authorization(run):
    require(run.name == RUN_ID, "RUN_ID")
    auth = load(run / "authorization.json")
    c = dict(auth)
    require(
        c.pop("fingerprint") == digest(c) and auth["maximum_experiments"] == 1,
        "ONE_SHOT_AUTHORIZATION",
    )
    require(auth["code_hashes"] == code_hashes(), "TRAINING_CODE_BINDING")
    require(
        file_sha256(SOURCE / "final-training-config.json") == auth["final_config_sha256"],
        "AUTHORIZED_CONFIG_BINDING",
    )
    require(
        file_sha256(SOURCE / "plan.json") == auth["source_plan_sha256"], "AUTHORIZED_DATA_BINDING"
    )
    return auth


def build_plan(run, checked, cfg, eligible):
    data = run / "data"
    data.mkdir(exist_ok=True)
    for name, sha in cfg["data_files"].items():
        target = data / name
        if not target.exists():
            shutil.copyfile(SOURCE / "final-data" / name, target.with_suffix(".copying"))
            require(file_sha256(target.with_suffix(".copying")) == sha, "COPIED_DATA_HASH")
            target.with_suffix(".copying").replace(target)
        require(file_sha256(target) == sha, "TRAINING_DATA_HASH")
    with np.load(data / "train.npz", allow_pickle=False) as z:
        y = z["y"].copy()
    model = make_model(y, 17)
    controls = {}
    manifest = load(data / "split.json")
    for key in ["window", "body"]:
        bins = {}
        for m in manifest:
            if m["role"] != "TRAIN":
                continue
            src = eligible[m["row"]]
            value = (
                str(int(src["source_row"] >= 1048576))
                if key == "window"
                else src["body_observation"]
            )
            bins.setdefault(value, [0, 0])[m["target"]] += 1
        controls[key] = bins
    plan = {
        "run_id": RUN_ID,
        "task": "publisher_anomaly",
        "feature_contract": cfg["feature_contract"],
        "dataset_fingerprint": cfg["dataset_fingerprint"],
        "split_fingerprint": cfg["split_fingerprint"],
        "final_config_fingerprint": cfg["fingerprint"],
        "source_run": SOURCE.name,
        "training_examples": len(y),
        "split_counts": cfg["split_counts"],
        "seed": 17,
        "epochs": 10,
        "batch_size": 64,
        "learning_rate": 0.001,
        "planned_steps": cfg["planned_steps"],
        "checkpoint_interval": 16,
        "architecture": model.metadata(),
        "parameters": 50696,
        "initial_weights_sha": digest(
            {k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in model.parameters.items()}
        ),
        "code_hashes": code_hashes(),
        "data_files": cfg["data_files"],
        "majority_baseline": {
            "class": int(np.argmax(np.bincount(y, minlength=2))),
            "anomaly_prior": float(np.mean(y)),
        },
        "shortcut_baselines_TRAIN_only": controls,
        "evaluation_protocol": cfg["evaluation"],
        "validation_fingerprint": checked["fingerprint"],
        "initialization": "fresh seed17; no teacher weights/optimizer",
        "selection": "final fixed budget only",
        "evaluation": "NOT_RUN_USER_RETURN_REQUIRED",
        "promotion": False,
    }
    plan["fingerprint"] = digest(plan)
    if (run / "plan.json").exists():
        require(load(run / "plan.json") == plan, "RESUME_PLAN_CHANGED")
    else:
        atomic_json(run / "plan.json", plan)
    return plan


def bind_plan(plan):
    c = dict(plan)
    require(
        c.pop("fingerprint") == digest(c) and plan["code_hashes"] == code_hashes(),
        "TRAINING_PLAN_BINDING",
    )
    return plan


def actual_prepare(run, plan, status):
    with np.load(run / "data/train.npz", allow_pickle=False) as z:
        x, y, groups = z["x"].copy(), z["y"].copy(), z["groups"].copy()
    if not (run / "model/latest.json").exists():
        # No committed optimizer update can exist before this generation0 pointer.
        model = make_model(y, 17)
        state, order = initial_state(model, groups, plan)
        save(run, model, state, order)
    loaded = load_checkpoint(run / "model")
    require(not loaded.used_previous, "LATEST_CHECKPOINT_INTEGRITY")
    model, state, order, checkpoint = reload(run, plan, len(y))
    if model.steps == 0:
        order = update_once(model, state, order, x, y, groups, plan)
        save(run, model, state, order)
    if model.steps == 1:
        restored, rs, ro, checkpoint = reload(run, plan, len(y))
        require(
            all(np.array_equal(v, restored.arrays()[k]) for k, v in model.arrays().items()),
            "STEP1_RELOAD",
        )
        control_state = copy.deepcopy(state)
        control_order = update_once(model, control_state, order.copy(), x, y, groups, plan)
        ro = update_once(restored, rs, ro, x, y, groups, plan)
        require(
            all(np.array_equal(v, restored.arrays()[k]) for k, v in model.arrays().items()),
            "NEXT_UPDATE_ADAM_WEIGHTS",
        )
        # Generation metadata reflects the checkpoint just loaded; model arrays
        # above validate the updated model. Compare actual continuation state.
        compared = {
            k: v for k, v in control_state.items() if k not in {"model", "checkpoint_format"}
        }
        require(
            compared == {k: rs[k] for k in compared} and np.array_equal(control_order, ro),
            "NEXT_UPDATE_RNG_CURSOR",
        )
        # Persist proof before committing step2, so an interrupted handoff can
        # repeat from its last committed step1 without losing proof provenance.
        atomic_json(
            run / "actual-preflight.json",
            {
                "state": "PASS",
                "actual_committed_updates_target": 2,
                "checkpoint_step1_reload_exact": True,
                "next_update_parameters_Adam_RNG_cursor_exact": True,
                "calibration_evaluation_gradient_rows": 0,
                "training_examples": len(y),
                "dataset_fingerprint": plan["dataset_fingerprint"],
            },
        )
        save(run, restored, rs, ro)
        model, state, order = restored, rs, ro
    require(
        model.steps >= 2 and load(run / "actual-preflight.json")["state"] == "PASS",
        "ACTUAL_PREFLIGHT",
    )
    atomic_json(run / "loss-history.json", state["losses"])
    status(
        phase="ACTUAL_PREFLIGHT_VERIFIED",
        optimizer_updates=model.steps,
        planned_steps=plan["planned_steps"],
        checkpoint=str(run / "model/latest.json"),
    )


def worker(run, attempt):
    bind_authorization(run)
    with RunLock(OLD.parent / "student-pipeline-global"), RunLock(run / "trainer.lock"):
        hb = TrainingHeartbeat(attempt)
        hb.write()
        thread = threading.Thread(target=hb.loop, daemon=True)
        thread.start()
        try:
            until = time.monotonic() + 20
            while not (attempt / "start.allowed").exists():
                require(time.monotonic() < until, "WATCHDOG_START_TIMEOUT")
                time.sleep(0.1)
            checked, cfg, eligible = validate_release(SOURCE, REPO, OLD, PILOT, hb.write)
            atomic_json(run / "validation.json", checked)
            plan = build_plan(run, checked, cfg, eligible)
            del eligible
            atomic_json(
                run / "handoff-status.json",
                {
                    "state": "TRIGGERED",
                    "training_readiness": "PASS",
                    "training": "NOT_STARTED",
                    "phase": "ACTUAL_PREFLIGHT",
                    "run_id": RUN_ID,
                    "dataset_fingerprint": cfg["dataset_fingerprint"],
                    "training_examples": plan["training_examples"],
                },
            )
            actual_prepare(run, plan, hb.write)
            atomic_json(
                run / "handoff-status.json",
                {
                    "state": "TRIGGERED",
                    "training_readiness": "PASS",
                    "training": "RUNNING",
                    "run_id": RUN_ID,
                    "training_examples": plan["training_examples"],
                    "actual_updates_verified": load(run / "model/latest.json")["global_step"],
                },
            )
            runner = module("student-publisher-pilot.py")
            runner.bind = bind_plan
            runner.train(run, attempt, hb.write)
            hb.write(state="COMPLETED", phase="FINAL_CHECKPOINT_VERIFIED_NO_EVALUATION")
            atomic_json(attempt / "worker-done.json", {"state": "COMPLETED"})
        except BaseException as exc:
            gate = exc.gate if isinstance(exc, GateError) else type(exc).__name__
            atomic_json(
                run / "gate-failure.json",
                {"gate": gate, "phase": hb.value.get("phase"), "checkpoint_preserved": True},
            )
            hb.write(state="FAILED", failing_gate=gate)
            raise
        finally:
            hb.done.set()
            thread.join()


def orchestrate(run):
    if (run / "terminal.json").exists():
        return
    with RunLock(run / "one-shot-lock"):
        bind_authorization(run)
        if (run / "terminal.json").exists():
            return
        # Never start against an active producer or another training scope.
        helpers = module("student-data-recovery.py")
        g = helpers.guard_module()
        for p in (
            sorted((run / "attempts").glob("*/services.json"))
            if (run / "attempts").exists()
            else []
        ):
            services = load(p)
            for key in ["worker_unit", "watchdog_unit"]:
                info = g.unit_state(services[key])
                require(
                    info["SubState"] not in ["running", "start"],
                    "PREVIOUS_SUPERVISION_STILL_ACTIVE",
                )
            require(
                not (p.parent / "thermal-terminal.json").exists(),
                "PREVIOUS_SAFETY_STOP_REQUIRES_REVIEW",
            )
        count = len(list((run / "attempts").glob("train-*"))) if (run / "attempts").exists() else 0
        mode = f"train-{count + 1:02d}"
        attempt = run / "attempts" / mode
        attempt.mkdir(parents=True, exist_ok=False)
        hardware = hardware_snapshot()
        sensor = SensorReader(hardware).read(time.monotonic())
        require(
            sensor["temperature_C"] < 75 and not sensor["hardware_emergency"],
            "START_THERMAL_HEADROOM",
        )
        atomic_json(attempt / "hardware.json", hardware)
        atomic_json(
            attempt / "recovery-plan.json",
            {
                "original_run_id": RUN_ID,
                "preflight": False,
                "code_hashes": code_hashes(),
                "warning_C": 85,
                "throttle_C": 90,
                "strong_throttle_C": 93,
                "cooldown_seconds": 15,
                "maximum_cooldown_seconds": 300,
                "runtime_seconds": 7200,
                "effective_emergency_C": hardware["effective_emergency_C"],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            },
        )
        atomic_json(run / "active-attempt.json", {"attempt": mode, "path": str(attempt)})
        atomic_json(
            run / "launch-marker.json",
            {
                "state": "LAUNCH_COMMITTED",
                "run_id": RUN_ID,
                "attempt": mode,
                "same_experiment_resume": count > 0,
            },
        )
        try:
            # Reuse the proven supervisor, quota controller, independent watchdog,
            # heartbeat/status writer and cleanup. Only route its worker entrypoint.
            runner = module("student-publisher-pilot.py")
            runner.__file__ = __file__
            runner.code_hashes = code_hashes
            runner.supervise(run, mode)
            require(
                load(run / "training-completion.json")["state"] == "COMPLETED",
                "TRAINING_COMPLETION",
            )
            final = load_checkpoint(run / "model")
            require(
                final.model.steps == load(run / "plan.json")["planned_steps"], "FINAL_STEP_BUDGET"
            )
            value = {
                "state": "COMPLETED",
                "training": "COMPLETED",
                "run_id": RUN_ID,
                "optimizer_updates": final.model.steps,
                "evaluation": "NOT_RUN_USER_RETURN_REQUIRED",
            }
        except BaseException as exc:
            validation_passed = (run / "validation.json").exists()
            value = {
                "state": "FAILED" if validation_passed else "BLOCKED",
                "training": "FAILED" if (run / "model/latest.json").exists() else "NOT_STARTED",
                "training_readiness": "PASS" if validation_passed else "BLOCKED",
                "run_id": RUN_ID,
                "gate": load(run / "gate-failure.json")
                if (run / "gate-failure.json").exists()
                else type(exc).__name__,
                "checkpoint_preserved": True,
            }
        atomic_json(run / "terminal.json", value)
        atomic_json(run / "handoff-status.json", value)
        # Terminal states are permanent decisions, never a launch/retry trigger.
        subprocess.run(
            ["systemctl", "--user", "disable", UNIT], capture_output=True, timeout=10, check=False
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--action", choices=["authorize", "supervise", "worker"], required=True)
    p.add_argument("--mode")
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        if a.action == "authorize":
            authorize(a.run.resolve())
        elif a.action == "worker":
            require(a.mode is not None, "ATTEMPT_REQUIRED")
            worker(a.run.resolve(), a.run.resolve() / "attempts" / a.mode)
        else:
            try:
                orchestrate(a.run.resolve())
            except GateError as exc:
                if a.run.name == RUN_ID and not (a.run / "terminal.json").exists():
                    value = {
                        "state": "BLOCKED",
                        "training": "NOT_STARTED",
                        "gate": exc.gate,
                        "checkpoint_preserved": True,
                    }
                    atomic_json(a.run / "terminal.json", value)
                    atomic_json(a.run / "handoff-status.json", value)
                    subprocess.run(
                        ["systemctl", "--user", "disable", UNIT],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                raise

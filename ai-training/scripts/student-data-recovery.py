#!/usr/bin/env python3
"""Resume the immutable student frame using a separately bound adaptive attempt."""

import argparse
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.checkpoint import RunLock
from idps_ai.training.heartbeat import SupervisorHeartbeat

REPO = Path(__file__).resolve().parents[2]
ORIGINAL = Path(__file__).with_name("student-data-pipeline.py")
GUARD = Path(__file__).with_name("adaptive-thermal-guard.py")
FINALIZE = Path(__file__).with_name("student-finalize.py")


def load(path):
    return json.loads(Path(path).read_text())


def guard_module():
    spec = importlib.util.spec_from_file_location("adaptive_guard", GUARD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cursor(output):
    p = output / "index.sqlite"
    if not p.exists():
        return 0
    with sqlite3.connect(f"file:{p}?mode=ro", uri=True) as db:
        n, upper, unique = db.execute(
            'SELECT count(*),coalesce(max(i)+1,0),count(DISTINCT s||":"||n) FROM r'
        ).fetchone()
        if n != upper or n != unique:
            raise PipelineError("Committed source cursor inconsistent")
        return n


def status_cursor(output):
    # A frozen SQLite writer can retain an exclusive lock. Monitoring must not
    # wait on its DB or mistake an intentional pause for monitor-heartbeat loss.
    path = output / "progress.json"
    return load(path)["rows_committed"] if path.exists() else 0


def pending_boundaries(value, stops=(4096, 100000)):
    if not 0 <= value <= 100000:
        raise PipelineError("Resume cursor out of fixed frame")
    return [stop for stop in stops if value < stop]


def code_binding():
    return {
        str(p.relative_to(REPO)): file_sha256(p)
        for p in [
            Path(__file__),
            GUARD,
            FINALIZE,
            REPO / "ai-training/src/idps_ai/training/adaptive_thermal.py",
            REPO / "ai-training/src/idps_ai/training/heartbeat.py",
            REPO / "ai-training/src/idps_ai/data/resumable_near.py",
        ]
    }


def initialize(root, attempt, preflight, preflight_proof=None):
    assert not attempt.exists(), "Never overwrite an attempt"
    assert cursor(root / "materialized") == 100000
    assert load(root / "plan.json")["candidate_positions"] == 100000
    hardware = hardware_snapshot()
    first = SensorReader(hardware).read(time.monotonic())
    if first["temperature_C"] >= 75 or first["hardware_emergency"]:
        raise PipelineError("Insufficient cool headroom for recovery preflight")
    if not preflight:
        assert preflight_proof is not None, "Supply the verified preflight attempt"
        proof = load(preflight_proof / "result.json")
        assert load(preflight_proof / "recovery-plan.json")["code_hashes"] == code_binding()
        assert proof["state"] == "COMPLETED" and proof["preflight"] is True
        assert load(preflight_proof / "integrity.json")["state"] == "PASS"
        assert load(preflight_proof / "control-probe.json")["state"] == "PASS"
    attempt.mkdir(parents=True, mode=0o700)
    (attempt / "history").mkdir()
    for name in ["status.json", "supervisor-result.json"]:
        if (root / name).exists():
            shutil.copyfile(root / name, attempt / "history" / name)
    atomic_json(attempt / "hardware.json", hardware)
    if (root / "materialized/near-progress.json").exists():
        shutil.copyfile(
            root / "materialized/near-progress.json", attempt / "history/legacy-near-progress.json"
        )
    plan = {
        "version": "student-finalization-recovery-v2",
        "original_run_id": root.name,
        "attempt_id": attempt.name,
        "original_plan_fingerprint": load(root / "plan.json")["fingerprint"],
        "original_plan_sha256": file_sha256(root / "plan.json"),
        "resume_cursor": 100000,
        "preflight": preflight,
        "preflight_proof": str(preflight_proof) if preflight_proof else None,
        "code_hashes": code_binding(),
        "hardware_sha256": file_sha256(attempt / "hardware.json"),
        "dataset_frame_changed": False,
        "quota_ceiling_percent_one_cpu": 20,
        "memory_cap_GiB": 8,
        "reserve_GiB": 4,
        "warning_C": 85,
        "throttle_C": 90,
        "strong_throttle_C": 93,
        "effective_emergency_C": hardware["effective_emergency_C"],
        "cooldown_seconds": 15,
        "maximum_cooldown_seconds": 300,
        "runtime_seconds": 180 if preflight else 10800,
        "model_training": "NOT_STARTED",
        "source_ingestion": "DISABLED; rebuild from committed normalized metadata and immutable feature copies",
        "legacy_near_cursor": "NOT_RESUMABLE; no accumulator; new audit begins at0 exactly once",
    }
    plan["fingerprint"] = digest(plan)
    atomic_json(attempt / "recovery-plan.json", plan)
    print(
        json.dumps(
            {
                "state": "PREPARED",
                "attempt": str(attempt),
                "fingerprint": plan["fingerprint"],
                "effective_emergency_C": plan["effective_emergency_C"],
            }
        )
    )


def verify_binding(root, attempt):
    plan = load(attempt / "recovery-plan.json")
    check = dict(plan)
    fp = check.pop("fingerprint")
    assert digest(check) == fp
    assert code_binding() == plan["code_hashes"]
    assert file_sha256(root / "plan.json") == plan["original_plan_sha256"]
    assert load(root / "plan.json")["fingerprint"] == plan["original_plan_fingerprint"]
    assert file_sha256(attempt / "hardware.json") == plan["hardware_sha256"]
    return plan


def integrity(root, attempt):
    # This runs only inside the capped, monitored worker, with no dataset writes.
    import numpy as np

    spec = importlib.util.spec_from_file_location("original_student_pipeline", ORIGINAL)
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    plan = pipeline.verify(root)
    dbpath = root / "materialized/index.sqlite"
    if Path(str(dbpath) + "-journal").exists():
        raise PipelineError("Journal recovery needs separate explicit diagnosis")
    shards = {}
    used = {}
    with sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM student").fetchone()[0] == cursor(
            root / "materialized"
        )
        for (sj,) in db.execute("SELECT j FROM student ORDER BY i"):
            m = json.loads(sj)
            ref = m["feature_ref"]
            if ref:
                used.setdefault(ref["shard"], []).append(ref["slot"])
    for name, slots in used.items():
        p = root / "materialized" / name
        with np.load(p, allow_pickle=False) as z:
            x = z["x"]
            assert (
                x.ndim == 2 and x.shape[1] == 588 and x.dtype == np.float32 and np.isfinite(x).all()
            )
            assert min(slots) >= 0 and max(slots) < len(x)
        shards[name] = file_sha256(p)
    present = {
        str(p.relative_to(root / "materialized"))
        for p in (root / "materialized/features").glob("*.npz")
    }
    assert present == set(used) and not list((root / "materialized").rglob("*.writing"))
    return {
        "state": "PASS",
        "cursor": cursor(root / "materialized"),
        "committed_shards": len(shards),
        "shard_hashes": shards,
        "original_plan_fingerprint": plan["fingerprint"],
        "source_bindings": "PASS",
        "old_code_policy_key": "PASS",
        "no_source_coordinate_duplicates": True,
        "partial_or_orphan_files": 0,
        "model_training": "NOT_STARTED",
    }


class WorkerHeartbeat:
    def __init__(self, attempt):
        self.attempt = attempt
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.value = {"state": "RUNNING", "phase": "WAITING_FOR_GUARD"}

    def write(self, **kw):
        with self.lock:
            self.value.update(kw)
            atomic_json(
                self.attempt / "worker-status.json",
                {
                    **self.value,
                    "last_heartbeat": time.time(),
                    "pid": os.getpid(),
                    "model_training": "NOT_STARTED",
                },
            )

    def loop(self):
        while not self.done.wait(1):
            self.write()


def worker(root, attempt):
    plan = verify_binding(root, attempt)
    with RunLock(root.parent / "student-pipeline-global"), RunLock(root / "orchestrator.lock"):
        hb = WorkerHeartbeat(attempt)
        hb.write()
        thread = threading.Thread(target=hb.loop, daemon=True)
        thread.start()
        try:
            end = time.monotonic() + 20
            while not (attempt / "start.allowed").exists():
                if time.monotonic() > end:
                    raise PipelineError("Independent guard start timeout")
                time.sleep(0.1)
            hb.write(phase="INTEGRITY")
            checked = integrity(root, attempt)
            assert checked["cursor"] == plan["resume_cursor"]
            atomic_json(attempt / "integrity.json", checked)
            if plan["preflight"]:
                hb.write(phase="PREFLIGHT_READ_ONLY")
                subprocess.run(
                    [
                        sys.executable,
                        str(FINALIZE),
                        "--root",
                        str(root),
                        "--attempt",
                        str(attempt),
                        "--action",
                        "benchmark",
                    ],
                    check=True,
                )
                # Keep the actual controller probe bounded and unheated.
                until = time.monotonic() + 3
                while time.monotonic() < until:
                    for name in list(checked["shard_hashes"])[:3]:
                        assert (
                            file_sha256(root / "materialized" / name)
                            == checked["shard_hashes"][name]
                        )
                    time.sleep(0.1)
                atomic_json(
                    attempt / "worker-result.json",
                    {
                        "state": "COMPLETED",
                        "preflight": True,
                        "cursor_unchanged": cursor(root / "materialized") == 100000,
                    },
                )
            else:
                command = [sys.executable, str(FINALIZE), "--root", str(root)]
                assert cursor(root / "materialized") == 100000
                for name in ["materialized", "rebuild"]:
                    output = root / name
                    if name == "rebuild":
                        hb.write(phase="REBUILD_DERIVATIVE_NO_SOURCE_INGESTION")
                        subprocess.run(
                            [*command, "--action", "clone", "--output", str(output)], check=True
                        )
                    hb.write(phase="FINALIZE_" + name)
                    subprocess.run(
                        [*command, "--action", "finish", "--output", str(output)], check=True
                    )
                a = load(root / "materialized/summary.json")
                b = load(root / "rebuild/summary.json")
                assert a == b
                for name in ["ledger.jsonl", "training-index.jsonl"]:
                    assert file_sha256(root / "materialized" / name) == file_sha256(
                        root / "rebuild" / name
                    )
                one = sorted((root / "materialized/features").glob("*.npz"))
                two = sorted((root / "rebuild/features").glob("*.npz"))
                assert len(one) == len(two) and all(
                    x.name == y.name and file_sha256(x) == file_sha256(y)
                    for x, y in zip(one, two, strict=True)
                )
                for name, sha in checked["shard_hashes"].items():
                    assert file_sha256(root / "materialized" / name) == sha
                assert cursor(root / "materialized") == cursor(root / "rebuild") == 100000
                result = {
                    "state": "COMPLETED",
                    "run_id": root.name,
                    "attempt_id": attempt.name,
                    "summary": a,
                    "original_plan_fingerprint": plan["original_plan_fingerprint"],
                    "resume_from": 100000,
                    "old_shards_unchanged": True,
                    "actual_cross_process_resume": True,
                    "deterministic_rebuild": True,
                    "rebuild_scope": "normalized metadata, exact graph, independently counted near pairs, finalized ledgers and bytecopied features; raw-source feature extraction NOT repeated",
                    "feature_shards_byte_identical": True,
                    "same_candidate_positions": 100000,
                    "new_source_positions": 0,
                    "model_training": "NOT_STARTED",
                    "resource_report": str((attempt / "thermal-report.json").relative_to(root)),
                }
                atomic_json(root / "completion.json", result)
                atomic_json(attempt / "worker-result.json", result)
            hb.write(state="COMPLETED", phase="VERIFIED")
            atomic_json(attempt / "worker-done.json", {"state": "COMPLETED"})
        except BaseException as exc:
            hb.write(state="FAILED", error_type=type(exc).__name__)
            raise
        finally:
            hb.done.set()
            thread.join()


def start_service(unit, command, log, *, quota, memory, runtime, affinity=False):
    args = [
        "systemd-run",
        "--user",
        "--quiet",
        "--unit",
        unit,
        "--service-type=exec",
        "--working-directory",
        str(REPO),
        "-p",
        f"CPUQuota={quota}%",
        "-p",
        "CPUQuotaPeriodSec=10ms",
        "-p",
        f"MemoryMax={memory}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "TasksMax=64",
        "-p",
        "KillMode=control-group",
        "-p",
        "TimeoutStopSec=2",
        "-p",
        f"RuntimeMaxSec={runtime}",
        "-p",
        "RemainAfterExit=yes",
        "-p",
        "Nice=10",
        "-p",
        f"StandardOutput=append:{log}",
        "-p",
        f"StandardError=append:{log}",
    ]
    if affinity:
        args += ["-p", "CPUAffinity=0-7"]
    for key in [
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "PYTHONDONTWRITEBYTECODE",
    ]:
        args += ["--setenv", key + "=1"]
    subprocess.run([*args, *command], check=True, timeout=10, capture_output=True)


def supervise(root, attempt):
    plan = verify_binding(root, attempt)
    g = guard_module()
    token = str(os.getpid()) + "-" + str(time.time_ns())[-6:]
    workunit = "idps-student-adaptive-work-" + token + ".service"
    watchunit = "idps-student-adaptive-watch-" + token + ".service"
    began = time.monotonic()
    work_started = False
    guard_started = False
    terminal = None
    last_status = 0
    last_sample = None
    completion_wait = None
    supervisor_heartbeat = None
    with RunLock(root.parent / "student-recovery-launcher"):
        try:
            vm = __import__("psutil").virtual_memory()
            cap = int(
                min(
                    8 * 1024**3,
                    vm.available - 4 * 1024**3,
                    30_000_000_000 - (vm.total - vm.available) - 4 * 1024**3,
                )
            )
            if cap < 1024**3:
                raise PipelineError("Shared RAM reserve unavailable")
            supervisor_heartbeat = SupervisorHeartbeat(attempt / "supervisor-heartbeat.json")
            supervisor_heartbeat.start_writer()
            start_service(
                workunit,
                [
                    sys.executable,
                    str(Path(__file__)),
                    "--root",
                    str(root),
                    "--attempt",
                    str(attempt),
                    "--action",
                    "worker",
                ],
                attempt / "worker.log",
                quota=20,
                memory=cap,
                runtime=plan["runtime_seconds"] + 10,
                affinity=True,
            )
            work_started = True
            c = g.CgroupControl(workunit)
            assert (c.path / "memory.swap.max").read_text().strip() == "0"
            atomic_json(
                attempt / "services.json",
                {
                    "worker_unit": workunit,
                    "watchdog_unit": watchunit,
                    "supervisor_pid": os.getpid(),
                    "memory_cap_bytes": cap,
                    "CPU_ceiling_percent_one_cpu": 20,
                    "worker_cgroup": str(c.path),
                },
            )
            watchcmd = [sys.executable, str(GUARD), "--attempt", str(attempt), "--unit", workunit]
            if plan["preflight"]:
                watchcmd += ["--probe-controls"]
            start_service(
                watchunit,
                watchcmd,
                attempt / "watchdog.log",
                quota=20,
                memory="256M",
                runtime=plan["runtime_seconds"] + 20,
            )
            guard_started = True
            while True:
                supervisor_heartbeat.pulse()
                now = time.monotonic()
                if now - began > plan["runtime_seconds"]:
                    raise PipelineError("Bounded attempt deadline exceeded")
                watch = g.unit_state(watchunit)
                work = g.unit_state(workunit)
                if (attempt / "thermal-terminal.json").exists():
                    terminal = load(attempt / "thermal-terminal.json")["state"]
                    raise PipelineError(
                        "Adaptive safety stop; exact reason in thermal-terminal.json"
                    )
                thermal = (
                    load(attempt / "thermal-status.json")
                    if (attempt / "thermal-status.json").exists()
                    else None
                )
                if thermal:
                    last_sample = thermal
                    if (
                        not -0.001
                        <= (time.monotonic_ns() - thermal["heartbeat_monotonic_ns"]) / 1e9
                        <= 2
                    ):
                        terminal = "WATCHDOG_FAILURE"
                        raise PipelineError("Independent controller heartbeat stale")
                    if (
                        not (attempt / "start.allowed").exists()
                        and (attempt / "worker-status.json").exists()
                    ):
                        (attempt / "start.allowed").touch()
                if (attempt / "worker-done.json").exists():
                    if work["ActiveState"] == "failed":
                        raise PipelineError("Worker failed after writing completion marker")
                    if completion_wait is None:
                        completion_wait = now
                    if (
                        work["ActiveState"] != "active"
                        or work["SubState"] != "exited"
                        or work.get("ExecMainStatus") != "0"
                    ):
                        if now - completion_wait < 10:
                            time.sleep(0.1)
                            continue
                        raise PipelineError("Worker completion exit not verified")
                    if (attempt / "thermal-report.json").exists() and watch["SubState"] == "exited":
                        assert load(attempt / "thermal-report.json")["state"] == "COMPLETED"
                        if plan["preflight"]:
                            assert load(attempt / "control-probe.json")["state"] == "PASS"
                        terminal = "COMPLETED"
                        break
                else:
                    if watch["ActiveState"] != "active" or watch["SubState"] != "running":
                        terminal = "WATCHDOG_FAILURE"
                        raise PipelineError("Independent controller service unavailable")
                    if work["ActiveState"] == "failed" or work["SubState"] == "exited":
                        terminal = "FAILED"
                        raise PipelineError("Worker exited without verified completion")
                if now - last_status >= 0.5:
                    worker_status = (
                        load(attempt / "worker-status.json")
                        if (attempt / "worker-status.json").exists()
                        else {}
                    )
                    state = "THERMAL_COOLDOWN" if thermal and thermal["paused"] else "RUNNING"
                    value = {
                        **worker_status,
                        "state": state,
                        "run_id": root.name,
                        "attempt_id": attempt.name,
                        "last_heartbeat": time.time(),
                        "thermal_state": thermal["state"] if thermal else "STARTING_GUARD",
                        "thermal": thermal,
                        "resume_cursor": 100000,
                        "current_cursor": status_cursor(root / "materialized"),
                    }
                    atomic_json(attempt / "status.json", value)
                    if not plan["preflight"]:
                        atomic_json(root / "status.json", value)
                    last_status = now
                time.sleep(0.1)
        except BaseException as exc:
            if terminal is None:
                terminal = "FAILED"
            atomic_json(
                attempt / "failure.json",
                {
                    "state": terminal,
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                    "time": time.time(),
                },
            )
            raise
        finally:
            if supervisor_heartbeat is not None:
                supervisor_heartbeat.close()
            if terminal != "COMPLETED" and work_started:
                try:
                    g.CgroupControl(workunit).stop()
                except Exception:
                    g.ctl("stop", workunit, check=False)
            # Watchdog retains independent fail-stop protection if this supervisor disappears.
            if guard_started:
                g.ctl("stop", watchunit, check=False)
            value = {
                "state": terminal,
                "run_id": root.name,
                "attempt_id": attempt.name,
                "preflight": plan["preflight"],
                "last_heartbeat": time.time(),
                "resume_cursor": 100000,
                "current_cursor": status_cursor(root / "materialized"),
                "last_thermal": last_sample,
                "seconds": time.monotonic() - began,
                "model_training": "NOT_STARTED",
            }
            atomic_json(attempt / "status.json", value)
            atomic_json(attempt / "result.json", value)
            if not plan["preflight"]:
                atomic_json(root / "status.json", value)
            if work_started:
                g.ctl("stop", workunit, check=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--attempt", type=Path, required=True)
    p.add_argument("--action", choices=["init", "supervise", "worker"], required=True)
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--preflight-proof", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.action == "init":
        initialize(a.root.resolve(), a.attempt.resolve(), a.preflight, a.preflight_proof)
    elif a.action == "worker":
        worker(a.root.resolve(), a.attempt.resolve())
    else:
        supervise(a.root.resolve(), a.attempt.resolve())

"""Bounded systemd user runner for trusted, local CPU workloads."""

import argparse
import errno
import fcntl
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, digest
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.heartbeat import process_identity
from idps_ai.training.resource_contract import (
    GIB,
    MIB,
    PHASES,
    HostBudget,
    ResourceController,
    ResourceSample,
    plan_resources,
    resume_gate,
    verify_containment,
)
from idps_ai.training.thermal_policy import admission, quota_for_state

CGROUP = Path("/sys/fs/cgroup")
CPU_DOMAINS = {"TCPU", "x86_pkg_temp", "TCPU_PCI"}
MODULE = "idps_ai.training.resource_adapter"
RUNTIME_CGROUP_FILES = frozenset(
    {
        "cpu.max",
        "memory.max",
        "memory.high",
        "memory.swap.max",
        "pids.max",
        "cpuset.cpus.effective",
        "cgroup.events",
        "cgroup.procs",
        "memory.events",
        "memory.current",
        "pids.events",
    }
)


def systemctl(*args):
    return subprocess.run(
        ["systemctl", "--user", *args], check=True, capture_output=True, text=True, timeout=2
    ).stdout


def properties(*args):
    return dict(line.split("=", 1) for line in systemctl("show", *args).splitlines() if "=" in line)


def counters(path):
    return {k: int(v) for k, v in (line.split() for line in path.read_text().splitlines())}


def cgroup_of(pid):
    return Path(f"/proc/{pid}/cgroup").read_text().strip().removeprefix("0::")


def start_unit(name, command, *, settings, wait=False):
    args = [
        "systemd-run",
        "--user",
        "--quiet",
        "--expand-environment=no",
        "--unit",
        name,
        "--service-type=exec",
    ]
    if wait:
        args.extend(("--wait", "--collect"))
    for key, value in settings.items():
        args.extend(("-p", f"{key}={value}"))
    return subprocess.run(
        [*args, "--", *command], check=not wait, timeout=None if wait else 5
    ).returncode


def common_limits(cpu_percent, memory, tasks, runtime):
    return {
        "Slice": "app.slice",
        "CPUQuota": f"{cpu_percent:.2f}%",
        "CPUQuotaPeriodSec": "100ms",
        "MemoryMax": memory,
        "MemoryHigh": memory * 4 // 5,
        "MemorySwapMax": 0,
        "TasksMax": tasks,
        "KillMode": "control-group",
        "Restart": "no",
        "Delegate": "no",
        "NoNewPrivileges": "yes",
        "TimeoutStopSec": "1s",
        "RuntimeMaxSec": f"{runtime}s",
    }


class OwnedWorker:
    """The caller creates a fresh nonce-named unit and pins its invocation."""

    def __init__(self, token, manager_group):
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise PipelineError("Invalid generated attempt token")
        self.unit = f"idps-t031-worker-{token}.service"
        self.description = f"AI-IDPS resource attempt {token}"
        self.group = f"{manager_group}/app.slice/{self.unit}"
        self.path = CGROUP / self.group.lstrip("/")
        self.invocation = None
        self.inode = None

    def owned(self, *, allow_empty=False):
        info = properties(self.unit)
        if (
            info["Id"] != self.unit
            or info["Transient"] != "yes"
            or info["Description"] != self.description
            or (info.get("ControlGroup") or "")
            not in ({self.group, ""} if allow_empty and not self.path.exists() else {self.group})
            or not re.fullmatch(r"[0-9a-f]{32}", info["InvocationID"])
        ):
            raise PipelineError("Worker ownership could not be established")
        if self.invocation is not None and info["InvocationID"] != self.invocation:
            raise PipelineError("Worker invocation changed")
        if self.inode is not None:
            try:
                inode = self.path.stat().st_ino
            except FileNotFoundError:
                if not allow_empty:
                    raise
            else:
                if inode != self.inode:
                    raise PipelineError("Worker cgroup identity changed")
        return info

    def pin(self):
        info = self.owned()
        pid = int(info["MainPID"])
        identity = process_identity(pid)
        if (
            identity is None
            or cgroup_of(pid) != self.group
            or info["Delegate"] != "no"
            or info["NoNewPrivileges"] != "yes"
            or info["ProtectControlGroups"] != "yes"
        ):
            raise PipelineError("Barrier process or unit isolation could not be verified")
        self.invocation = info["InvocationID"]
        self.inode = self.path.stat().st_ino
        return info, pid, identity

    def exit_info(self, pid, started_at):
        """Read the registered main process's exit from the pinned invocation."""
        if self.invocation is None or self.inode is None or process_identity(pid) is not None:
            raise PipelineError("Worker exit or PID identity could not be verified")
        info = self.owned(allow_empty=True)
        if (
            info["ExecMainPID"] != str(pid)
            or info["ExecMainStartTimestampMonotonic"] != started_at
            or int(started_at) <= 0
        ):
            raise PipelineError("Worker exit does not match the registered main process")
        if info["SubState"] == "running" and info["MainPID"] == str(pid):
            return None  # The service manager has not reaped the worker yet.
        code = int(info["ExecMainCode"])
        if (
            info["MainPID"] != "0"
            or int(info["ExecMainExitTimestampMonotonic"]) < int(started_at)
            or code not in {os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED}
            or not 0 <= int(info["ExecMainStatus"]) <= 255
            or not info["Result"]
        ):
            raise PipelineError("Worker exit status could not be verified")
        if info["Result"] == "success" and (
            (info["ActiveState"], info["SubState"]) != ("active", "exited")
            or code != os.CLD_EXITED
            or info["ExecMainStatus"] != "0"
        ):
            raise PipelineError("Worker did not reach a verified successful exit")
        return info

    def limits(self, info, cpus, quota, memory, tasks):
        if self.path.stat().st_ino != self.inode:
            raise PipelineError("Worker cgroup replaced")
        files = ("cpu.max", "memory.max", "memory.high", "memory.swap.max", "pids.max")
        limits = {key: (self.path / key).read_text().strip() for key in files}
        effective = self.path / "cpuset.cpus.effective"
        if effective.exists():
            allowed = cpu_list(effective.read_text().strip())
            if not allowed or not cpus <= allowed:
                raise PipelineError("Configured affinity exceeds effective cpuset")
            limits["cpuset.cpus.effective"] = effective.read_text().strip()
        amount, period = map(int, limits["cpu.max"].split())
        expected = (memory, memory * 4 // 5, 0, tasks)
        # Kernel stores memory thresholds rounded down to whole pages.
        page = os.sysconf("SC_PAGE_SIZE")
        actual = tuple(int(limits[k]) for k in files[1:])
        if (
            100 * amount != round(quota * period)
            or period != 100_000
            or actual != (expected[0], expected[1] // page * page, *expected[2:])
            or info["KillMode"] != "control-group"
            or info["Restart"] != "no"
            or info["KillSignal"] != "9"
        ):
            raise PipelineError(f"Kernel or lifecycle limit mismatch: {limits}")
        return dict(
            limits,
            path=self.group,
            cpuset=sorted(cpus),
            owned=True,
            ownership_proof_sha256=digest({"invocation": self.invocation, "inode": self.inode}),
            descendants_complete=True,
            KillMode=info["KillMode"],
            Restart=info["Restart"],
        )

    def members(self):
        members = []
        for directory, _, _ in os.walk(self.path, onerror=_raise):
            for value in (Path(directory) / "cgroup.procs").read_text().split():
                pid = int(value)
                identity = process_identity(pid)
                if identity is None:
                    continue
                try:
                    group = cgroup_of(pid)
                    affinity = set()
                    for thread in Path(f"/proc/{pid}/task").iterdir():
                        try:
                            affinity.update(os.sched_getaffinity(int(thread.name)))
                        except ProcessLookupError:
                            continue
                except FileNotFoundError:
                    if process_identity(pid) == identity:
                        raise
                    continue
                if process_identity(pid) == identity:
                    members.append(
                        dict(
                            pid=pid,
                            start_ticks=identity,
                            cgroup=group,
                            affinity=sorted(affinity),
                            owned=True,
                        )
                    )
        return members

    def freeze(self, paused):
        self.owned()
        systemctl("freeze" if paused else "thaw", self.unit)
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            if counters(self.path / "cgroup.events")["frozen"] == int(paused):
                return
            time.sleep(0.01)
        raise PipelineError("Freeze/thaw readback mismatch")

    def quota(self, percent):
        self.owned()
        systemctl("set-property", "--runtime", self.unit, f"CPUQuota={percent:.2f}%")

    def populated(self):
        try:
            return bool(counters(self.path / "cgroup.events")["populated"])
        except FileNotFoundError:
            if not self.path.exists():
                return False
            raise

    def cleanup(self):
        # If startup failed before creating the cgroup, there is no live target.
        info = properties(self.unit)
        if not info.get("ControlGroup") and not self.path.exists():
            if info.get("LoadState") == "not-found":
                return True
        else:
            self.owned()
            if self.populated():
                systemctl("kill", "--signal=SIGKILL", "--kill-whom=all", self.unit)
            end = time.monotonic() + 0.8
            while self.populated():
                if time.monotonic() >= end:
                    raise PipelineError("Owned cgroup still populated after SIGKILL")
                time.sleep(0.02)
        info = self.owned(allow_empty=True)
        if info["ActiveState"] == "failed":
            systemctl("reset-failed", self.unit)
        else:
            systemctl("stop", self.unit)
        return not self.populated()


def _raise(error):
    raise error


def cpu_list(text):
    cpus = set()
    for part in text.split(","):
        first, sep, last = part.partition("-")
        cpus.update(range(int(first), int(last if sep else first) + 1))
    return cpus


def cpu_limit(snapshot):
    return min(
        [s["critical_C"] for s in snapshot["cpu_sensors"]]
        + [
            tip["C"]
            for zone in snapshot["platform_zones"]
            if zone["type"] in CPU_DOMAINS
            for tip in zone["limits"]
        ]
    )


def host_memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable"}:
            values[key] = int(value.split()[0]) * 1024
    return values


def host_budget(parent, cpus, critical):
    cpu_caps, memory_caps = [], []
    for node in (parent, *parent.parents):
        if not node.is_relative_to(CGROUP):
            break
        quota = node / "cpu.max"
        if quota.exists():
            amount, period = quota.read_text().split()
            if amount != "max":
                cpu_caps.append(int(amount) / int(period))
        for name in ("memory.max", "memory.high"):
            bound = node / name
            if bound.exists() and (value := bound.read_text().strip()) != "max":
                memory_caps.append(max(0, int(value) - int((node / "memory.current").read_text())))
    vm = host_memory()
    return HostBudget(
        tuple(cpus),
        vm["MemTotal"],
        vm["MemAvailable"],
        critical,
        min(cpu_caps, default=None),
        min(memory_caps, default=None),
    )


def swap_pages():
    vmstat = counters(Path("/proc/vmstat"))
    return vmstat["pswpin"] + vmstat["pswpout"]


def full_psi():
    line = next(
        line
        for line in Path("/proc/pressure/memory").read_text().splitlines()
        if line.startswith("full ")
    )
    return float(dict(item.split("=") for item in line.split()[1:])["avg10"])


class WorkerLimitExceeded(PipelineError):
    """A kernel counter already reported a terminal resource event."""


class Telemetry:
    def __init__(self, snapshot):
        self.reader = SensorReader(snapshot)
        self.old_pages, self.old_time = swap_pages(), time.monotonic()
        self.sensor_targets = {
            Path(s["path"]): (Path(s["path"]).resolve(strict=True), s["label"])
            for s in snapshot["cpu_sensors"]
        }

    def sample(self, worker, attempt):
        began = time.monotonic()
        # Read cgroup counters before host sensors. Never discard a limit event
        # already seen if another file disappears while systemd reaps the unit.
        oom = counters(worker.path / "memory.events")
        if oom["oom"] or oom["oom_kill"]:
            raise WorkerLimitExceeded("memory.events reports OOM")
        if counters(worker.path / "pids.events")["max"]:
            raise WorkerLimitExceeded("pids.events reports a task limit violation")
        memory = int((worker.path / "memory.current").read_text())
        for source, (target, label) in self.sensor_targets.items():
            if (
                source.resolve(strict=True) != target
                or source.with_name(source.name.replace("_input", "_label")).read_text().strip()
                != label
            ):
                raise PipelineError("CPU sensor mapping changed")
        reading = self.reader.read(began)
        pages = swap_pages()
        swap_rate = (pages - self.old_pages) * os.sysconf("SC_PAGE_SIZE") / (began - self.old_time)
        self.old_pages, self.old_time = pages, began
        disk = os.statvfs(attempt)
        critical = [
            int(p.with_name(p.name.replace("_input", "_crit")).read_text()) / 1000
            for p in self.sensor_targets
        ]
        critical.extend(z["limit_C"] for z in reading["platform"] if z["type"] in CPU_DOMAINS)
        psi = full_psi()
        available = host_memory()["MemAvailable"]
        return ResourceSample(
            now=time.monotonic(),
            sampled_at=began,
            temperature_c=reading["temperature_C"],
            cpu_critical_c=min(critical),
            available_bytes=available,
            cgroup_memory_bytes=memory,
            psi_full_avg10=psi,
            swap_bytes_per_second=swap_rate,
            disk_free_bytes=disk.f_bavail * disk.f_frsize,
            supervisor_healthy=True,
            watchdog_healthy=True,
            containment_verified=True,
            sensor_mapping_verified=True,
            hardware_alarm=reading["hardware_emergency"],
            oom_kill_delta=0,
            pids_max_delta=0,
        )


def watchdog_ping():
    address = os.environ["NOTIFY_SOCKET"]
    if not 0 < int(os.environ["WATCHDOG_USEC"]) <= 3_000_000:
        raise PipelineError("Guardian watchdog unavailable")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.2)
        sock.sendto(b"WATCHDOG=1", "\0" + address[1:] if address.startswith("@") else address)


def guardian_readback(manager, guardian):
    group = cgroup_of(os.getpid())
    info = properties(guardian)
    if (
        group != f"{manager}/app.slice/{guardian}"
        or info.get("ControlGroup") != group
        or info.get("Transient") != "yes"
        or info.get("MainPID") != str(os.getpid())
        or info.get("Restart") != "no"
    ):
        raise PipelineError("Guardian must run in its own bounded systemd unit")
    path = CGROUP / group.lstrip("/")
    keys = ("cpu.max", "memory.max", "memory.swap.max", "pids.max")
    limits = {key: (path / key).read_text().strip() for key in keys}
    if list(limits.values()) != ["25000 100000", str(256 * MIB), "0", "32"]:
        raise PipelineError(f"Guardian kernel limit mismatch: {limits}")
    return limits


def apply_decision(worker, decision, paused, quota, readback, attempt):
    action = decision["action"]
    if action == "FREEZE" and not paused:
        worker.freeze(True)
    requested = round(decision["cpu_quota_percent_one_cpu"], 2)
    if requested != quota:
        worker.quota(requested)
        readback(requested)
    if action == "FREEZE":
        return True, requested
    if paused:
        worker.freeze(False)
    if action == "CHECKPOINT_AND_EXIT" and not (attempt / "checkpoint-request.json").exists():
        atomic_json(
            attempt / "checkpoint-request.json",
            {
                "reason": "SLICE_DEADLINE",
                "invocation": worker.invocation,
            },
        )
    return False, requested


def completion_reason(attempt, invocation, exit_info):
    if exit_info["Result"] != "success" or exit_info["ExecMainStatus"] != "0":
        return "WORKER_FAILED"
    if not (attempt / "checkpoint-request.json").exists():
        return "COMPLETED"
    try:
        receipt = json.loads((attempt / "checkpoint-receipt.json").read_text())
    except (OSError, ValueError):
        return "SLICE_CHECKPOINT_UNCONFIRMED"
    if (
        isinstance(receipt, dict)
        and receipt.get("invocation") == invocation
        and receipt.get("checkpoint_committed") is True
    ):
        return "SLICE_COMPLETE"
    return "SLICE_CHECKPOINT_UNCONFIRMED"


def reconcile_cgroup_read_exit(error, worker, pid, started_at):
    """Recover read-only ENOENT after the entire pinned worker cgroup is gone."""
    if error.errno != errno.ENOENT or error.filename is None:
        return None
    path = Path(error.filename)
    root = worker.path
    if path != root and not (
        (path.parent == root and path.name in RUNTIME_CGROUP_FILES)
        or (root in path.parents and path.name == "cgroup.procs")
    ):
        return None
    try:
        root.stat()
    except FileNotFoundError:
        info = worker.exit_info(pid, started_at)
        # With the final counters gone, systemd must report an OOM kill as a
        # failure. Sleep/cooling alone must not turn an unsafe exit into success.
        if info is not None and info["OOMPolicy"] in {"stop", "kill"}:
            return info
    return None


def resume_verdict(
    result,
    *,
    bindings_match,
    checkpoint_valid,
    used_previous,
    fresh_preflight,
    explicit_resume_request,
):
    """Workload-specific checkpoint validation stays with the future workload."""
    reason = result.get("reason") if result.get("cleanup_verified") is True else None
    return resume_gate(
        terminal_reason=reason,
        bindings_match=bindings_match,
        checkpoint_valid=checkpoint_valid,
        used_previous=used_previous,
        fresh_preflight=fresh_preflight,
        explicit_resume_request=explicit_resume_request,
    )


def guard(attempt, token):
    spec = json.loads((attempt / "request.json").read_text())
    guardian = f"idps-t031-guardian-{token}.service"
    manager = properties()["ControlGroup"]
    limits = guardian_readback(manager, guardian)
    watchdog_ping()
    # One managed allocation per user. Release follows worker cleanup.
    lock_path = Path(os.environ["XDG_RUNTIME_DIR"]) / "idps-resource-adapter.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "rb+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        parent = CGROUP / manager.lstrip("/") / "app.slice"
        for path in parent.glob("idps-t031-worker-*.service"):
            if counters(path / "cgroup.events")["populated"]:
                raise PipelineError("Prior managed worker still populated; admission refused")
        return guard_locked(attempt, token, spec, guardian, manager, limits)


def guard_locked(attempt, token, spec, guardian, manager, guardian_limits):
    worker = OwnedWorker(token, manager)
    result = {"reason": "PREFLIGHT_REFUSED", "cleanup_verified": False, "auto_restart": False}
    launched = False
    try:
        hardware = hardware_snapshot()
        cpus = os.sched_getaffinity(0)
        plan = plan_resources(
            host_budget(worker.path.parent, cpus, cpu_limit(hardware)), spec["phase"]
        )
        quota = spec["cpu_percent"]
        memory = spec["memory_mib"] * MIB
        if review := spec.get("allocation_review"):
            from idps_ai.common import file_sha256
            from idps_ai.training.allocation_review import reviewed_plan

            path = Path(review["path"])
            if path.is_symlink() or file_sha256(path) != review["sha256"]:
                raise PipelineError("Allocation review digest changed")
            plan = reviewed_plan(plan, json.loads(path.read_text()), quota / 100, memory)
        tasks = 16
        controller = ResourceController(
            plan, cpu_cores=quota / 100, memory_bytes=memory, slice_seconds=spec["seconds"]
        )
        telemetry = Telemetry(hardware)
        receipt = admission(telemetry.reader, "RESOURCE_ADAPTER_GUARDIAN")
        atomic_json(attempt / "cold-start-admission.json", receipt)
        if receipt["decision"] != "ACCEPT":
            raise PipelineError("Cold-start refused: " + receipt["state"])
        first = receipt["reading"]
        base_quota = quota
        quota = quota_for_state(base_quota, receipt["state"])
        if properties(worker.unit)["LoadState"] != "not-found":
            raise PipelineError("Generated worker unit name already exists")
        settings = common_limits(quota, memory, tasks, spec["seconds"] + 30)
        settings.update(
            {
                "Description": worker.description,
                "BindsTo": guardian,
                "After": guardian,
                "RemainAfterExit": "yes",
                "ProtectControlGroups": "yes",
                "KillSignal": "SIGKILL",
                "CPUAffinity": " ".join(map(str, sorted(cpus))),
                "WorkingDirectory": spec["cwd"],
            }
        )
        launched = True  # A timed-out start request may already have created the unit.
        atomic_json(attempt / "worker-launch.json", {"unit": worker.unit})
        result["reason"] = "START_BARRIER_REFUSED"
        start_unit(worker.unit, internal("barrier", attempt, token), settings=settings)
        info, pid, identity = worker.pin()
        started_at = info["ExecMainStartTimestampMonotonic"]
        atomic_json(
            attempt / "worker-identity.json",
            {
                "invocation": worker.invocation,
                "inode": worker.inode,
            },
        )
        if guardian not in info["BindsTo"].split() or guardian not in info["After"].split():
            raise PipelineError("Worker lifecycle dependency missing")
        if info["MainPID"] == "0" or (attempt / "start.allowed").exists():
            raise PipelineError("Start barrier is not pending")
        deadline = time.monotonic() + 1
        while not (attempt / "barrier.json").exists():
            if time.monotonic() >= deadline:
                raise PipelineError("Worker did not acknowledge start barrier")
            time.sleep(0.02)
        marker = json.loads((attempt / "barrier.json").read_text())
        if marker != {"pid": pid, "start_ticks": identity}:
            raise PipelineError("Barrier process identity mismatch")

        def check_readback(value):
            nonlocal limits
            limits = worker.limits(info, cpus, value, memory, tasks)
            return limits

        limits = check_readback(quota)
        members = worker.members()
        if len(members) != 1 or members[0]["pid"] != pid:
            raise PipelineError("Unexpected processes before barrier release")
        if verify_containment(plan, [limits], members):
            raise PipelineError("Worker containment not verified")
        start_sample = telemetry.sample(worker, attempt)
        decision = controller.update(start_sample)
        if decision["action"] != "APPLY_QUOTA":
            raise PipelineError(f"Unsafe start: {decision}")
        paused, quota = apply_decision(worker, decision, False, quota, check_readback, attempt)
        limits = check_readback(quota)
        watchdog_ping()
        atomic_json(
            attempt / "preflight.json",
            {
                "limits": limits,
                "members": members,
                "guardian": guardian,
                "guardian_limits": guardian_limits,
                "worker": worker.unit,
                "guardian_pid": os.getpid(),
                "guardian_start_ticks": process_identity(os.getpid()),
                "invocation": worker.invocation,
                "worker_pid": pid,
                "worker_start_ticks": identity,
                "thermal": plan["thermal"],
                "base_cpu_quota_percent_one_cpu": base_quota,
                "initial_decision": decision,
                "temperature_c": first["temperature_C"],
                "preflight_monotonic_ns": time.monotonic_ns(),
            },
        )
        atomic_json(attempt / "start.allowed", {"invocation": worker.invocation})
        last_report = 0.0
        result["reason"] = "RUNTIME_CONTROL_FAILURE"

        def record_exit(exit_info, missing=None):
            reason = completion_reason(attempt, worker.invocation, exit_info)
            if reason in {"COMPLETED", "SLICE_COMPLETE"} and (paused or controller.terminal):
                raise PipelineError("Worker exited while a safety action was active")
            watchdog_ping()
            result.update(
                reason=reason,
                exit_proof={
                    "invocation": worker.invocation,
                    "worker_pid": pid,
                    "worker_start_ticks": identity,
                    "started_at_monotonic_us": int(started_at),
                    "exited_at_monotonic_us": int(exit_info["ExecMainExitTimestampMonotonic"]),
                    "exit_code_kind": int(exit_info["ExecMainCode"]),
                    "exit_status": int(exit_info["ExecMainStatus"]),
                    "systemd_result": exit_info["Result"],
                    "missing_cgroup_file": missing,
                },
            )

        while True:
            time.sleep(0.2)
            current = process_identity(pid)
            if current is None:
                exit_info = worker.exit_info(pid, started_at)
                if exit_info is None:
                    continue  # systemd has not observed the exit yet; watchdog still expires
                record_exit(exit_info)
                break
            if current != identity:
                raise PipelineError("Worker PID start ticks changed")
            try:
                check_readback(quota)
                if counters(worker.path / "cgroup.events")["frozen"] != int(paused):
                    raise PipelineError("Unexpected kernel freeze state")
                members = worker.members()
                if verify_containment(plan, [limits], members):
                    raise PipelineError("Runtime containment verification failed")
                sample = telemetry.sample(worker, attempt)
            except FileNotFoundError as exc:
                if paused or controller.terminal is not None:
                    raise
                exit_info = reconcile_cgroup_read_exit(exc, worker, pid, started_at)
                if exit_info is None:
                    raise
                record_exit(exit_info, Path(exc.filename).name)
                break
            decision = controller.update(sample)
            if decision["action"] == "STOP_OWNED_CGROUPS":
                result["reason"] = decision["reason"]
                atomic_json(
                    attempt / "terminal-sample.json",
                    {
                        "decision": decision,
                        "temperature_c": sample.temperature_c,
                        "monotonic": sample.now,
                        "hardware_alarm": sample.hardware_alarm,
                        "limits": limits,
                    },
                )
                break
            was_paused, previous_quota = paused, quota
            paused, quota = apply_decision(worker, decision, paused, quota, check_readback, attempt)
            if (paused, quota) != (was_paused, previous_quota) or sample.now - last_report >= 1:
                atomic_json(
                    attempt / "status.json",
                    {
                        "decision": decision,
                        "members": members,
                        "limits": limits,
                        "temperature_c": sample.temperature_c,
                        "memory_bytes": sample.cgroup_memory_bytes,
                        "monotonic": sample.now,
                        "psi_full_avg10": sample.psi_full_avg10,
                        "swap_bytes_per_second": sample.swap_bytes_per_second,
                    },
                )
                last_report = sample.now
            watchdog_ping()
    except WorkerLimitExceeded as exc:
        result.update(reason="OOM_OR_TASK_LIMIT", detail=str(exc))
    except (OSError, ValueError, KeyError, PipelineError, subprocess.SubprocessError) as exc:
        result["detail"] = str(exc)
    finally:
        try:
            result["cleanup_verified"] = worker.cleanup() if launched else True
        except (OSError, ValueError, KeyError, PipelineError, subprocess.SubprocessError) as exc:
            result["cleanup_error"] = str(exc)
        if not result["cleanup_verified"] and result["reason"] in {"COMPLETED", "SLICE_COMPLETE"}:
            result["reason"] = "RUNTIME_CONTROL_FAILURE"
        atomic_json(attempt / "result.json", result)
    return (
        0
        if result["cleanup_verified"] and result["reason"] in {"COMPLETED", "SLICE_COMPLETE"}
        else 1
    )


def internal(role, attempt, token):
    return [
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "_" + role,
        str(attempt),
        token,
    ]


def systemd_arg(arg):
    # ExecStopPost is parsed by systemd, with its own % and $ expansion rules.
    return json.dumps(arg.replace("%", "%%").replace("$", "$$"), ensure_ascii=False)


def after_guard(attempt, token):
    """Run under the guardian unit's ExecStopPost, including after watchdog kill."""
    manager = properties()["ControlGroup"]
    guardian = f"idps-t031-guardian-{token}.service"
    if cgroup_of(os.getpid()) != f"{manager}/app.slice/{guardian}":
        raise PipelineError("Cleanup hook is outside the guardian unit")
    if not (attempt / "worker-launch.json").is_file():
        return
    worker = OwnedWorker(token, manager)
    pinned = attempt / "worker-identity.json"
    if pinned.exists():
        identity = json.loads(pinned.read_text())
        worker.invocation, worker.inode = identity["invocation"], identity["inode"]
    path = attempt / "result.json"
    result = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "reason": "GUARDIAN_EXIT_WITHOUT_RESULT",
            "auto_restart": False,
        }
    )
    if result.get("cleanup_verified") is True:
        return
    result["guardian_service_result"] = os.environ.get("SERVICE_RESULT")
    try:
        result["cleanup_verified"] = worker.cleanup()
    except (OSError, ValueError, KeyError, PipelineError, subprocess.SubprocessError) as exc:
        result.update(cleanup_verified=False, cleanup_error=str(exc))
    atomic_json(path, result)


def barrier(attempt):
    atomic_json(
        attempt / "barrier.json",
        {
            "pid": os.getpid(),
            "start_ticks": process_identity(os.getpid()),
        },
    )
    deadline = time.monotonic() + 8
    while not (attempt / "start.allowed").is_file():
        if time.monotonic() >= deadline:
            raise PipelineError("Start barrier expired")
        time.sleep(0.025)
    preflight = json.loads((attempt / "preflight.json").read_text())
    release = json.loads((attempt / "start.allowed").read_text())
    if (
        preflight["worker_pid"] != os.getpid()
        or preflight["worker_start_ticks"] != process_identity(os.getpid())
        or release["invocation"] != preflight["invocation"]
        or process_identity(preflight["guardian_pid"]) != preflight["guardian_start_ticks"]
    ):
        raise PipelineError("Barrier approval does not match worker and guardian identities")
    spec = json.loads((attempt / "request.json").read_text())
    argv = spec["command"]
    from idps_ai.training.allocation_review import worker_environment

    env = worker_environment(spec, os.environ)
    env["IDPS_RESOURCE_ATTEMPT"] = str(attempt)
    os.execvpe(argv[0], argv, env)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "_guard":
        return guard(Path(sys.argv[2]), sys.argv[3])
    if len(sys.argv) == 4 and sys.argv[1] == "_barrier":
        return barrier(Path(sys.argv[2]))
    if len(sys.argv) == 4 and sys.argv[1] == "_after_guard":
        return after_guard(Path(sys.argv[2]), sys.argv[3])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True, help="New private output directory")
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--cpu-percent", type=int, default=25, help="Percent of one CPU")
    parser.add_argument("--memory-mib", type=int, default=256)
    parser.add_argument("--allocation-evidence", type=Path)
    parser.add_argument("--blas-threads", type=int, default=1)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    maximum_cpu = 100 if args.allocation_evidence is None else 100 * len(os.sched_getaffinity(0))
    if not command or not 1 <= args.seconds <= 3600 or not 5 <= args.cpu_percent <= maximum_cpu:
        parser.error("Require a command, 1–3600 seconds and CPU within the reviewed host envelope")
    if not 64 <= args.memory_mib <= 8 * GIB // MIB:
        parser.error("Memory must be between 64 MiB and 8 GiB, subject to the phase budget")
    if not 1 <= args.blas_threads <= max(1, (args.cpu_percent + 99) // 100) or (
        args.blas_threads > 1 and args.allocation_evidence is None
    ):
        parser.error("Multiple BLAS threads require matching reviewed CPU allocation")
    attempt = args.attempt.absolute()
    attempt.mkdir(mode=0o700)
    token = uuid.uuid4().hex
    review = {}
    if args.allocation_evidence is not None:
        from idps_ai.common import file_sha256

        path = args.allocation_evidence.absolute()
        if path.is_symlink() or not path.is_file():
            parser.error("Allocation evidence must be a regular non-symlink file")
        review = {"allocation_review": {"path": str(path), "sha256": file_sha256(path)}}
    atomic_json(
        attempt / "request.json",
        {
            "phase": args.phase,
            "seconds": args.seconds,
            "cpu_percent": args.cpu_percent,
            "memory_mib": args.memory_mib,
            "blas_threads": args.blas_threads,
            "cwd": os.getcwd(),
            "command": command,
            **review,
        },
    )
    settings = common_limits(25, 256 * MIB, 32, args.seconds + 40)
    settings.update(
        {
            "WatchdogSec": "3s",
            "WatchdogSignal": "SIGKILL",
            "NotifyAccess": "main",
            "TimeoutStopSec": "6s",
            "ExecStopPost": " ".join(
                systemd_arg(arg) for arg in internal("after_guard", attempt, token)
            ),
        }
    )
    code = start_unit(
        f"idps-t031-guardian-{token}.service",
        internal("guard", attempt, token),
        settings=settings,
        wait=True,
    )
    if not (attempt / "result.json").exists():
        # A missing cleanup receipt is a failed attempt even if the cgroup is gone.
        worker = OwnedWorker(token, properties()["ControlGroup"])
        deadline = time.monotonic() + 3
        while worker.path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        atomic_json(
            attempt / "result.json",
            {
                "reason": "GUARDIAN_EXIT_WITHOUT_RESULT",
                "cleanup_verified": not worker.path.exists(),
                "auto_restart": False,
            },
        )
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Thermal controller for trusted workers inside a delegated systemd service."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from idps_ai.common import PipelineError
from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
from idps_ai.training.resource_adapter import watchdog_ping
from idps_ai.training.thermal_policy import admission, quota_for_state

CGROUP = Path("/sys/fs/cgroup")
SUPERVISOR_LEAF = "ai-guardian"
UNIT_PROPERTIES = (
    "Delegate=cpu memory pids", f"DelegateSubgroup={SUPERVISOR_LEAF}",
    "NotifyAccess=main", "WatchdogSec=3s", "KillMode=control-group",
)


def membership(pid):
    relative = Path(f"/proc/{pid}/cgroup").read_text().strip().removeprefix("0::")
    if not relative.startswith("/") or ".." in Path(relative).parts:
        raise PipelineError("Unified cgroup membership is unavailable")
    return CGROUP / relative.lstrip("/")


def unit_root():
    leaf = membership("self")
    root = leaf.parent
    if leaf.name != SUPERVISOR_LEAF or not os.environ.get("INVOCATION_ID"):
        raise PipelineError("Run the guardian as the delegated systemd main process")
    if root.stat().st_uid != os.geteuid() or str(os.getpid()) not in (leaf / "cgroup.procs").read_text().split():
        raise PipelineError("Delegated unit ownership failed")
    if (root / "cgroup.procs").read_text().strip():
        raise PipelineError("Delegated parent contains unexpected processes")
    return root


def evidence(phase, **data):
    print(json.dumps({"resource_guardian": phase, **data}), flush=True)


def owns_worker_path(path, worker, *, allow_subgroups):
    return path == worker or (allow_subgroups and path.is_relative_to(worker))


def run(command, *, health=None, reader=None, allow_subgroups=False):
    """Run a trusted worker and its descendants under the unit's existing envelope."""
    root = unit_root()
    amount, period = map(int, (root / "cpu.max").read_text().split())
    if not 0 < amount or not 1000 <= period <= 1_000_000:
        raise PipelineError("A finite CPU quota is required")
    limits = {name: (root / name).read_text().strip() for name in
              ("memory.max", "memory.high", "memory.swap.max", "pids.max")}
    if limits["memory.swap.max"] != "0" or not all(
        int(limits[name]) > 0 for name in ("memory.max", "pids.max")
    ):
        raise PipelineError("A finite RAM and process envelope is required")
    reader = reader or SensorReader(hardware_snapshot())
    required = {"cpu", "memory", "pids"}
    if not required <= set((root / "cgroup.controllers").read_text().split()):
        raise PipelineError("The worker controllers are unavailable")
    (root / "cgroup.subtree_control").write_text("+cpu +memory +pids")
    worker = root / "ai-worker"
    worker.mkdir(mode=0o700)
    installed = None
    child = None
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    old_handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for name, value in limits.items():
            path = worker / name
            path.write_text(value)
            if path.read_text().strip() != value:
                raise PipelineError("Worker kernel envelope mismatch")
        while True:
            sample = admission(reader, "DELEGATED_GUARDIAN")
            if stopping:
                return 0
            if sample["decision"] != "ACCEPT":
                evidence("terminal", admission=sample)
                return 78
            watchdog_ping()
            wanted = f"{int(quota_for_state(amount, sample['state']))} {period}"
            if int(wanted.split()[0]) < 1000:
                raise PipelineError("Thermal quota is below the kernel minimum")
            path = worker / "cpu.max"
            if installed is not None and path.read_text().strip() != installed:
                raise PipelineError("Worker quota changed outside the guardian")
            if installed != wanted:
                path.write_text(wanted)
                installed = path.read_text().strip()
                if installed != wanted:
                    raise PipelineError("Worker quota readback mismatch")
                evidence("launch" if child is None else "runtime", cpu_max=installed,
                         state=sample["state"], temperature_c=sample["reading"]["temperature_C"])
            if child is None:
                def enter_worker():
                    (worker / "cgroup.procs").write_text(str(os.getpid()))

                environment = {k: v for k, v in os.environ.items()
                               if k not in {"NOTIFY_SOCKET", "WATCHDOG_USEC", "WATCHDOG_PID"}}
                child = subprocess.Popen(command, preexec_fn=enter_worker, env=environment)
            elif child.poll() is not None:
                return child.returncode if child.returncode >= 0 else 128 - child.returncode
            else:
                try:
                    if not owns_worker_path(
                        membership(child.pid), worker, allow_subgroups=allow_subgroups
                    ) or (root / "cpu.max").read_text().strip() != f"{amount} {period}":
                        raise PipelineError("Worker escaped its resource envelope")
                except FileNotFoundError:
                    if child.poll() is None:
                        raise
                    continue
                if health is not None:
                    code = health()
                    if code is not None:
                        return code
            time.sleep(0.2)
    finally:
        try:
            if stopping and child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            (worker / "cgroup.kill").write_text("1")
            if child is not None:
                child.wait(timeout=2)
            deadline = time.monotonic() + 1
            while "populated 1" in (worker / "cgroup.events").read_text().splitlines():
                if time.monotonic() >= deadline:
                    raise PipelineError("Worker cgroup did not empty")
                time.sleep(0.02)
            if allow_subgroups:
                descendants = [path for path in worker.rglob("*") if path.is_dir()]
                for descendant in sorted(descendants, key=lambda path: len(path.parts), reverse=True):
                    descendant.rmdir()
            worker.rmdir()
            evidence("cleanup", verified=not worker.exists())
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-owned-subgroups", action="store_true",
                        help="Allow supervisor movement only within its kernel-limited worker cgroup")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("Supply a worker command")
    try:
        return run(command, allow_subgroups=args.allow_owned_subgroups)
    except (OSError, ValueError, subprocess.SubprocessError, PipelineError) as exc:
        evidence("unverified", error=type(exc).__name__, detail=str(exc))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())

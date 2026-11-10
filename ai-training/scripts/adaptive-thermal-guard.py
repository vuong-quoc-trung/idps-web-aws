#!/usr/bin/env python3
"""Independent job-only adaptive controller; no host power/thermal changes."""

import argparse
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

import psutil

from idps_ai.common import PipelineError, atomic_json, canonical_bytes
from idps_ai.training.adaptive_thermal import SensorReader, ThermalMachine
from idps_ai.training.heartbeat import HeartbeatMonitor


def ctl(*items, check=True):
    return subprocess.run(
        ["systemctl", "--user", *items], check=check, capture_output=True, text=True, timeout=2
    )


def unit_state(unit):
    result = ctl(
        "show",
        unit,
        "-p",
        "ActiveState",
        "-p",
        "SubState",
        "-p",
        "MainPID",
        "-p",
        "ControlGroup",
        "-p",
        "Result",
        "-p",
        "ExecMainStatus",
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


class CgroupControl:
    def __init__(self, unit):
        if not re.fullmatch(r"idps-student-adaptive-work-[a-z0-9-]+\.service", unit):
            raise PipelineError("Refuse to control a non-research worker unit")
        self.unit = unit
        self.info = unit_state(unit)
        group = self.info["ControlGroup"]
        if not group.startswith(f"/user.slice/user-{os.getuid()}.slice/") or not group.endswith(
            "/" + unit
        ):
            raise PipelineError("Unexpected worker cgroup ownership")
        self.path = Path("/sys/fs/cgroup" + group)
        self.quota = None
        self.paused = False

    def quota_set(self, quota):
        quota = max(1, min(20, math.floor(quota)))
        if self.quota != quota:
            ctl("set-property", "--runtime", self.unit, f"CPUQuota={quota}%")
            q, period = map(int, (self.path / "cpu.max").read_text().split())
            if abs(q / period - quota / 100) > 0.001:
                raise PipelineError("CPU quota readback mismatch")
            self.quota = quota

    def freeze(self, paused):
        if paused != self.paused:
            ctl("freeze" if paused else "thaw", self.unit)
            expected = "1" if paused else "0"
            until = time.monotonic() + 1
            while time.monotonic() < until:
                fields = dict(
                    line.split() for line in (self.path / "cgroup.events").read_text().splitlines()
                )
                if fields["frozen"] == expected:
                    self.paused = paused
                    return
                time.sleep(0.01)
            raise PipelineError("Cgroup freeze/thaw readback mismatch")

    def stop(self):
        # Kill is valid for frozen cgroups; never thaw a hot worker before killing.
        ctl("kill", "--signal=SIGKILL", "--kill-whom=all", self.unit, check=False)
        ctl("thaw", self.unit, check=False)
        ctl("stop", self.unit, check=False)


def heartbeat_healthy(path, now=None):
    try:
        observed = Path(path).stat().st_mtime
        current = time.time() if now is None else now
        age = current - observed
        # Legacy filesystem API: bounded50ms skew, never arbitrary future dates.
        return -0.05 <= age <= 3
    except OSError:
        return False


def probe_safe(temperature, pressure, band):
    # An intentional freeze changes state to COOLDOWN, not the measured heat band.
    return temperature < 75 and not pressure and band == "NORMAL"


def publish_stop(attempt, state):
    plan = json.loads((attempt / "recovery-plan.json").read_text())
    status = {
        "state": state,
        "attempt_id": attempt.name,
        "last_heartbeat": time.time(),
        "run_id": plan["original_run_id"],
        "model_training": "NOT_STARTED",
        "exact_reason": "thermal-terminal.json",
    }
    atomic_json(attempt / "safety-stop.json", status)
    if not plan["preflight"]:
        atomic_json(attempt.parent.parent / "status.json", status)


def watch(attempt, unit, probe=False):
    hardware = json.loads((attempt / "hardware.json").read_text())
    reader = SensorReader(hardware)
    policy = json.loads((attempt / "recovery-plan.json").read_text())
    machine = ThermalMachine(
        emergency=hardware["effective_emergency_C"],
        warning=policy["warning_C"],
        throttle=policy["throttle_C"],
        strong=policy["strong_throttle_C"],
        cooldown=policy["cooldown_seconds"],
        cooling_timeout=policy["maximum_cooldown_seconds"],
    )
    supervisor_pid = json.loads((attempt / "services.json").read_text())["supervisor_pid"]
    heartbeat = HeartbeatMonitor(attempt / "supervisor-heartbeat.json", supervisor_pid)
    control = CgroupControl(unit)
    control.quota_set(20)
    started = time.monotonic()
    previous = None
    peak = 0
    samples = 0
    probe_phase = 0
    next_probe = started + 2
    probe_seen = []
    terminal = None
    last_flush = 0
    last_resource = 0
    pressure = False
    swap_old = psutil.swap_memory()
    metrics = {}
    total_area = active_area = seconds = active_seconds = 0
    try:
        with (attempt / "thermal-samples.jsonl").open("xb") as log:
            while True:
                now = time.monotonic()
                if (attempt / "worker-done.json").exists():
                    terminal = "COMPLETED"
                    break
                sample = reader.read(now)
                temp = sample["temperature_C"]
                peak = max(peak, temp)
                if now - last_resource >= 1:
                    vm = psutil.virtual_memory()
                    swap = psutil.swap_memory()
                    elapsed = max(0.001, now - last_resource) if last_resource else 1
                    psi = Path("/proc/pressure/memory").read_text()
                    full = next(
                        (
                            float(dict(p.split("=") for p in line.split()[1:])["avg10"])
                            for line in psi.splitlines()
                            if line.startswith("full ")
                        ),
                        0,
                    )
                    pressure = (
                        vm.available < 4 * 1024**3
                        or full >= 1
                        or (swap.sin - swap_old.sin + swap.sout - swap_old.sout) / elapsed
                        >= 16 * 1024**2
                    )
                    metrics = {
                        "MemAvailable_bytes": vm.available,
                        "swap": swap._asdict(),
                        "memory_pressure": pressure,
                        "cgroup_memory_bytes": int((control.path / "memory.current").read_text()),
                        "cgroup_cpu_stat": (control.path / "cpu.stat").read_text(),
                        "host_cpu_percent": psutil.cpu_percent(),
                        "memory_events": (control.path / "memory.events").read_text(),
                    }
                    if int(
                        dict(line.split() for line in metrics["memory_events"].splitlines()).get(
                            "oom_kill", 0
                        )
                    ):
                        raise PipelineError("Worker OOM detected")
                    last_resource = now
                    swap_old = swap
                health = heartbeat.check()
                result = machine.update(
                    now,
                    temp,
                    supervisor_healthy=health["healthy"],
                    memory_pressure=pressure,
                    hardware_emergency=sample["hardware_emergency"],
                )
                if previous:
                    dt = now - previous[0]
                    total_area += previous[1] * dt
                    seconds += dt
                    if not previous[2]:
                        active_area += previous[1] * dt
                        active_seconds += dt
                previous = (now, temp, result["paused"])
                if result["stop"]:
                    terminal = result["state"]
                    atomic_json(
                        attempt / "thermal-terminal.json",
                        {
                            "state": terminal,
                            "sample": sample,
                            "policy": result,
                            "supervisor_health": health,
                            "time": time.time(),
                        },
                    )
                    publish_stop(attempt, terminal)
                    control.stop()
                else:
                    control.quota_set(result["quota"])
                    control.freeze(result["paused"])
                    # Preflight only: exercise real kernel quota/freeze/readback at cool temperatures.
                    # No fake temperature is ever supplied to the live safety controller.
                    if probe and not (attempt / "control-probe.json").exists():
                        if not probe_safe(temp, pressure, result["band"]):
                            raise PipelineError("Preflight control probe lacks cool headroom")
                        if now >= next_probe:
                            actions = [
                                ("quota", 10),
                                ("freeze", True),
                                ("freeze", False),
                                ("quota", 5),
                                ("quota", 20),
                            ]
                            action, value = actions[probe_phase]
                            if action == "quota":
                                control.quota_set(value)
                            else:
                                control.freeze(value)
                            # Keep machine state consistent so the next tick does not undo the probe.
                            machine.quota = control.quota
                            machine.paused = control.paused
                            if not control.paused:
                                machine.pause_since = None
                            probe_seen.append({"action": action, "value": value, "at": time.time()})
                            probe_phase += 1
                            next_probe = now + 1
                            if probe_phase == len(actions):
                                machine.quota = 20
                                machine.paused = False
                                atomic_json(
                                    attempt / "control-probe.json",
                                    {
                                        "state": "PASS",
                                        "real_sensor_max_C": peak,
                                        "operations": probe_seen,
                                        "worker_heartbeat_not_used_for_monitor_health": True,
                                    },
                                )
                samples += 1
                status = {
                    "state": result["state"],
                    "time": time.time(),
                    "last_heartbeat": time.time(),
                    "heartbeat_monotonic_ns": time.monotonic_ns(),
                    "unit": unit,
                    "controller_pid": os.getpid(),
                    "CPU_quota_percent_one_core": control.quota,
                    "paused": control.paused,
                    "temperature_C": temp,
                    "peak_temperature_C": peak,
                    "effective_emergency_C": machine.emergency,
                    "sample": sample,
                    "policy": result,
                    "supervisor_health": health,
                    "resources": metrics,
                    "samples": samples,
                    "active_average_C": active_area / active_seconds if active_seconds else None,
                    "wall_average_C": total_area / seconds if seconds else None,
                }
                atomic_json(attempt / "thermal-status.json", status)
                log.write(canonical_bytes(status) + b"\n")
                if now - last_flush >= 1:
                    log.flush()
                    last_flush = now
                if terminal:
                    break
                time.sleep(max(0.001, 0.1 - (time.monotonic() - now)))
    except BaseException as exc:
        terminal = "SENSOR_OR_CONTROLLER_FAILURE"
        atomic_json(
            attempt / "thermal-terminal.json",
            {
                "state": terminal,
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "time": time.time(),
            },
        )
        publish_stop(attempt, terminal)
        control.stop()
        raise
    finally:
        atomic_json(
            attempt / "thermal-report.json",
            {
                "state": terminal,
                "peak_temperature_C": peak,
                "samples": samples,
                "independent_systemd_service": True,
                "effective_emergency_C": machine.emergency,
                "seconds": time.monotonic() - started,
            },
        )
    if terminal != "COMPLETED":
        raise PipelineError("Adaptive controller safely stopped the worker")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attempt", type=Path, required=True)
    p.add_argument("--unit", required=True)
    p.add_argument("--probe-controls", action="store_true")
    args = p.parse_args()
    os.umask(0o077)
    watch(args.attempt, args.unit, args.probe_controls)

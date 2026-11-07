#!/usr/bin/env python3
"""One research systemd cgroup plus independent CPU-temperature watchdog.

Uses existing CPU sensor reader. Kernel quota covers every task in the unit,
including threads/descendants. No host thermal/power configuration is modified.
"""

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

spec = importlib.util.spec_from_file_location(
    "p0thermal", Path(__file__).with_name("p0-thermal-run.py")
)
thermal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thermal)
rolling_spec = importlib.util.spec_from_file_location(
    "rolling_policy", Path(__file__).with_name("rolling-resource-policy.py")
)
rolling = importlib.util.module_from_spec(rolling_spec)
rolling_spec.loader.exec_module(rolling)


def atomic_status(root, value):
    value = {"schema_version": "resource-supervisor-1", **value}
    path = root / "resource-status.tmp"
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.replace(root / "resource-status.json")


def ctl(*args, check=True):
    return subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, text=True, timeout=5, check=check
    )


def kill_unit(unit):
    ctl("kill", "--signal=SIGKILL", "--kill-whom=all", unit, check=False)
    ctl("thaw", unit, check=False)
    ctl("stop", unit, check=False)


def cpu_reading():
    values = thermal.cpu_sensors()
    return max(v["celsius"] for v in values.values()), values


def control_action(temp, rate, paused, cool_seconds, pressure=False):
    if temp >= 80:
        return "KILL"
    if pressure or temp >= 72 or (temp >= 65 and rate >= 5):
        return "FREEZE" if not paused else "WAIT"
    if paused and temp < 68 and cool_seconds >= 5:
        return "THAW"
    return "WAIT"


def reduced_quota(quota):
    """A thermal reduction must never raise a conservative caller's quota."""
    return max(1, min(10, quota / 2))


def watchdog_override(action, build_pause, paused, watchdog_paused):
    # A prior early-freeze marker must never override a current hard stop.
    if action != "KILL" and build_pause and watchdog_paused and not paused:
        return "FREEZE"
    return action


def watchdog(unit, root, build_pause=False, policy="rolling", cutoff=90):
    root = Path(root)
    samples = []
    reason = "monitor_completed"
    try:
        while not (root / "watchdog-done").exists():
            temp, _ = cpu_reading()
            heartbeat = root / "heartbeat"
            age = time.time() - heartbeat.stat().st_mtime
            samples.append(
                {
                    "monotonic": time.monotonic(),
                    "cpu_max_celsius": temp,
                    "heartbeat_age_seconds": age,
                }
            )
            if policy == "legacy" and build_pause and temp >= 70 and age <= 3:
                ctl("freeze", unit)
                (root / "watchdog-paused").touch()
            if temp >= (79 if policy == "legacy" else cutoff) or age > 3:
                reason = (
                    "emergency_temperature"
                    if temp >= (79 if policy == "legacy" else cutoff)
                    else "monitor_heartbeat_stale"
                )
                kill_unit(unit)
                (root / "watchdog-tripped").write_text(reason)
                break
            time.sleep(0.2)
    except BaseException as exc:
        reason = "watchdog_sensor_or_control_error:" + type(exc).__name__
        kill_unit(unit)
        (root / "watchdog-tripped").write_text(reason)
    finally:
        (root / "watchdog-report.json").write_text(
            json.dumps(
                {
                    "reason": reason,
                    "samples": len(samples),
                    "temperature_min": min((x["cpu_max_celsius"] for x in samples), default=None),
                    "temperature_max": max((x["cpu_max_celsius"] for x in samples), default=None),
                },
                indent=2,
            )
            + "\n"
        )
        with (root / "watchdog-samples.jsonl").open("w") as stream:
            for row in samples:
                stream.write(json.dumps(row) + "\n")


def build_control_action(temp, rate, paused, cool_seconds, pressure=False):
    """Suspend build processes early, retaining compiler state, never used by AI."""
    if temp >= 80:
        return "KILL"
    if pressure or temp >= 65 or (temp >= 60 and rate >= 5):
        return "FREEZE" if not paused else "WAIT"
    if paused and temp < 60 and cool_seconds >= 5:
        return "THAW"
    return "WAIT"


def run(
    command,
    output,
    quota=100,
    max_seconds=180,
    sensor=None,
    build_pause=False,
    scope=False,
    policy="rolling",
    memory_gib=4,
    cutoff=90,
):
    sensor = sensor or cpu_reading
    if not 80 < cutoff <= 90 or not 0 < memory_gib <= 26:
        raise ValueError("Cutoff must be >80 and <=90C; memory budget must be <=26GiB")
    root = Path(output).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    unit = (
        "idps-integration-"
        + str(os.getpid())
        + "-"
        + str(time.time_ns())[-8:]
        + (".scope" if scope else ".service")
    )
    temperature, readings = cpu_reading()
    memory = psutil.virtual_memory()
    safe_ram = min(
        memory_gib * 1024**3 if policy == "rolling" else 2 * 1024**3,
        memory.available - (4 * 1024**3 if policy == "rolling" else 2_000_000_000),
        30_000_000_000
        - (memory.total - memory.available)
        - (4 * 1024**3 if policy == "rolling" else 2_000_000_000),
    )
    if temperature >= (75 if policy == "rolling" else 65) or safe_ram < 1024**3:
        raise RuntimeError("CPU must be below65C and shared RAM headroom >=1GiB")
    if not 1 <= quota <= (100 if policy == "legacy" else 50 * (os.cpu_count() or 1)):
        raise RuntimeError("Quota exceeds soft50% host budget (quota units are percent of one CPU)")
    (root / "heartbeat").touch()
    monitor = None
    heat = rolling.HeatWindow()
    last_adjust = 0
    current_quota = quota
    previous_cpu_usage = None
    previous_swap = None
    emergency = False
    psutil.cpu_percent()
    samples, events = [], []
    metrics = None
    paused = False
    cool_since = None
    previous = temperature
    previous_at = time.monotonic()
    start = time.monotonic()
    failure = None
    group = None
    result = None
    scope_process = None
    unit_start = [
        "systemd-run",
        "--user",
        "--quiet",
        "--unit",
        unit,
        "--service-type=exec",
        "--working-directory",
        os.getcwd(),
        "-p",
        f"CPUQuota={quota}%",
        "-p",
        "CPUQuotaPeriodSec=10ms",
        "-p",
        f"MemoryMax={int(safe_ram)}",
        "-p",
        f"MemoryHigh={int(safe_ram * 0.8)}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "TasksMax=64",
        "-p",
        "KillMode=control-group",
        "-p",
        "TimeoutStopSec=2",
        "-p",
        "RemainAfterExit=yes",
        "-p",
        f"RuntimeMaxSec={max_seconds + 5}",
        "-p",
        f"CPUAffinity={'0' if policy == 'legacy' else '0-' + str(max(0, min(7, (os.cpu_count() or 1) - 1)))}",
        "-p",
        "Nice=10",
        "-p",
        f"StandardOutput=append:{root / 'stdout.log'}",
        "-p",
        f"StandardError=append:{root / 'stderr.log'}",
    ]
    for name in [
        "PYTHONDONTWRITEBYTECODE",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
    ]:
        unit_start += ["--setenv", name + "=" + ("1")]
    unit_start += ["--setenv", "PATH=" + os.environ["PATH"]]

    def interrupted(signum, frame):
        raise InterruptedError(f"monitor signal {signum}")

    old = {s: signal.signal(s, interrupted) for s in [signal.SIGTERM, signal.SIGINT]}
    try:
        if scope:
            # A scope inherits the caller's user-namespace permissions/AppArmor
            # domain. A service starts under the user manager's domain instead.
            # Keep the same kernel memory/CPU limits and independent watchdog.
            scope_command = ["systemd-run", "--user", "--scope", "--quiet", "--unit", unit]
            for setting in [
                f"CPUQuota={quota}%",
                "CPUQuotaPeriodSec=10ms",
                f"MemoryMax={int(safe_ram)}",
                f"MemoryHigh={int(safe_ram * 0.8)}",
                "MemorySwapMax=0",
                "TasksMax=64",
            ]:
                scope_command += ["-p", setting]
            environment = os.environ | {
                name: "1"
                for name in [
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "PYTHONDONTWRITEBYTECODE",
                ]
            }
            scope_process = subprocess.Popen(
                [
                    *scope_command,
                    "nice",
                    "-n",
                    "10",
                    "taskset",
                    "-c",
                    "0"
                    if policy == "legacy"
                    else "0-" + str(max(0, min(7, (os.cpu_count() or 1) - 1))),
                    *command,
                ],
                env=environment,
                stdout=(root / "stdout.log").open("ab"),
                stderr=(root / "stderr.log").open("ab"),
            )
            deadline = time.monotonic() + 10
            while not ctl(
                "show", unit, "-p", "ControlGroup", "--value", check=False
            ).stdout.strip():
                if scope_process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Guarded scope did not start")
                time.sleep(0.05)
        else:
            subprocess.run(
                [*unit_start, *command], check=True, capture_output=True, text=True, timeout=15
            )
        group = ctl("show", unit, "-p", "ControlGroup", "--value").stdout.strip()
        if not group or group == "/":
            raise RuntimeError("Workload exited before cgroup readback; inspect stderr.log")
        cgroup = Path("/sys/fs/cgroup") / group.lstrip("/")
        readback = {
            k: (cgroup / k).read_text().strip()
            for k in ["cpu.max", "memory.max", "memory.high", "memory.swap.max"]
        }
        q, p = map(int, readback["cpu.max"].split())
        if abs(q / p - quota / 100) > 0.001 or readback["memory.swap.max"] != "0":
            raise RuntimeError("Kernel quota or swap readback mismatch")
        (root / "kernel-readback.json").write_text(
            json.dumps({"unit": unit, "cgroup": group, "limits": readback}, indent=2) + "\n"
        )
        monitor_command = [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "--action",
            "watchdog",
            "--unit",
            unit,
            "--output",
            str(root),
        ]
        monitor_command += ["--policy", policy, "--cutoff", str(cutoff)]
        if build_pause:
            monitor_command.append("--build-pause")
        monitor = subprocess.Popen(
            monitor_command,
            start_new_session=True,
        )
        while True:
            (root / "heartbeat").touch()
            if scope_process is not None and scope_process.poll() is not None:
                code = scope_process.wait()
                result = {
                    "ExecMainStatus": str(code),
                    "Result": "success" if code == 0 else "exit-code",
                    "scope": True,
                }
                break
            temp, values = sensor()
            now = time.monotonic()
            elapsed = now - start
            memory = psutil.virtual_memory()
            used = memory.total - memory.available
            pressure = (
                (used >= 29_000_000_000 or memory.available < 2_000_000_000)
                if policy == "legacy"
                else memory.available < 4 * 1024**3
            )
            metrics = heat.add(now, temp, paused)
            cpu_percent = psutil.cpu_percent()
            psi = (
                Path("/proc/pressure/memory").read_text()
                if Path("/proc/pressure/memory").exists()
                else "NOT_AVAILABLE"
            )
            swap = psutil.swap_memory()._asdict()
            if policy == "rolling" and previous_swap:
                pressure = pressure or rolling.memory_pressure(
                    psi,
                    swap["sin"] - previous_swap["sin"],
                    swap["sout"] - previous_swap["sout"],
                    now - previous_at,
                )
            previous_swap = swap
            cpu_usage = (
                int(
                    dict(
                        line.split() for line in (cgroup / "cpu.stat").read_text().splitlines()
                    ).get("usage_usec", 0)
                )
                if cgroup.exists()
                else 0
            )
            own_cpu_percent = (
                0
                if previous_cpu_usage is None
                else max(
                    0, (cpu_usage - previous_cpu_usage) / 1e6 / max(now - previous_at, 0.1) * 100
                )
            )
            previous_cpu_usage = cpu_usage
            rate = (temp - previous) / max(now - previous_at, 0.1)
            previous = temp
            previous_at = now
            if (
                paused
                and temp < (75 if policy == "rolling" else (60 if build_pause else 68))
                and not pressure
            ):
                cool_since = now if cool_since is None else cool_since
            else:
                cool_since = None
            action = (build_control_action if build_pause else control_action)(
                temp, rate, paused, 0 if cool_since is None else now - cool_since, pressure
            )
            if policy == "rolling":
                action = rolling.action(
                    temp,
                    metrics["rolling_300s_c"],
                    rate,
                    paused,
                    0 if cool_since is None else now - cool_since,
                    pressure,
                    cutoff,
                )
                if (
                    metrics["rolling_300s_c"] < 76
                    and temp < 75
                    and not paused
                    and now - last_adjust > 5
                ):
                    # Host utilization includes other apps; headroom is a soft budget.
                    next_quota = rolling.cpu_budget(
                        current_quota, quota, cpu_percent, own_cpu_percent, os.cpu_count() or 1
                    )
                    if next_quota != current_quota:
                        ctl("set-property", "--runtime", unit, f"CPUQuota={next_quota}%")
                        current_quota = next_quota
                    last_adjust = now
            threads = []
            if cgroup.exists():
                for pid in (cgroup / "cgroup.procs").read_text().split():
                    for task in Path("/proc").joinpath(pid, "task").glob("*"):
                        try:
                            threads.append(
                                {
                                    "tid": int(task.name),
                                    "affinity": sorted(os.sched_getaffinity(int(task.name))),
                                }
                            )
                        except OSError:
                            pass
                sample = {
                    "elapsed": elapsed,
                    "cpu_max_celsius": temp,
                    "readings": values,
                    "temperature_rise_per_second": rate,
                    "memory_current": int((cgroup / "memory.current").read_text()),
                    "system_used_bytes": used,
                    "mem_available_bytes": memory.available,
                    "cpu_stat": (cgroup / "cpu.stat").read_text(),
                    "threads": threads,
                    "paused": paused,
                    "action": action,
                    "thermal": metrics,
                    "host_cpu_utilization_percent": cpu_percent,
                    "own_cpu_percent_one_cpu": own_cpu_percent,
                    "memory_pressure": psi,
                    "swap": swap,
                    "memory_events": (cgroup / "memory.events").read_text(),
                    "cpu_quota_percent_one_cpu": current_quota,
                }
                samples.append(sample)
            if (root / "watchdog-tripped").exists():
                raise RuntimeError((root / "watchdog-tripped").read_text())
            atomic_status(
                root,
                {
                    "status": "PAUSED" if paused else "RUNNING",
                    "heartbeat": time.time(),
                    "unit": unit,
                    "thermal": metrics,
                    "host_cpu_utilization_percent": cpu_percent,
                    "mem_available_bytes": memory.available,
                    "quota_percent_one_cpu": current_quota,
                    "policy": policy,
                },
            )
            if policy == "legacy":
                action = watchdog_override(
                    action, build_pause, paused, (root / "watchdog-paused").exists()
                )
            if action == "KILL":
                emergency = True
                raise RuntimeError(f"{cutoff if policy == 'rolling' else 80}C emergency stop")
            if action == "REDUCE" and now - last_adjust >= 2:
                current_quota = max(1, current_quota / 2)
                ctl("set-property", "--runtime", unit, f"CPUQuota={current_quota}%")
                events.append(
                    {
                        "elapsed": elapsed,
                        "action": "REDUCE",
                        "temperature": temp,
                        "cpu_quota_percent": current_quota,
                    }
                )
                last_adjust = now
            if action == "FREEZE":
                ctl("freeze", unit)
                current_quota = (
                    reduced_quota(current_quota)
                    if policy == "legacy"
                    else max(1, current_quota / 2)
                )
                ctl("set-property", "--runtime", unit, f"CPUQuota={current_quota}%")
                paused = True
                events.append(
                    {
                        "elapsed": elapsed,
                        "action": "FREEZE_AND_REDUCE",
                        "temperature": temp,
                        "cpu_quota_percent": current_quota,
                    }
                )
            elif action == "THAW":
                (root / "watchdog-paused").unlink(missing_ok=True)
                ctl("thaw", unit)
                paused = False
                events.append({"elapsed": elapsed, "action": "THAW", "temperature": temp})
            heat.previous = (now, temp, paused)
            if elapsed > max_seconds:
                raise RuntimeError("wall-time limit")
            status = ctl(
                "show",
                unit,
                "-p",
                "ActiveState",
                "-p",
                "SubState",
                "-p",
                "ExecMainStatus",
                "-p",
                "Result",
                "-p",
                "CPUUsageNSec",
                "-p",
                "MemoryPeak",
                check=not scope,
            ).stdout
            state = dict(line.split("=", 1) for line in status.splitlines() if "=" in line)
            if scope:
                time.sleep(0.2)
                continue
            if (
                state.get("ActiveState") in ["inactive", "failed"]
                or state.get("SubState") == "exited"
            ):
                result = state
                break
            time.sleep(0.2)
        if int(result["ExecMainStatus"]) != 0 or result.get("Result") != "success":
            raise RuntimeError("Workload failed: " + str(result))
    except BaseException as exc:
        failure = str(exc)
        kill_unit(unit)
    finally:
        (root / "watchdog-done").touch()
        if monitor:
            try:
                monitor.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor.kill()
                monitor.wait()
        for s, h in old.items():
            signal.signal(s, h)
        if result is None:
            result = ctl(
                "show",
                unit,
                "-p",
                "ActiveState",
                "-p",
                "ExecMainStatus",
                "-p",
                "Result",
                "-p",
                "CPUUsageNSec",
                "-p",
                "MemoryPeak",
                check=False,
            ).stdout
        watchdog_reason = (
            (root / "watchdog-tripped").read_text()
            if (root / "watchdog-tripped").exists()
            else None
        )
        emergency = emergency or watchdog_reason == "emergency_temperature"
        report = {
            "status": "PASS" if failure is None else "STOPPED",
            "failure": failure,
            "unit": unit,
            "wall_seconds": time.monotonic() - start,
            "kernel_cpu_quota_percent": quota,
            "cpu_temperature_min": min((s["cpu_max_celsius"] for s in samples), default=None),
            "cpu_temperature_mean": sum(s["cpu_max_celsius"] for s in samples) / len(samples)
            if samples
            else None,
            "cpu_temperature_max": max((s["cpu_max_celsius"] for s in samples), default=None),
            "peak_cgroup_memory_bytes": max((s["memory_current"] for s in samples), default=0),
            "peak_system_used_bytes": max((s["system_used_bytes"] for s in samples), default=0),
            "events": events,
            "systemd_result": result,
            "source_sha256": __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest(),
            "safety_scope": (
                "build: freeze>=65C, independent freeze>=70C AND kill>=79C; resume<60C stable5s; sensor/heartbeat failure kills; no control of external host heat"
                if build_pause
                else "all tasks in named cgroup; independent watchdog>=79C or heartbeat>3s; runtime deadline; no absolute spike guarantee"
            ),
            "build_pause_only": build_pause,
            "scope_mode": scope,
            "policy": policy,
            "instant_cutoff_c": cutoff if policy == "rolling" else 79,
            "thermal_time_weighted": metrics if samples else None,
            "emergency_stops": int(emergency),
            "watchdog_failure": watchdog_reason,
            "automatic_restarts": 0,
            "reserve_bytes": 4 * 1024**3 if policy == "rolling" else 2_000_000_000,
        }
        if policy == "rolling":
            report["safety_scope"] = (
                "rolling300s>=80 pause; reduce>=77; instantaneous cutoff; independent sensor/heartbeat watchdog; active/paused averages separate, no auto emergency restart; cannot control external heat"
            )
        atomic_status(
            root,
            {
                "status": "COMPLETED"
                if failure is None
                else (
                    "THERMAL_STOPPED"
                    if emergency
                    else (
                        "INTERRUPTED"
                        if failure.startswith("monitor signal") or failure == "wall-time limit"
                        else "FAILED"
                    )
                ),
                "heartbeat": time.time(),
                "failure": failure,
                "unit": unit,
                "thermal": metrics if samples else None,
            },
        )
        (root / "resource-report.json").write_text(json.dumps(report, indent=2) + "\n")
        with (root / "samples.jsonl").open("w") as stream:
            for sample in samples:
                stream.write(json.dumps(sample) + "\n")
        if failure is None:
            ctl("stop", unit, check=False)
    if failure:
        raise RuntimeError(failure)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=["run", "watchdog"], default="run")
    parser.add_argument("--output", required=True)
    parser.add_argument("--unit")
    parser.add_argument("--quota", type=int, default=100)
    parser.add_argument("--policy", choices=["rolling", "legacy"], default="rolling")
    parser.add_argument("--memory-gib", type=float, default=4)
    parser.add_argument("--cutoff", type=float, default=90)
    parser.add_argument("--max-seconds", type=int, default=180)
    parser.add_argument(
        "--scope",
        action="store_true",
        help="Retain caller user-namespace permissions in a guarded scope; selected policy still applies",
    )
    parser.add_argument(
        "--build-pause",
        action="store_true",
        help="Legacy policy only: early build freeze65C/resume60C. Rolling policy uses the common adaptive control.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "watchdog":
        watchdog(args.unit, args.output, args.build_pause, args.policy, args.cutoff)
    else:
        run(
            args.command[1:] if args.command[:1] == ["--"] else args.command,
            args.output,
            args.quota,
            args.max_seconds,
            build_pause=args.build_pause,
            scope=args.scope,
            policy=args.policy,
            memory_gib=args.memory_gib,
            cutoff=args.cutoff,
        )

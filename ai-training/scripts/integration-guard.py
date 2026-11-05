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


def watchdog(unit, root):
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
            if temp >= 79 or age > 3:
                reason = "temperature_79" if temp >= 79 else "monitor_heartbeat_stale"
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


def run(command, output, quota=25, max_seconds=180, sensor=None):
    sensor = sensor or cpu_reading
    root = Path(output).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    unit = "idps-integration-" + str(os.getpid()) + "-" + str(time.time_ns())[-8:] + ".service"
    temperature, readings = cpu_reading()
    memory = psutil.virtual_memory()
    safe_ram = min(
        2 * 1024**3,
        memory.available - 2_000_000_000,
        30_000_000_000 - (memory.total - memory.available) - 2_000_000_000,
    )
    if temperature >= 65 or safe_ram < 1024**3:
        raise RuntimeError("CPU must be below65C and shared RAM headroom >=1GiB")
    if not 1 <= quota <= 100:
        raise RuntimeError("This bounded pilot permits1–100% of one CPU")
    (root / "heartbeat").touch()
    monitor = None
    samples, events = [], []
    paused = False
    cool_since = None
    previous = temperature
    previous_at = time.monotonic()
    start = time.monotonic()
    failure = None
    group = None
    result = None
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
        "CPUAffinity=0",
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

    def interrupted(signum, frame):
        raise InterruptedError(f"monitor signal {signum}")

    old = {s: signal.signal(s, interrupted) for s in [signal.SIGTERM, signal.SIGINT]}
    try:
        subprocess.run(
            [*unit_start, *command], check=True, capture_output=True, text=True, timeout=15
        )
        group = ctl("show", unit, "-p", "ControlGroup", "--value").stdout.strip()
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
        monitor = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "--action",
                "watchdog",
                "--unit",
                unit,
                "--output",
                str(root),
            ],
            start_new_session=True,
        )
        while True:
            (root / "heartbeat").touch()
            temp, values = sensor()
            now = time.monotonic()
            elapsed = now - start
            memory = psutil.virtual_memory()
            used = memory.total - memory.available
            pressure = used >= 29_000_000_000 or memory.available < 2_000_000_000
            rate = (temp - previous) / max(now - previous_at, 0.1)
            previous = temp
            previous_at = now
            if paused and temp < 68 and not pressure:
                cool_since = now if cool_since is None else cool_since
            else:
                cool_since = None
            action = control_action(
                temp, rate, paused, 0 if cool_since is None else now - cool_since, pressure
            )
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
                }
                samples.append(sample)
            if (root / "watchdog-tripped").exists():
                raise RuntimeError((root / "watchdog-tripped").read_text())
            if action == "KILL":
                raise RuntimeError("80C hard stop")
            if action == "FREEZE":
                ctl("freeze", unit)
                ctl("set-property", "--runtime", unit, "CPUQuota=10%")
                paused = True
                events.append(
                    {"elapsed": elapsed, "action": "FREEZE_AND_REDUCE", "temperature": temp}
                )
            elif action == "THAW":
                ctl("thaw", unit)
                paused = False
                events.append({"elapsed": elapsed, "action": "THAW", "temperature": temp})
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
            ).stdout
            state = dict(line.split("=", 1) for line in status.splitlines() if "=" in line)
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
            "safety_scope": "all tasks in named cgroup; independent watchdog>=79C or heartbeat>3s; runtime deadline; no absolute spike guarantee",
        }
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
    parser.add_argument("--quota", type=int, default=25)
    parser.add_argument("--max-seconds", type=int, default=180)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "watchdog":
        watchdog(args.unit, args.output)
    else:
        run(
            args.command[1:] if args.command[:1] == ["--"] else args.command,
            args.output,
            args.quota,
            args.max_seconds,
        )

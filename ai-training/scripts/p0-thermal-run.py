#!/usr/bin/env python3
"""Bounded P0 process supervisor; CPU-only sensors, pause/resume and shared RAM.

This supervises only a named research process group and explicitly named lab
containers. It does not change host power settings or existing services.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import psutil


def cpu_sensors():
    readings = {}
    for directory in Path("/sys/class/hwmon").glob("hwmon*"):
        if (directory / "name").read_text().strip() not in {"coretemp", "k10temp", "zenpower"}:
            continue
        for sensor in directory.glob("temp*_input"):
            label = sensor.with_name(sensor.name.replace("_input", "_label"))
            name = label.read_text().strip() if label.exists() else sensor.name
            value = float(sensor.read_text()) / 1000
            if not 0 < value < 130:
                raise RuntimeError("Invalid CPU temperature")
            readings[str(sensor)] = {"label": name, "celsius": value}
    if not readings:
        raise RuntimeError("No reliable CPU sensor; refusing workload")
    return readings


def podman(action, name, *args):
    return subprocess.run(
        ["podman", action, *args, name], capture_output=True, text=True, timeout=12
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--containers", nargs="*", default=[])
    parser.add_argument("--max-seconds", type=int, default=1800)
    parser.add_argument("--initial-cpus", type=int, default=1)
    parser.add_argument("--sample-seconds", type=float, default=0.2)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if (
        not 1 <= args.initial_cpus <= len(os.sched_getaffinity(0))
        or not 0.05 <= args.sample_seconds <= 1
    ):
        raise RuntimeError("Invalid CPU affinity count or sensor sample period")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.umask(0o077)
    sensors = cpu_sensors()
    memory = psutil.virtual_memory()
    budget = min(30_000_000_000, memory.total)
    reserve = 2_000_000_000
    headroom = min(memory.available, budget - (memory.total - memory.available)) - reserve
    if headroom < 2_000_000_000 or max(x["celsius"] for x in sensors.values()) >= 100:
        raise RuntimeError("Insufficient shared RAM or CPU not cool enough to start")
    start = time.monotonic()
    events, samples = [], []
    process = None
    stopped = False
    reduced = False
    hard_stops = 0
    cool_since = None
    previous_temperature = max(x["celsius"] for x in sensors.values())
    previous_elapsed = 0.0
    known_containers = set()
    paused_containers = set()
    peak_tree_rss = 0
    exit_reason = "completed"
    old_handlers = {}

    def interrupted(signum, _frame):
        raise InterruptedError(f"Supervisor interrupted by signal {signum}")

    for signum in (signal.SIGTERM, signal.SIGINT):
        old_handlers[signum] = signal.signal(signum, interrupted)
    psutil.cpu_percent()
    try:
        with (root / "stdout.log").open("xb") as stdout, (root / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                preexec_fn=lambda: os.sched_setaffinity(
                    0, set(sorted(os.sched_getaffinity(0))[: args.initial_cpus])
                ),
            )
            while process.poll() is None:
                sensors = cpu_sensors()
                temperature = max(x["celsius"] for x in sensors.values())
                memory = psutil.virtual_memory()
                used = memory.total - memory.available
                elapsed = time.monotonic() - start
                rate = (temperature - previous_temperature) / max(elapsed - previous_elapsed, 0.1)
                rapid_rise = temperature >= 100 and rate >= 5
                previous_temperature, previous_elapsed = temperature, elapsed
                try:
                    parent = psutil.Process(process.pid)
                    children = parent.children(recursive=True)
                    rss = sum(p.memory_info().rss for p in [parent, *children] if p.is_running())
                except psutil.Error:
                    rss = 0
                peak_tree_rss = max(peak_tree_rss, rss)
                samples.append(
                    {
                        "elapsed_seconds": elapsed,
                        "cpu_max_celsius": temperature,
                        "cpu_readings_celsius": {
                            s["label"]: s["celsius"] for s in sensors.values()
                        },
                        "temperature_rise_celsius_per_second": rate,
                        "system_cpu_percent": psutil.cpu_percent(),
                        "system_used_bytes_total_minus_available": used,
                        "mem_available_bytes": memory.available,
                        "process_tree_rss_bytes": rss,
                        "paused": stopped,
                    }
                )
                # Check explicit names only. New containers are discovered while
                # the child starts them; CPU enforcement also covers their cgroups.
                if len(samples) % 3 == 1:
                    for name in args.containers:
                        if (
                            name not in known_containers
                            and podman("container", name, "exists").returncode == 0
                        ):
                            known_containers.add(name)
                pressure = used >= budget - 500_000_000 or memory.available < reserve
                if (temperature >= 100 or rapid_rise or pressure) and not stopped:
                    os.killpg(process.pid, signal.SIGSTOP)
                    for name in known_containers:
                        if podman("pause", name).returncode == 0:
                            paused_containers.add(name)
                    stopped = True
                    cool_since = None
                    hard_stops += int(temperature >= 100)
                    events.append(
                        {
                            "seconds": elapsed,
                            "action": "PAUSE",
                            "temperature": temperature,
                            "memory_pressure": pressure,
                            "rapid_temperature_rise": rapid_rise,
                        }
                    )
                    if hard_stops >= 1:
                        raise RuntimeError(
                            "CPU thermal hard stop; ending workload without automatic resume"
                        )
                elif (
                    stopped
                    and temperature < 100
                    and used < budget - 2_000_000_000
                    and memory.available > reserve
                ):
                    if cool_since is None:
                        cool_since = elapsed
                    if elapsed - cool_since >= 3:
                        for name in list(paused_containers):
                            podman("unpause", name)
                        paused_containers.clear()
                        os.killpg(process.pid, signal.SIGCONT)
                        stopped = False
                        events.append(
                            {"seconds": elapsed, "action": "RESUME", "temperature": temperature}
                        )
                elif stopped:
                    cool_since = None
                if temperature >= 100 and not reduced:
                    for name in known_containers:
                        podman("update", name, "--cpus=1")
                    # Kernel scheduler affinity also limits a CPU-bound child or
                    # image unpacker; no dependency on cooperative worker checks.
                    try:
                        for child in [
                            psutil.Process(process.pid),
                            *psutil.Process(process.pid).children(recursive=True),
                        ]:
                            allowed = child.cpu_affinity()
                            child.cpu_affinity(allowed[:1])
                            # Linux affinity is per-thread. Existing BLAS threads
                            # must also be constrained, not only their leader.
                            for task in Path(f"/proc/{child.pid}/task").glob("*"):
                                try:
                                    os.sched_setaffinity(int(task.name), set(allowed[:1]))
                                except (OSError, ValueError):
                                    pass
                    except psutil.Error:
                        pass
                    reduced = True
                    events.append(
                        {"seconds": elapsed, "action": "REDUCE_LOAD", "temperature": temperature}
                    )
                if elapsed > args.max_seconds:
                    exit_reason = "wall_time_limit"
                    raise RuntimeError("P0 supervised workload exceeded wall-time")
                time.sleep(args.sample_seconds)
            returncode = process.returncode
    except BaseException:
        exit_reason = "supervisor_error_or_interruption"
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL if stopped else signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        returncode = process.returncode if process is not None else -1
        raise
    finally:
        if exit_reason == "completed":
            for name in paused_containers:
                podman("unpause", name)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        report = {
            "cpu_sensor_sources": sensors,
            "shared_system_budget_bytes": budget,
            "initial_ai_headroom_bytes_after_reserve": headroom,
            "reserve_bytes": reserve,
            "warning_celsius": 75,
            "reduce_load_celsius": 72,
            "hard_pause_celsius": 80,
            "proactive_pause_celsius": 74,
            "resume_below_celsius": 70,
            "minimum_continuously_cool_seconds": 3,
            "abort_after_hard_stops": 1,
            "rapid_rise_pause": {"minimum_celsius": 68, "minimum_celsius_per_second": 5},
            "containers_left_paused_on_error": sorted(paused_containers)
            if exit_reason != "completed"
            else [],
            "sample_seconds": args.sample_seconds,
            "initial_cpu_affinity_count": args.initial_cpus,
            "supervisor_source_sha256": __import__("hashlib")
            .sha256(Path(__file__).read_bytes())
            .hexdigest(),
            "samples": len(samples),
            "events": events,
            "wall_seconds": time.monotonic() - start,
            "returncode": returncode,
            "exit_reason": exit_reason,
            "peak_process_tree_rss_bytes": peak_tree_rss,
            "cpu_temperature_min": min((s["cpu_max_celsius"] for s in samples), default=None),
            "cpu_temperature_mean": sum(s["cpu_max_celsius"] for s in samples) / len(samples)
            if samples
            else None,
            "cpu_temperature_max": max((s["cpu_max_celsius"] for s in samples), default=None),
            "peak_system_used_bytes": max(
                (s["system_used_bytes_total_minus_available"] for s in samples), default=None
            ),
            "system_cpu_percent_mean": sum(s["system_cpu_percent"] for s in samples) / len(samples)
            if samples
            else None,
            "system_cpu_percent_max": max((s["system_cpu_percent"] for s in samples), default=None),
            "limits": "Reactive sensor sampling; spikes cannot be absolutely excluded; tree RSS excludes detached container processes; system RAM covers all workloads",
        }
        (root / "resource-report.json").write_text(json.dumps(report, indent=2) + "\n")
        with (root / "samples.jsonl").open("w") as stream:
            for sample in samples:
                stream.write(json.dumps(sample) + "\n")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())

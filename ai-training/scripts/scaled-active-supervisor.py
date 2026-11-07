#!/usr/bin/env python3
"""Existing cgroup/watchdog supervisor with a rolling ACTIVE-time thermal window."""

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def active_policy(base):
    class ActiveWindow(base.HeatWindow):
        def __init__(self):
            super().__init__()
            self.active_intervals = deque()
            self.active_clock = 0

        def add(self, now, temperature, paused):
            previous = self.previous
            result = super().add(now, temperature, paused)
            if previous and not previous[2]:
                duration = now - previous[0]
                self.active_intervals.append(
                    (self.active_clock, self.active_clock + duration, previous[1])
                )
                self.active_clock += duration
            cutoff = self.active_clock - 300
            while self.active_intervals and self.active_intervals[0][1] <= cutoff:
                self.active_intervals.popleft()
            area = duration = 0
            for a, b, value in self.active_intervals:
                dt = b - max(a, cutoff)
                area += value * dt
                duration += dt
            result["wall_rolling_300s_c"] = result["rolling_300s_c"]
            result["rolling_300s_c"] = area / duration if duration else temperature
            result["rolling_window_basis"] = (
                "ACTIVE_SECONDS_ONLY; paused/idle cannot cool this average"
            )
            result["active_window_seconds"] = duration
            return result

    return ActiveWindow


class ServiceWatchdog:
    def __init__(self, unit):
        self.unit = unit

    def healthy(self):
        q = subprocess.run(
            ["systemctl", "--user", "show", self.unit, "-p", "ActiveState", "-p", "SubState"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        info = dict(line.split("=", 1) for line in q.stdout.splitlines() if "=" in line)
        return info.get("ActiveState") == "active" and info.get("SubState") == "running"

    def wait(self, timeout=None):
        until = time.monotonic() + (timeout or 30)
        while self.healthy():
            if time.monotonic() >= until:
                raise subprocess.TimeoutExpired(self.unit, timeout)
            time.sleep(0.1)
        return 0

    def kill(self):
        subprocess.run(["systemctl", "--user", "stop", self.unit], capture_output=True, timeout=5)


def start_external_watchdog(command):
    unit = "idps-normalization-watchdog-" + str(os.getpid()) + "-" + str(time.time_ns())[-7:]
    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--quiet",
            "--unit",
            unit,
            "--service-type=exec",
            "-p",
            "CPUQuota=20%",
            "-p",
            "MemoryMax=128M",
            "-p",
            "MemorySwapMax=0",
            *command,
        ],
        capture_output=True,
        check=True,
        timeout=10,
    )
    monitor = ServiceWatchdog(unit)
    assert monitor.healthy(), "Independent watchdog did not start"
    return monitor


def run(args):
    g = module("integration-guard")
    original_ctl = g.ctl

    def safe_ctl(*items, **kw):
        # Some systemd versions reject fractional quota precision after repeated halving.
        fixed = []
        for item in items:
            if item.startswith("CPUQuota="):
                item = (
                    "CPUQuota="
                    + str(max(1, math.floor(float(item.split("=")[1].rstrip("%")))))
                    + "%"
                )
            fixed.append(item)
        return original_ctl(*fixed, **kw)

    g.ctl = safe_ctl
    original_popen = subprocess.Popen
    monitors = []

    def popen(command, **kw):
        if (
            isinstance(command, list)
            and command[0] == sys.executable
            and "--action" in command
            and "watchdog" in command
        ):
            monitor = start_external_watchdog(command)
            monitors.append(monitor)
            Path(args.output, "external-watchdog.json").write_text(
                json.dumps({"unit": monitor.unit, "independent_systemd_service": True}) + "\n"
            )
            return monitor
        return original_popen(command, **kw)

    g.subprocess.Popen = popen

    def sensor():
        if monitors and not monitors[0].healthy():
            raise RuntimeError("Independent watchdog service lost")
        return g.cpu_reading()

    original = g.rolling.action
    g.rolling.HeatWindow = active_policy(g.rolling)

    def action(temp, rolling, rate, paused, cool, pressure=False, cutoff=90):
        if rolling >= 80:
            Path(args.output, "active-thermal-stop.json").write_text(
                json.dumps(
                    {
                        "reason": "ACTIVE_ROLLING_LIMIT_80C",
                        "rolling_active_300s_C": rolling,
                        "instant_C": temp,
                    }
                )
                + "\n"
            )
            return "KILL"  # No automatic restart or idle-time dilution at limit.
        if paused and temp < 70 and rolling < 80 and cool >= 15 and not pressure:
            return "THAW"
        return original(temp, rolling, rate, paused, cool, pressure, cutoff)

    g.rolling.action = action
    try:
        g.run(
            args.command[1:] if args.command[:1] == ["--"] else args.command,
            args.output,
            quota=args.quota,
            sensor=sensor,
            max_seconds=args.max_seconds,
            policy="rolling",
            memory_gib=args.memory_gib,
            cutoff=90,
        )
    except BaseException as exc:
        if args.experiment_root:
            from idps_ai.common import atomic_json

            status_path = Path(args.experiment_root) / "status.json"
            previous = json.loads(status_path.read_text()) if status_path.exists() else {}
            resource_path = Path(args.output) / "resource-status.json"
            resource = json.loads(resource_path.read_text()) if resource_path.exists() else {}
            atomic_json(
                status_path,
                {
                    **previous,
                    "state": resource.get("status", "FAILED"),
                    "error": str(exc),
                    "last_heartbeat": time.time(),
                    "finished_at": time.time(),
                    "thermal": resource.get("thermal"),
                },
            )
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--experiment-root")
    p.add_argument("--quota", type=int, default=100)
    p.add_argument("--memory-gib", type=float, default=4)
    p.add_argument("--max-seconds", type=int, default=7200)
    p.add_argument("command", nargs=argparse.REMAINDER)
    run(p.parse_args())

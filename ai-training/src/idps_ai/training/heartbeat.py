"""Atomic cross-process heartbeat with same-boot monotonic age and PID identity."""

import json
import os
import threading
import time
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json


def process_identity(pid):
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        fields = text[text.rfind(")") + 2 :].split()
        if fields[0] in {"Z", "X"}:
            return None
        return int(fields[19])  # /proc stat field22, starttime since boot
    except (OSError, ValueError, IndexError):
        return None


def boot_identity():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


class SupervisorHeartbeat:
    def __init__(self, path):
        self.path = Path(path)
        self.pid = os.getpid()
        self.start = process_identity(self.pid)
        self.boot = boot_identity()
        self.sequence = 0
        self.loop_ns = time.monotonic_ns()
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _write(self):
        with self.lock:
            self.sequence += 1
            value = {
                "version": 1,
                "pid": self.pid,
                "start_ticks": self.start,
                "boot_id": self.boot,
                "sequence": self.sequence,
                "monotonic_ns": time.monotonic_ns(),
                "main_loop_monotonic_ns": self.loop_ns,
                "wall_time": time.time(),
            }
        atomic_json(self.path, value)

    def start_writer(self):
        self._write()
        self.thread.start()

    def pulse(self):
        if self.error:
            raise PipelineError("Supervisor heartbeat writer failed") from self.error
        with self.lock:
            self.loop_ns = time.monotonic_ns()

    def _loop(self):
        try:
            while not self.done.wait(0.25):
                self._write()
        except BaseException as exc:
            self.error = exc

    def close(self):
        self.done.set()
        self.thread.join(timeout=2)


class HeartbeatMonitor:
    def __init__(self, path, expected_pid, timeout=3):
        self.path = Path(path)
        self.expected_pid = expected_pid
        self.timeout = timeout
        self.boot = boot_identity()
        self.failures = 0
        self.last_sequence = None

    def check(self):
        value = {}
        reason = "HEARTBEAT_UNREADABLE"
        alive = False
        age = loop_age = None
        observed_mtime = None
        try:
            # Atomic writer guarantees this is a complete old or complete new record.
            with self.path.open() as stream:
                value = json.load(stream)
                if not isinstance(value, dict):
                    value = {}
                    raise ValueError("Heartbeat must be a record")
                if (
                    any(
                        type(value.get(k)) is not int
                        for k in [
                            "pid",
                            "start_ticks",
                            "sequence",
                            "monotonic_ns",
                            "main_loop_monotonic_ns",
                        ]
                    )
                    or value["pid"] <= 0
                    or value["sequence"] < 1
                ):
                    raise ValueError("Invalid heartbeat schema")
                observed_mtime = os.fstat(stream.fileno()).st_mtime
            observed_pid = value["pid"]
            identity = process_identity(observed_pid)
            alive = (
                identity is not None
                and identity == value["start_ticks"]
                and observed_pid == self.expected_pid
            )
            now_ns = time.monotonic_ns()  # sample AFTER the immutable record was read
            age = (now_ns - value["monotonic_ns"]) / 1e9
            loop_age = (now_ns - value["main_loop_monotonic_ns"]) / 1e9
            if value["version"] != 1 or value["boot_id"] != self.boot:
                reason = "BOOT_OR_SCHEMA_MISMATCH"
            elif not alive:
                reason = "SUPERVISOR_DEAD_OR_PID_REUSED"
            elif min(age, loop_age) < -0.001:
                reason = "MONOTONIC_FUTURE_INVALID"
            elif age > self.timeout:
                reason = "HEARTBEAT_STALE"
            elif loop_age > self.timeout:
                reason = "SUPERVISOR_LOOP_STALE"
            elif self.last_sequence is not None and value["sequence"] < self.last_sequence:
                reason = "HEARTBEAT_SEQUENCE_REVERSED"
            else:
                reason = "HEALTHY"
            self.last_sequence = value["sequence"]
        except (OSError, ValueError, KeyError, TypeError):
            now_ns = time.monotonic_ns()
        healthy = reason == "HEALTHY"
        self.failures = 0 if healthy else self.failures + 1
        return {
            "healthy": healthy,
            "decision_reason": reason,
            "current_wall_time": time.time(),
            "current_monotonic_ns": now_ns,
            "observed_wall_time": value.get("wall_time"),
            "observed_monotonic_ns": value.get("monotonic_ns"),
            "observed_file_mtime": observed_mtime,
            "age_seconds": age,
            "main_loop_age_seconds": loop_age,
            "supervisor_pid": value.get("pid", self.expected_pid),
            "pid_alive_and_identity_matches": alive,
            "consecutive_failure_count": self.failures,
            "sequence": value.get("sequence"),
            "timeout_seconds": self.timeout,
        }

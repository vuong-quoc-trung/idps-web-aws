#!/usr/bin/env python3
"""Systemd-owned supervisor for the existing worker, not a second inference pipeline."""
import argparse
from datetime import datetime
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def latest(path):
    try:
        with path.open("rb") as f:
            f.seek(max(0, path.stat().st_size - 16384))
            lines = f.read().splitlines()
        for line in reversed(lines):
            try:
                value = json.loads(line)
                if value.get("kind") == "heartbeat":
                    return value
            except (ValueError, TypeError):
                pass
    except OSError:
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--socket", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--socket-mode", choices=["600", "620"], default="620")
    args = p.parse_args()
    thermal = load(ROOT / "ai-training/scripts/p0-thermal-run.py", "host_thermal")
    # Fail closed without a reliable sensor; do not auto-restart a thermal stop.
    if max(x["celsius"] for x in thermal.cpu_sensors().values()) >= 75:
        return 78
    started = time.time()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = subprocess.Popen([
        sys.executable, str(ROOT / "scripts/ai-shadow-worker.py"),
        "--bundle", str(args.bundle), "--socket", str(args.socket),
        "--output", str(args.output), "--socket-mode", args.socket_mode,
    ], start_new_session=True)
    reason = "worker_exit"
    code = 1
    try:
        while child.poll() is None and not stopping:
            try:
                temp = max(x["celsius"] for x in thermal.cpu_sensors().values())
                heartbeat = latest(args.output)
                stamp = datetime.fromisoformat(heartbeat["observed_at"]).timestamp() if heartbeat else 0
                if temp >= 90:
                    reason, code = "thermal_stop", 78
                    break
                if heartbeat and stamp >= started and heartbeat.get("status") in {
                    "THERMAL_STOP", "RAM_STOP", "THERMAL_CONTROL_NOT_VERIFIED"
                }:
                    reason, code = heartbeat["status"], 78
                    break
                if time.time() - started > 30 and time.time() - stamp > 10:
                    reason, code = "heartbeat_stale", 1
                    break
            except Exception:
                reason, code = "supervision_unverified", 78
                break
            time.sleep(.5)
        if stopping:
            reason, code = "operator_stop", 0
        elif child.poll() is not None:
            heartbeat = latest(args.output)
            if heartbeat and datetime.fromisoformat(heartbeat["observed_at"]).timestamp() >= started and heartbeat.get("status") in {"THERMAL_STOP", "RAM_STOP", "THERMAL_CONTROL_NOT_VERIFIED"}:
                code = 78
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
        print(json.dumps({"supervisor": reason, "exit": code}), flush=True)
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("AI host supervisor unavailable; no raw data logged", flush=True)
        raise SystemExit(78)

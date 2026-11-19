"""Run the finite R34 study through the existing exclusive Resource Adapter."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256, load_json

HERE = Path(__file__).resolve().parent
# All running stages are separate bounded, guardian-owned systemd workers.
STAGES = (
    ("http", "TRAIN", 1700, 90, 4096, "http_study.py", (), "http-pilot-result.json"),
    ("local", "SERVE", 120, 75, 768, "local_probe.py", (), "local-readback.json"),
    ("download", "DATA", 3200, 75, 1536, "acquire.py", (), "source.json"),
    ("extract", "DATA", 1200, 90, 1536, "login_data.py", ("extract",), "raw-index.json"),
    ("project", "DATA", 900, 90, 1536, "login_data.py", ("project",), "projection.json"),
    ("train", "TRAIN", 700, 85, 3072, "login_study.py", ("train",), "login-lock.json"),
    ("transfer", "EVALUATE", 480, 85, 3072, "login_study.py", ("transfer",), "login-transfer.json"),
)


def run(folder, start):
    folder = folder.resolve()
    folder.mkdir(mode=0o700, exist_ok=True)
    status = folder / "study-status.json"
    from fcntl import LOCK_EX, LOCK_NB, flock

    with (folder / ".coordinator.lock").open("a") as lock:
        flock(lock, LOCK_EX | LOCK_NB)
        for i, (name, phase, seconds, cpu, mem, script, args, artifact) in enumerate(STAGES):
            attempt = folder / ("adapter-" + name)
            result = attempt / "result.json"
            output = folder / artifact
            if i < start and not result.exists():
                atomic_json(status, {"state": "OBSERVING", "stage": name, "pid": os.getpid()})
                until = time.monotonic() + seconds + 90
                while not result.exists() and time.monotonic() < until:
                    time.sleep(2)
            if result.exists():
                receipt = load_json(result)
                if receipt.get("reason") != "COMPLETED" or not receipt.get("cleanup_verified"):
                    atomic_json(status, {"state": "BLOCKED", "stage": name, "receipt": receipt})
                    raise RuntimeError(f"{name}: {receipt.get('reason')}, see {result}")
                if not output.is_file():
                    raise ValueError(f"{name}: missing committed output")
                continue
            if attempt.exists() or i < start:
                raise RuntimeError(f"{name}: prior stage is in progress or lacks reconciliation")
            command = [
                sys.executable,
                "-B",
                "-m",
                "idps_ai.training.resource_adapter",
                "--attempt",
                str(attempt),
                "--phase",
                phase,
                "--seconds",
                str(seconds),
                "--cpu-percent",
                str(cpu),
                "--memory-mib",
                str(mem),
                "--",
                sys.executable,
                "-B",
                str(HERE / script),
                *args,
                str(folder),
            ]
            atomic_json(
                status,
                {"state": "RUNNING", "stage": name, "pid": os.getpid(), "started": time.time()},
            )
            subprocess.run(command, check=False)
            receipt = load_json(result)
            if (
                receipt["reason"] != "COMPLETED"
                or not receipt["cleanup_verified"]
                or not output.is_file()
            ):
                atomic_json(status, {"state": "BLOCKED", "stage": name, "receipt": receipt})
                raise RuntimeError(f"{name}: incomplete, inspect {result}")
        atomic_json(
            status,
            {
                "state": "COMPLETED",
                "pid": os.getpid(),
                "completed": time.time(),
                "outputs": {s[0]: file_sha256(folder / s[-1]) for s in STAGES},
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--from-stage", choices=[s[0] for s in STAGES], default=STAGES[0][0])
    args = parser.parse_args()
    os.umask(0o077)
    run(args.folder, [s[0] for s in STAGES].index(args.from_stage))

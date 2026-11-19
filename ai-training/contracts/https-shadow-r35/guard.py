"""One bounded delegated user unit for an R35 training or acceptance stage."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-training/src"))
from idps_ai.training.delegated_guard import UNIT_PROPERTIES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    command = parser.parse_args().command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("Worker command required")
    properties = [
        *UNIT_PROPERTIES,
        "CPUQuota=100%",
        "MemoryMax=2G",
        "MemoryHigh=1700M",
        "MemorySwapMax=0",
        "TasksMax=160",
        "RuntimeMaxSec=240",
    ]
    args = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        "--unit=idps-r35-" + uuid.uuid4().hex,
        "--working-directory=" + str(ROOT),
        "--setenv=PYTHONPATH=" + str(ROOT / "ai-training/src"),
    ]
    for prop in properties:
        args.extend(["-p", prop])
    for key in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        args.append("--setenv=" + key + "=1")
    return subprocess.run(
        args + [sys.executable, "-B", "-m", "idps_ai.training.delegated_guard", "--", *command]
    ).returncode


if __name__ == "__main__":
    sys.exit(main())

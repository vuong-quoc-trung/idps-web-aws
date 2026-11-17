"""Run the bounded R24 development pilot and resume verifier under systemd."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from r18_data import check, read, status

from idps_ai.common import atomic_json
from idps_ai.training.checkpoint import RunLock


def run(out, etl_attempt):
    deadline = time.monotonic() + 420
    etl = etl_attempt / "result.json"
    while not etl.exists() and time.monotonic() < deadline:
        time.sleep(1)
    check(
        etl.exists() and read(etl)["reason"] == "COMPLETED" and read(etl)["cleanup_verified"],
        "ETL did not successfully close its resource scope",
    )
    with RunLock(out / "supervisor"):
        for phase in ("pilot", "verify"):
            attempt = out / f"resource-{phase}"
            stage = attempt / "result.json"
            if stage.exists():
                prior = read(stage)
                check(
                    prior["reason"] == "COMPLETED" and prior["cleanup_verified"],
                    "Prior phase requires explicit diagnosis",
                )
                continue
            status(out, f"R24_{phase.upper()}")
            code = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "idps_ai.training.resource_adapter",
                    "--attempt",
                    str(attempt),
                    "--phase",
                    "TRAIN",
                    "--seconds",
                    "180",
                    "--cpu-percent",
                    "100",
                    "--memory-mib",
                    "4096",
                    "--",
                    sys.executable,
                    "-B",
                    str(Path(__file__).with_name("r24_pilot.py")),
                    phase,
                    str(out),
                ],
                check=False,
            ).returncode
            result = read(stage) if stage.exists() else {}
            if code or result.get("reason") != "COMPLETED" or not result.get("cleanup_verified"):
                atomic_json(
                    out / "status.json",
                    {
                        "state": "BLOCKED",
                        "phase": phase,
                        "reason": result.get("reason", "ADAPTER_RESULT_MISSING"),
                    },
                )
                return 1
        atomic_json(
            out / "status.json",
            {
                "state": "PILOT_COMPLETED",
                "pilot": "PASS",
                "resume": read(out / "resume.json")["state"],
                "final_training_started": False,
            },
        )
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("etl_attempt", type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.out, args.etl_attempt))

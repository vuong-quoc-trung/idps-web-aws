# isort: skip_file

"""Finite independent supervisor over existing Resource Adapter, no HTTP dispatcher."""

import argparse
import os
import subprocess
import sys
import time

from common import HERE, atomic_json, check, file_sha256, read, status

PHASES = {
    "prepare": [("precalibrate", "EVALUATE", 300)],
    "train": [("continue_b", "TRAIN", 600)],
    "evaluate": [("evaluate", "EVALUATE", 600)],
    "verify": [("verify", "EVALUATE", 600)],
    "diagnose": [("diagnose", "EVALUATE", 600)],
    "native": [("native", "DATA", 300)],
    "rust": [("rust_tests", "EVALUATE", 300)],
    "replay": [("replay", "EVALUATE", 300)],
    "live": [("live", "EVALUATE", 120)],
    "warm": [("warm", "EVALUATE", 120)],
    "compose": [("compose_verification", "EVALUATE", 120)],
    "allocation": [("allocation_probe", "EVALUATE", 120)],
}
PHASES["finish"] = [*PHASES["replay"], *PHASES["diagnose"], *PHASES["native"], *PHASES["live"]]


def recoverable_software_pause(result, trip, health):
    """A separate fresh attempt needs complete trip proof; never guess watchdog cause."""
    return (
        result.get("reason") == "THERMAL_EMERGENCY"
        and result.get("cleanup_verified") is True
        and trip.get("software_threshold_only") is True
        and trip.get("hardware_alarm") is False
        and type(trip.get("temperature_c")) in (int, float)
        and trip["temperature_c"] > 100
        and health.get("stable_samples", 0) >= 5
        and health.get("all_readings_fresh") is True
        and health.get("hardware_alarm") is False
        and type(health.get("maximum_c")) in (int, float)
        and 0 < health["maximum_c"] <= 90
    )


def run(out, kind, attempt_suffix=""):
    from idps_ai.training.checkpoint import RunLock

    with RunLock(out / "supervisor-lock"):
        for name, phase, seconds in PHASES[kind]:
            worker = HERE / f"{name}.py"
            check(worker.is_file(), "Missing phase implementation")
            label = name + attempt_suffix
            attempt = out / f"resource-{label}"
            check(
                not attempt.exists(),
                "Phase already attempted; reconcile its result rather than duplicate",
            )
            request = {
                "kind": kind,
                "phase": phase,
                "worker_sha256": file_sha256(worker),
                "pid": os.getpid(),
                "invocation": os.environ.get("INVOCATION_ID"),
                "started": time.time(),
            }
            atomic_json(out / f"supervisor-{label}.json", request)
            status(
                out,
                "RUNNING",
                name.upper(),
                pid=os.getpid(),
                checkpoint=str(out / "training/model/latest.json"),
            )
            cpu = "100" if name == "rust_tests" else "400"
            allocation = (
                []
                if name == "rust_tests"
                else ["--allocation-evidence", str(out / f"allocation-{phase.lower()}.json")]
            )
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
                cpu,
                "--memory-mib",
                "4096",
                "--blas-threads",
                "1" if name == "rust_tests" else "4",
                *allocation,
                "--",
                sys.executable,
                "-B",
                str(worker),
                str(out),
            ]
            with (out / f"{label}.log").open("xb") as log:
                process = subprocess.run(
                    command, stdout=log, stderr=subprocess.STDOUT, timeout=seconds + 60, check=False
                )
            result = (
                read(attempt / "result.json")
                if (attempt / "result.json").exists()
                else {"reason": "MISSING_RESULT"}
            )
            atomic_json(
                out / f"supervisor-{label}.json",
                request
                | {"finished": time.time(), "exit_code": process.returncode, "result": result},
            )
            if (
                process.returncode
                or result.get("reason") != "COMPLETED"
                or result.get("cleanup_verified") is not True
            ):
                status(
                    out, "BLOCKED", name.upper(), reason=result.get("reason"), automatic_retry=False
                )
                return 1
            status(out, "COMPLETED", name.upper(), resource_adapter="COMPLETED", cleanup=True)
    return 0


if __name__ == "__main__":
    from pathlib import Path

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("kind", choices=PHASES)
    parser.add_argument("--attempt-suffix", choices=("-v2", "-v3"), default="")
    args = parser.parse_args()
    raise SystemExit(run(args.out, args.kind, args.attempt_suffix))

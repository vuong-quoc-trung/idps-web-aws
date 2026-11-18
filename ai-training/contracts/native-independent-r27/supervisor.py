"""Finite serial owned phases; safety failures never restart automatically."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from plan import FAMILIES

from idps_ai.common import atomic_json, file_sha256
from idps_ai.training.checkpoint import RunLock

HERE = Path(__file__).resolve().parent


def finish(root, reuse=False):
    """Finalize fresh results, or reuse committed admission without any HTTP path."""
    if reuse:
        checkpoint = json.loads((root / "checkpoint.json").read_text())
        complete = checkpoint["completed"]
        if {r["family"] for r in complete} != set(FAMILIES) or any(
            r["state"] != "CAPTURED" or r["exit_code"] != 0 for r in complete
        ):
            raise ValueError("Incomplete acquisition cannot use offline-only finalization")
        ledger_sha = {}
        for family in FAMILIES:
            directory = root / family
            receipt = directory / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl"
            expected = json.loads((directory / "checkpoint.json").read_text())["ledger_sha256"]
            if file_sha256(receipt) != expected:
                raise ValueError("Committed receipt changed")
            ledger_sha[family] = expected
        for file, key in (
            ("admission.json", "admission_sha256"),
            ("native-source-role-registry.json", "role_registry_sha256"),
        ):
            if file_sha256(root / file) != checkpoint[key]:
                raise ValueError("Committed admission/role state changed")
    elif not managed(root, "admit", 120, 1024, "admit"):
        atomic_json(
            root / "status.json",
            {"state": "BLOCKED", "phase": "ADMISSION", "automatic_retry": False},
        )
        return 1
    for name in ("information", "finalize"):
        subprocess.run(
            [sys.executable, "-B", str(HERE / (name + ".py")), str(root)], check=True, timeout=30
        )
    if reuse:
        if any(
            file_sha256(root / family / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl") != sha
            for family, sha in ledger_sha.items()
        ):
            raise ValueError("Offline finalization modified a receipt")
        atomic_json(
            root / "offline-resume-proof.json",
            {
                "mode": "COMMITTED_OFFLINE_FINALIZATION_ONLY",
                "HTTP_dispatched": 0,
                "receipt_sha256_unchanged": ledger_sha,
                "admission_reused": True,
                "request_replay_allowed": False,
                "completed_unix": time.time(),
            },
        )
    return 0


def managed(root, name, seconds, memory, script):
    attempt = root / ("resource-" + name)
    if attempt.exists():
        raise ValueError("Phase already attempted; reconcile existing checkpoint")
    command = [
        sys.executable,
        "-B",
        "-m",
        "idps_ai.training.resource_adapter",
        "--attempt",
        str(attempt),
        "--phase",
        "EVALUATE",
        "--seconds",
        str(seconds),
        "--cpu-percent",
        "100",
        "--memory-mib",
        str(memory),
        "--",
        sys.executable,
        "-B",
        str(HERE / (script + ".py")),
        str(root),
    ]
    with (root / (name + ".log")).open("xb") as stream:
        result = subprocess.run(
            command, stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=seconds + 40
        )
    receipt = json.loads((attempt / "result.json").read_text())
    return (
        result.returncode == 0 and receipt["reason"] == "COMPLETED" and receipt["cleanup_verified"]
    )


def run(args):
    root = args.output
    with RunLock(root / "supervisor-lock"):
        if args.finalize_existing:
            return finish(root, reuse=True)
        started = time.monotonic()
        completed = []
        atomic_json(
            root / "supervisor.json",
            {
                "pid": os.getpid(),
                "invocation": os.environ.get("INVOCATION_ID"),
                "run_id": root.name,
                "started_unix": time.time(),
                "retry_policy": "No auto restart of safety failure; all HTTP namespaces fresh",
            },
        )
        for name, seconds, memory in (("build", 180, 768), ("verify", 90, 512)):
            atomic_json(
                root / "status.json",
                {"state": "RUNNING", "phase": name, "completed_families": completed},
            )
            if not managed(root, name, seconds, memory, name):
                atomic_json(
                    root / "status.json",
                    {"state": "BLOCKED", "phase": name, "automatic_retry": False},
                )
                return 1
        for family in FAMILIES:
            directory = root / family
            directory.mkdir(mode=0o700)
            atomic_json(
                root / "status.json",
                {
                    "state": "RUNNING",
                    "phase": "CAPTURE",
                    "family": family,
                    "completed_families": completed,
                    "remaining_families": len(FAMILIES) - len(completed),
                    "ETA_seconds": 70 * (len(FAMILIES) - len(completed)),
                },
            )
            command = [
                sys.executable,
                "-B",
                str(HERE / "capture.py"),
                "supervise",
                str(directory),
                str(args.iso),
                str(args.h2),
                str(args.numpy),
                "--family",
                family,
            ]
            with (root / (family + ".log")).open("xb") as stream:
                process = subprocess.run(
                    command, stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=300
                )
            status = (
                json.loads((directory / "status.json").read_text())
                if (directory / "status.json").exists()
                else {}
            )
            completed.append(
                {
                    "family": family,
                    "state": status.get("state", "BLOCKED"),
                    "exit_code": process.returncode,
                }
            )
            atomic_json(
                root / "checkpoint.json",
                {"phase": "CAPTURE", "completed": completed, "resend_committed": False},
            )
            # Unknown/safety termination ends compute. An application/Oracle
            # failure is preserved; a distinct family may still be inspected.
            reason = status.get("adapter", {}).get("reason")
            if reason not in ("COMPLETED", "WORKER_FAILED"):
                atomic_json(
                    root / "status.json",
                    {
                        "state": "BLOCKED",
                        "reason": reason,
                        "completed": completed,
                        "automatic_retry": False,
                    },
                )
                return 1
        atomic_json(
            root / "status.json",
            {
                "state": "ACQUIRED",
                "phase": "OFFLINE_ADMISSION_PENDING",
                "completed": completed,
                "elapsed_seconds": time.monotonic() - started,
                "HTTP_replay_allowed": False,
            },
        )
        return finish(root)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    for name in ("output", "iso", "h2", "numpy"):
        parser.add_argument(name, type=lambda p: Path(p).resolve(strict=True))
    parser.add_argument(
        "--finalize-existing",
        action="store_true",
        help="Offline committed-results recovery only; never boot or dispatch HTTP",
    )
    args = parser.parse_args()
    raise SystemExit(run(args))

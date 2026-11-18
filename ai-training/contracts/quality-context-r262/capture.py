"""Finite R262 context-availability capture; reuses R261 acquisition unchanged.

Two campaigns have different sessions/guest boot scopes, but shared policy and
templates: they are NOT two independent lineage components for evaluation.
"""

# isort: skip_file
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "quality-recovery-r261"
sys.path.insert(0, str(PREVIOUS))
spec = importlib.util.spec_from_file_location("r262_native_base", PREVIOUS / "native_capture.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
base = native.base
from idps_ai.common import atomic_json, digest, file_sha256  # noqa: E402
from idps_ai.training.checkpoint import RunLock  # noqa: E402


def roster(index):
    if index != 0:
        raise ValueError("Bounded campaign only")
    return [dict(row, session="r262-" + row["session"]) for row in native.roster(0)]


def extend(root, pins):
    native.extend(root, pins)
    from lab_auth import stage_guest_python

    for name in ("context.py", "collector.py", "session_transport.py"):
        target = stage_guest_python(HERE / name, root, "/lab/" + name)
        pins["/lab/" + name] = file_sha256(target)
    acquire = root / "lab/acquire.py"
    source = base.replace_once(
        acquire.read_text(),
        "    source_integrity.install(t08)\n",
        "    source_integrity.install(t08)\n    import collector, session_transport\n    collector.install(t08)\n    session_transport.install(PILOT)\n",
    )
    acquire.write_text(source)
    pins["/lab/acquire.py"] = file_sha256(acquire)
    timing = root / "bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"
    text = base.replace_once(
        timing.read_text(),
        '            headers = {"X-Request-Id": SPOOF, "Connection": "close"}\n',
        '            headers = {"X-Request-Id": SPOOF, "Connection": "close", "X-Role": "ADMIN", "X-User-Id": "1", "X-Forwarded-For": "203.0.113.55"}\n',
    )
    text = base.replace_once(
        text,
        '                    self.session["cookie"] = cookie["JSESSIONID"].value\n',
        '                    self.session["cookie"] = cookie["JSESSIONID"].value\n'
        '                    self.session["cookie_http_only"] = bool(cookie["JSESSIONID"]["httponly"])\n',
    )
    text = base.replace_once(
        text,
        '                "empty": not body,\n',
        '                "empty": not body,\n'
        '                "continued_http_only_session": bool(previous and previous == self.session.get("cookie") and self.session.get("cookie_http_only")),\n',
    )
    timing.write_text(text)
    pins["/bundle/ai-training/contracts/capture-timing-v1/timing_guest.py"] = file_sha256(timing)


def supervise(args):
    with RunLock(args.output):
        if (args.output / "checkpoint.json").exists():
            raise ValueError("Never resend a committed/attempted capture")
        import zipfile
        import hashlib

        policy = native.r8.POLICY
        policy_source = base.ROOT / ("student-web/backend/src/main/java/" + policy + ".java")
        jar = base.ROOT / "student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar"
        reference = json.loads(
            (native.PARENT.parent / "t09-r8-authorized-20261117/plan.json").read_text()
        )
        with zipfile.ZipFile(jar) as z:
            packaged = hashlib.sha256(z.read("BOOT-INF/classes/" + policy + ".class")).hexdigest()
        if (
            file_sha256(policy_source) != reference["policy_source_sha256"]
            or packaged != reference["packaged_policy_sha256"]
        ):
            raise ValueError("Pinned authorization policy changed")
        plan = {
            "version": "idps-r262-context-availability-capture-v1",
            "run_id": args.output.name,
            "rows": roster(0),
            "max_HTTP_attempts": len(roster(0)),
            "cutoff_ns": 1_000_000_000,
            "guard_ns": 1_000_000,
            "no_training": True,
            "purpose": "NEW_CAUSAL_CONTEXT_RECEIPT_NOT_DUPLICATE_COUNTING",
            "switched_session": args.switch_session,
            "policy_source_sha256": file_sha256(policy_source),
            "packaged_policy_sha256": packaged,
            "privacy": "No credentials/cookies/raw actor IDs in persisted features",
            "oracle_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "source_sha256": {p.name: file_sha256(p) for p in HERE.glob("*.py")},
        }
        atomic_json(args.output / "plan.json", plan)
        atomic_json(
            args.output / "checkpoint.json",
            {"state": "RUNNING", "binding": digest(plan), "committed": 0, "resend": False},
        )
        atomic_json(
            args.output / "status.json",
            {"state": "RUNNING", "phase": "CAPTURE", "planned": len(roster(0))},
        )
        started = time.monotonic()
        attempt, command = base.start(args, 0, 1)
        attempt.parent.mkdir(mode=0o700)
        command[command.index(str(Path(base.__file__).resolve()))] = str(HERE / "capture.py")
        if args.switch_session:
            command += ["--switch-session"]
        result = subprocess.run(command, check=False, timeout=260)
        ledger = attempt / "guest/receipt-ledger.jsonl"
        records = (
            [
                v
                for line in ledger.read_text().splitlines()
                if (v := json.loads(line)).get("kind") == "ATTEMPT"
            ]
            if ledger.exists()
            else []
        )
        adapter = json.loads((attempt / "result.json").read_text())
        state = (
            "CAPTURED"
            if result.returncode == 0 and adapter.get("reason") == "COMPLETED"
            else "BLOCKED"
        )
        atomic_json(
            args.output / "checkpoint.json",
            {
                "state": state,
                "binding": digest(plan),
                "committed": len(records),
                "ledger_sha256": file_sha256(ledger) if ledger.exists() else None,
                "resend": False,
            },
        )
        atomic_json(
            args.output / "status.json",
            {
                "state": state,
                "phase": "RECONCILE_OFFLINE",
                "completed": len(records),
                "planned": len(roster(0)),
                "seconds": time.monotonic() - started,
                "adapter_reason": adapter.get("reason"),
                "cleanup": adapter.get("cleanup_verified"),
            },
        )
        return result.returncode


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("supervise", "worker"))
    for name in ("output", "iso", "h2", "numpy"):
        parser.add_argument(name, type=lambda s: Path(s).resolve(strict=True))
    parser.add_argument("--index", type=int, choices=(0,))
    parser.add_argument("--campaign")
    parser.add_argument("--switch-session", action="store_true")
    args = parser.parse_args()
    if args.switch_session:
        previous_roster = roster

        def roster(index):
            rows = [
                dict(r, session="r262-account-switch")
                for r in previous_roster(index)
                if r["oracle"] != "record"
            ]
            return [dict(r, attempt=i + 1) for i, r in enumerate(rows)]

    base.roster, base.extend = roster, extend
    raise SystemExit(base.worker(args) if args.action == "worker" else supervise(args))

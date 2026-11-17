"""Systemd workers for the Local sidecar and request-time evidence."""

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path

import store
from policy import configured, fetch

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features.request_time import schema
from idps_ai.training import delegated_guard

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / name) for name in ("request-time-v1", "local-shadow-r22")]
from bundle import ONNX, RUST, SCOPE, verify  # noqa: E402
from receiver import Receiver  # noqa: E402

ORT_SHA = "fc44112fbe06d7d689c57e11d3862031f64711007e4ee020f8eed5185fd2c1d3"
FEATURES = ("structure_available", "uri_lexical_available", "query_lexical_available")
BOOT = Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def health(path, **data):
    atomic_json(
        path, {"pid": os.getpid(), "boot_scope": BOOT, "updated_wall_ns": time.time_ns(), **data}
    )


def scorer(args):
    root = args.state
    manifest = verify(root / "bundle")
    binary, ort = root / "uri76-shadow", root / "ort.so"
    if file_sha256(binary) != RUST or file_sha256(ort) != ORT_SHA:
        raise ValueError("Inference dependency integrity mismatch")
    path = args.socket
    # RuntimeDirectory cleanup is owned by systemd. Refuse an unexpected
    # existing socket instead of unlinking a potentially live listener.
    if path.exists() or path.is_symlink():
        raise ValueError("Unexpected scorer socket")
    ready_by = time.monotonic() + 10
    last = 0
    status = root / "scorer-health.json"
    base = {
        "model_version": "uri76-swiglu-dev-v1",
        "model_sha256": ONNX,
        "threshold": manifest["tuning_calibration"]["threshold"],
    }
    health(status, status="STARTING", **base)

    def probe():
        nonlocal last
        now = time.monotonic()
        if path.is_socket():
            if now - last >= 3:
                health(status, status="READY", **base)
                last = now
        elif now >= ready_by:
            return 1
        return None

    try:
        return delegated_guard.run(
            [
                str(binary),
                str(path),
                str(root / "bundle"),
                "swiglu",
                str(ort),
                "--research-manifest-sha",
                SCOPE,
            ],
            health=probe,
        )
    finally:
        health(status, status="STOPPED", **base)


def projection(row, lineage):
    vector = row["vectors"]
    sha = store.vector_sha(vector)
    spec = schema()
    if (
        row["source"] != "NGINX_REQUEST_MIRROR"
        or row["transform_sha256"] != spec["transform_sha256"]
    ):
        raise ValueError("Projection provenance mismatch")
    scored = row["rust_shadow"]
    if scored["status"] == "SCORED" and scored["model_sha256"] != ONNX:
        raise ValueError("Unexpected shadow model")
    return {
        "request_id": row["request_id"],
        "dispatch_wall_ns": row["nginx_dispatch_unix_ns"],
        "cutoff_ns": 1_000_000_000,
        "guard_ns": 1_000_000,
        "clock_scope": "NGINX_AND_PROJECTOR_SAME_HOST",
        "scope": "LOCAL_MIRROR_ONLY",
        "source_mask_at_cutoff": None,
        "lineage": lineage,
        "uri76_sha256": sha,
        "uri76": {
            "vector": vector,
            "transform_sha256": spec["transform_sha256"],
            "observed_monotonic_ns": row["received_monotonic_ns"],
            "available_monotonic_ns": row["available_monotonic_ns"],
            "feature_availability": {
                name: bool(vector[spec["columns"].index(name)]) for name in FEATURES
            },
            "history": row["history_diagnostic"],
            "history_ready_by_monotonic_ns": scored["available_monotonic_ns"],
        },
        "r20": scored | {"model_sha256": ONNX, "model_version": "uri76-swiglu-dev-v1"},
        "rule": None,
        "hybrid": None,
        "oracle": None,
        "label": {"kind": "UNLABELED_OBSERVATION"},
    }


def receiver(args):
    with store.connect(args.state / "evidence.sqlite") as db:
        store.initialize(db)
        state = args.state / "receiver-health.json"

        class PersistentReceiver(Receiver):
            def append(self, row):
                record = projection(
                    row,
                    {
                        "host_boot": BOOT,
                        "receiver_invocation": os.environ.get("INVOCATION_ID"),
                        "profile": "LOCAL_URI76_MIRROR",
                    },
                )
                try:
                    accepted = store.enqueue(db, record)
                except sqlite3.OperationalError as exc:
                    if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                        raise
                    health(state, status="BACKPRESSURE", reason="SQLITE_BUSY")
                    return
                if not accepted:
                    health(state, status="BACKPRESSURE_OR_DUPLICATE")

        with PersistentReceiver(
            args.socket, None, rust_socket=args.rust_socket, representation_history=True
        ) as server:
            last = 0

            def maintain():
                nonlocal last
                now = time.monotonic()
                if now - last >= 5:
                    health(state, status="READY", socket=str(args.socket))
                    last = now

            server.service_actions = maintain
            try:
                server.serve_forever(poll_interval=1)
            finally:
                args.socket.unlink(missing_ok=True)


def collector(args):
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    pg_service = configured(args.state)
    with store.connect(args.state / "evidence.sqlite") as db:
        store.initialize(db)
        store.verify_commits(db)
        status = args.state / "collector-health.json"
        last = 0
        while not stopping:
            try:
                store.collect(db, args.ri_journal, policy_lookup=lambda ids: fetch(pg_service, ids))
            except sqlite3.OperationalError as exc:
                if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                    raise
                time.sleep(0.4)
                continue
            now = time.monotonic()
            if now - last >= 5:
                health(status, status="READY", **store.stats(db))
                last = now
            time.sleep(0.4)
        health(status, status="STOPPED", **store.stats(db))


def import_r22(args):
    """Import already committed R22 evidence, preserving its original lane."""
    run = args.r22_run
    summary_path, ledger_path = run / "quality-summary.json", run / "quality-ledger.json"
    status = json.loads((run / "status.json").read_text())
    summary, ledger = json.loads(summary_path.read_text()), json.loads(ledger_path.read_text())
    verification = run / "verification.json"
    receipts = run / "guest-resource/guest/receipt-ledger.jsonl"
    if not (
        status["state"] == "COMPLETED"
        and status["verification_sha256"] == file_sha256(verification)
        and status["summary_sha256"] == file_sha256(summary_path)
        and summary["ledger_sha256"] == file_sha256(ledger_path)
        and summary["guest_ledger_sha256"] == file_sha256(receipts)
        and ledger["rows_sha256"] == digest(ledger["rows"])
    ):
        raise ValueError("R22 evidence pin mismatch")
    rows = ledger["rows"]
    delivered = 0
    with store.connect(args.state / "evidence.sqlite") as db:
        store.initialize(db)
        found = {
            row["attempt"]: row
            for line in receipts.read_text().splitlines()
            if (row := json.loads(line))["kind"] == "ATTEMPT"
        }
        for row in rows:
            guest = found[row["attempt"]]
            if row["receipt_sha256"] != digest(guest) or row["request_key"] != guest["request_key"]:
                raise ValueError("R22 request join mismatch")
            vector = row["uri76"]
            sha = store.vector_sha(vector["vector"])
            if sha != vector["sha256"]:
                raise ValueError("R22 URI76 hash mismatch")
            delivered += store.enqueue(
                db,
                row
                | {
                    "scope": "R22_ARCHIVED_KVM_ENGINEERING",
                    "dispatch_wall_ns": guest["send_monotonic_ns"]
                    + guest["clock_first_sample_ns"][1]
                    - guest["clock_first_sample_ns"][0],
                    "clock_scope": "R22_GUEST_DISPATCH_ESTIMATE",
                    "uri76_sha256": sha,
                },
            )
    print(json.dumps({"enqueued": delivered, "source": run.name}))


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("scorer", "receiver", "collector", "import-r22"))
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--socket", type=Path)
    p.add_argument("--rust-socket", type=Path)
    p.add_argument("--ri-journal", type=Path)
    p.add_argument("--r22-run", type=Path)
    args = p.parse_args()
    try:
        return {
            "scorer": scorer,
            "receiver": receiver,
            "collector": collector,
            "import-r22": import_r22,
        }[args.action](args)
    except (ValueError, OSError, sqlite3.DatabaseError, KeyError) as exc:
        print(f"{args.action}: {type(exc).__name__}", flush=True)
        return 78 if args.action == "scorer" or isinstance(exc, ValueError) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Single active HTTPS research scorer. Emits request-bound, non-enforcing metadata."""

import argparse
import contextlib
import hashlib
import errno
import fcntl
import signal
import socket
import stat
import json
import os
from pathlib import Path
import sqlite3
import sys
import subprocess

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "https-shadow-r35"))
from receiver import Scorer, serve, SCHEMA, initialize


SLOT_ROOT = HERE.parent / "quality-freeze-r37"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def slot(which):
    registry = json.loads((SLOT_ROOT / "slots.json").read_text())
    s = registry["slots"][which or registry["default"]]
    evidence = SLOT_ROOT / s["manifest"]
    model = SLOT_ROOT / s["model"]
    if (
        registry["abi"] != SCHEMA
        or registry["schema_sha256"] != digest(HERE.parent / "https-shadow-r35/schema.json")
        or digest(evidence) != s["manifest_sha256"]
        or digest(model) != s["sha256"]
    ):
        raise ValueError("Release pin mismatch")
    m = json.loads(evidence.read_text())
    if (
        m["model_sha256"] != s["sha256"]
        or m["enforcement_allowed"] is not False
        or m["threshold"] != s["threshold"]
    ):
        raise ValueError("Invalid research slot")
    return s


def initialize_journal(db):
    initialize(db)
    with db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS https_outbox(seq INTEGER PRIMARY KEY AUTOINCREMENT,rid TEXT NOT NULL,data TEXT NOT NULL,conflict INTEGER NOT NULL)"
        )
        for name, op in [("insert", "INSERT"), ("conflict", "UPDATE OF conflicted")]:
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS r36_{name} AFTER {op} ON receipts BEGIN
                INSERT INTO https_outbox(rid,data,conflict) VALUES(NEW.request_id,NEW.data,NEW.conflicted); END""")


def resume_journal(stream):
    # Let the ingester quarantine a torn line. The durable outbox then replays
    # its complete record on a new line, preserving every previously committed byte.
    if stream.seek(0, os.SEEK_END):
        stream.seek(-1, os.SEEK_END)
        if stream.read(1) != b"\n":
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())


def drain(db, stream, registry):
    # Durable journal first. A crash before deletion can only replay the identical event.
    rows = db.execute(
        "SELECT seq,rid,data,conflict FROM https_outbox ORDER BY seq LIMIT 64"
    ).fetchall()
    if not rows:
        return
    for _, rid, data, conflict in rows:
        obs = json.loads(data)
        identity = registry[obs["model_sha256"]]
        scored = obs["status"] == "SCORED" and obs["availability"] == "AVAILABLE" and not conflict
        entry = dict(
            request_id=rid,
            version=identity["version"],
            model_sha256=identity["sha256"],
            schema=SCHEMA,
            dispatch_ns=obs["dispatch_ns"],
            receipt_ns=obs["receipt_ns"],
            available_ns=obs["available_ns"],
            cutoff_ns=obs["cutoff_ns"],
            guard_ns=obs["guard_ns"],
            status="CONFLICT" if conflict else ("SCORED" if scored else "ABSTAIN"),
            score=obs["score"] if scored else None,
            threshold=identity["threshold"],
            enforcement=False,
        )
        stream.write((json.dumps(entry, separators=(",", ":"), allow_nan=False) + "\n").encode())
    stream.flush()
    os.fsync(stream.fileno())
    with db:
        db.execute("DELETE FROM https_outbox WHERE seq<=?", (rows[-1][0],))


@contextlib.contextmanager
def owned_socket(path):
    if path.parent.stat().st_uid != os.geteuid() or path.parent.stat().st_mode & 0o022:
        raise ValueError("Invalid socket directory ownership")
    fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.exists() or path.is_symlink():
            st = path.lstat()
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.geteuid():
                raise ValueError("Unexpected socket owner or type")
            with socket.socket(socket.AF_UNIX) as client:
                if client.connect_ex(str(path)) != errno.ECONNREFUSED:
                    raise ValueError("Socket is already active")
            path.unlink()
        yield
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["socket", "database", "journal", "binary", "ort"]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--slot", choices=["candidate", "rollback"])
    p.add_argument("--lineage", required=True)
    p.add_argument("--peer-uid", type=int, default=os.geteuid())
    p.add_argument("--peer-gid", type=int, help="NGINX connecting group, socket only")
    p.add_argument("--journal-gid", type=int, help="Read-only group for the Rust ingester")
    args = p.parse_args()
    os.umask(0o077)
    selected = slot(args.slot)
    registry = {
        v["sha256"]: v for v in json.loads((SLOT_ROOT / "slots.json").read_text())["slots"].values()
    }
    scorer = Scorer(args.binary, SLOT_ROOT / selected["model"], selected["sha256"], args.ort)
    stopping = False

    def terminate(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, terminate)
    with (
        owned_socket(args.socket),
        contextlib.closing(sqlite3.connect(args.database)) as db,
        args.journal.open("a+b") as stream,
    ):
        if args.journal_gid is not None:
            os.fchown(stream.fileno(), -1, args.journal_gid)
            os.fchmod(stream.fileno(), 0o640)
        resume_journal(stream)
        initialize_journal(db)
        drain(db, stream, registry)
        with serve(args.socket, db, scorer, args.lineage, args.peer_uid) as server:
            if args.peer_gid is not None:
                os.chown(args.socket, -1, args.peer_gid)
                os.chmod(args.socket, 0o660)
            elif args.peer_uid != os.geteuid():
                # The edge's exclusive primary group can read its HMAC key. Only
                # grant the edge UID socket access, never share that group with AI.
                subprocess.run(
                    [
                        "/usr/bin/setfacl",
                        "-m",
                        f"u:{args.peer_uid}:rw,g::---,m::rw,o::---",
                        str(args.socket),
                    ],
                    check=True,
                    timeout=2,
                )
            server.timeout = 0.25
            while not stopping:
                server.handle_request()
                drain(db, stream, registry)


if __name__ == "__main__":
    main()

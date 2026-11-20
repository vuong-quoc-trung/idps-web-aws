"""Private Linux Unix-socket receiver for the opt-in proof edge. Shadow only."""

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import select
import socket
import socketserver
import sqlite3
import struct
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

SCHEMA = "idps-uri100-raw-ascii-r26-v1"
PROFILE = "HTTPS_PROOF_EDGE_MAIN_REQUEST_V1"
MODE = "HTTPS_EDGE_SHADOW"
GUARD = 1_000_000
CUTOFF = 1_000_000_000


def vector_sha(vector):
    # IEEE -0 and +0 compare equal; enforce identical canonical bytes across languages.
    return hashlib.sha256(struct.pack("<100f", *(0.0 if v == 0 else v for v in vector))).hexdigest()


def decision(dispatch, receipt, ready, elapsed):
    if dispatch > receipt or ready < receipt or abs(ready - receipt - elapsed) > GUARD:
        return "CLOCK_INVALID"
    return "AVAILABLE" if ready + GUARD <= dispatch + CUTOFF else "LATE"


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS receipts(
        lineage TEXT, request_id TEXT, data TEXT NOT NULL, conflicted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(lineage, request_id))""")


def record(db, row):
    key = (row["lineage"], row["request_id"])
    with db:
        existing = db.execute(
            "SELECT data,conflicted FROM receipts WHERE lineage=? AND request_id=?", key
        ).fetchone()
        if existing:
            previous = json.loads(existing[0])
            if existing[1] or any(
                previous.get(k) != row.get(k)
                for k in ("dispatch_ns", "vector_sha256", "model_sha256")
            ):
                db.execute("UPDATE receipts SET conflicted=1 WHERE lineage=? AND request_id=?", key)
                return "QUARANTINED"
            return "DUPLICATE"
        db.execute(
            "INSERT INTO receipts(lineage,request_id,data) VALUES(?,?,?)",
            (*key, json.dumps(row, allow_nan=False)),
        )
        return "COMMITTED"


class Scorer:
    def __init__(self, binary, model, sha, ort):
        self.cmd = [binary, "--https-shadow", model, sha, ort]
        self.sha = sha
        self.worker = None

    def close(self):
        if self.worker is not None:
            self.worker.kill()
            self.worker.communicate(timeout=2)
            self.worker = None

    def exchange(self, payload):
        # One deadline covers pipe backpressure, first byte and the terminating newline.
        deadline = time.monotonic() + 0.9
        writer, reader = self.worker.stdin.fileno(), self.worker.stdout.fileno()
        os.set_blocking(writer, False)
        os.set_blocking(reader, False)
        remaining = memoryview(payload)
        while remaining:
            if not select.select([], [writer], [], max(0, deadline - time.monotonic()))[1]:
                raise TimeoutError("Scorer write deadline")
            remaining = remaining[os.write(writer, remaining) :]
        reply = bytearray()
        while len(reply) < 16384:
            if not select.select([reader], [], [], max(0, deadline - time.monotonic()))[0]:
                raise TimeoutError("Scorer response deadline")
            part = os.read(reader, 16384 - len(reply))
            if not part:
                raise ValueError("Incomplete scorer response")
            reply.extend(part)
            if b"\n" in part:
                if reply.count(b"\n") != 1 or reply[-1:] != b"\n":
                    raise ValueError("Unexpected scorer frames")
                return json.loads(reply)
        raise ValueError("Scorer frame too large")

    def score(self, method, target):
        try:
            if not self.worker or self.worker.poll() is not None:
                self.close()
                self.worker = subprocess.Popen(
                    self.cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
            frame = dict(schema=SCHEMA, mode=MODE, method=method, target=target)
            row = self.exchange(json.dumps(frame).encode() + b"\n")
            if row.get("status") == "ABSTAIN":
                return None
            vector = row["features"]
            if (
                row["schema"] != SCHEMA
                or row["mode"] != MODE
                or row["model_sha256"] != self.sha
                or len(vector) != 100
                or not all(math.isfinite(v) for v in vector)
                or not 0 <= row["score"] <= 1
                or row["hybrid_allowed"] is not False
            ):
                raise ValueError("ABI or model mismatch")
            return (
                vector,
                row["score"],
                {
                    k: row[k]
                    for k in ("inference_ns", "preprocessing_ns", "model_load_ns")
                    if type(row.get(k)) is int and row[k] >= 0
                },
            )
        except (OSError, ValueError, KeyError, TypeError):
            self.close()
            return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/healthz":
            # Private SO_PEERCRED-gated inference probe. Never create a request receipt.
            scorer = self.server.scorer
            result = scorer.score("GET", "/api/health")
            self.send_response(200 if result else 503)
            self.send_header("Content-Length", "0")
            self.send_header("X-Model-SHA256", scorer.sha)
            self.end_headers()
            return
        received = time.time_ns()
        start = time.monotonic_ns()
        h = self.headers
        names = ["X-IDPS-" + v for v in ("Request-Id", "Dispatch", "Method", "Target")]
        if self.path != "/project" or any(len(h.get_all(k, [])) != 1 for k in names):
            self.send_error(400)
            return
        rid, stamp, method, target = (h[k] for k in names)
        if (
            not re.fullmatch("[0-9a-f]{32}", rid)
            or not re.fullmatch(r"[0-9]{1,12}\.[0-9]{3}", stamp)
            or not target.startswith("/api/")
            or len(target) > 8192
        ):
            self.send_error(400)
            return
        dispatch = int(stamp.replace(".", "")) * 1_000_000
        scorer = self.server.scorer
        result = scorer.score(method, target)
        ready = time.time_ns()
        elapsed = time.monotonic_ns() - start
        state = decision(dispatch, received, ready, elapsed)
        row = dict(
            request_id=rid,
            schema=SCHEMA,
            profile=PROFILE,
            lineage=self.server.lineage,
            dispatch_ns=dispatch,
            receipt_ns=received,
            available_ns=ready,
            elapsed_ns=elapsed,
            guard_ns=GUARD,
            cutoff_ns=dispatch + CUTOFF,
            clock="EDGE_RECEIVER_SAME_KERNEL",
            availability=state,
            model_sha256=scorer.sha,
            status="ABSTAIN",
            vector_sha256=None,
            label=None,
            hybrid_allowed=False,
        )
        if result:
            vector, score, timing = result
            row["scorer_timing"] = timing
            row["vector_sha256"] = vector_sha(vector)
            row["features"] = vector
            if state == "AVAILABLE":
                row.update(status="SCORED", score=score)
        record(self.server.db, row)
        self.send_response(204)
        self.end_headers()


class Receiver(socketserver.UnixStreamServer):
    def verify_request(self, sock, address):
        sock.settimeout(1)
        _, uid, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid == self.peer_uid


@contextlib.contextmanager
def serve(path, db, scorer, lineage, peer_uid):
    if path.parent.stat().st_mode & 0o022 or path.exists() or path.is_symlink():
        raise ValueError("Private socket directory and unused socket path required")
    initialize(db)
    with Receiver(str(path), Handler) as server:
        try:
            os.chmod(path, 0o600)
            server.db, server.scorer, server.lineage, server.peer_uid = (
                db,
                scorer,
                lineage,
                peer_uid,
            )
            yield server
        finally:
            scorer.close()
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("socket", "database", "binary", "model", "ort"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--model-sha", required=True)
    ap.add_argument("--lineage", required=True)
    ap.add_argument("--peer-uid", type=int, default=os.geteuid())
    args = ap.parse_args()
    os.umask(0o077)
    with (
        contextlib.closing(sqlite3.connect(args.database)) as db,
        serve(
            args.socket,
            db,
            Scorer(args.binary, args.model, args.model_sha, args.ort),
            args.lineage,
            args.peer_uid,
        ) as service,
    ):
        service.serve_forever()

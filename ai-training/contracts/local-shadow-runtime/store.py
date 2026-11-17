"""Durable request-time inbox and bounded evidence retention."""

import json
import math
import re
import sqlite3
import struct
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from idps_ai.common import canonical_bytes, digest

ROW_BYTES = 12_288
DB_PAGES = 4096  # 16 MiB, excluding the equally bounded rollback journal
MAX_PENDING = 256
RETAIN = 768
TTL = 7 * 86400
JOIN_GRACE_NS = 2_000_000_000
RID = re.compile(r"[a-f0-9]{32}\Z")
RI_PIN = "b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c"
RI_MODEL = "request-intelligence-v2-frozen-step3072"


def connect(path):
    if path.is_symlink() or path.exists() and not path.is_file():
        raise ValueError("Invalid evidence database type")
    db = sqlite3.connect(path, timeout=0.15, isolation_level=None)
    db.execute("PRAGMA page_size=4096")
    db.execute(f"PRAGMA max_page_count={DB_PAGES}")
    db.execute("PRAGMA synchronous=FULL")
    return db


def initialize(db):
    with db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS inbox (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, rid TEXT UNIQUE NOT NULL,
              queued_ns INTEGER NOT NULL, fingerprint TEXT NOT NULL, payload BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, rid TEXT UNIQUE NOT NULL,
              fingerprint TEXT NOT NULL, vector TEXT NOT NULL, committed_ns INTEGER NOT NULL,
              payload BLOB NOT NULL, sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS state (
              singleton INTEGER PRIMARY KEY CHECK (singleton=1), cursor INTEGER NOT NULL,
              committed INTEGER NOT NULL, rotated INTEGER NOT NULL, duplicate INTEGER NOT NULL,
              rejected INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO state VALUES (1,0,0,0,0,0);
        """)


def vector_sha(vector):
    if len(vector) != 76 or not all(
        type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 1 for n in vector
    ):
        raise ValueError("Invalid URI76")
    return sha256(struct.pack("<76f", *vector)).hexdigest()


def encode(row):
    data = canonical_bytes(row)
    if len(data) > ROW_BYTES:
        raise ValueError("Evidence row exceeds budget")
    return data


def enqueue(db, row, *, limit=MAX_PENDING):
    rid = row["request_id"]
    if not RID.fullmatch(rid):
        raise ValueError("Invalid request identity")
    fingerprint = digest([row["dispatch_wall_ns"], row["uri76_sha256"], row["lineage"]])
    data = encode(row)
    db.execute("BEGIN IMMEDIATE")
    try:
        seen = db.execute(
            "SELECT fingerprint FROM inbox WHERE rid=? UNION ALL SELECT fingerprint FROM evidence WHERE rid=?",
            (rid, rid),
        ).fetchone()
        if seen:
            field = "duplicate" if seen[0] == fingerprint else "rejected"
            db.execute(f"UPDATE state SET {field}={field}+1 WHERE singleton=1")
            accepted = False
        elif db.execute("SELECT count(*) FROM inbox").fetchone()[0] >= limit:
            db.execute("UPDATE state SET rejected=rejected+1 WHERE singleton=1")
            accepted = False
        else:
            db.execute(
                "INSERT INTO inbox(rid,queued_ns,fingerprint,payload) VALUES(?,?,?,?)",
                (rid, time.time_ns(), fingerprint, data),
            )
            accepted = True
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return accepted


def tail(path, budget=131072):
    """Read complete lines from the actual opened inode during rotation."""
    if path is None:
        return []
    try:
        with Path(path).open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - budget))
            if size > budget:
                stream.readline(budget)
            lines = stream.read(budget).splitlines(keepends=True)
    except FileNotFoundError:
        return []
    return lines


def ri_results(path, candidates):
    result = {}
    if path is None:
        return result
    from datetime import UTC

    for journal in (path.with_name(path.name + ".1"), path):
        for line in tail(journal):
            if not line.endswith(b"\n"):
                continue
            try:
                row = json.loads(line)
                rid = row.get("request_id")
                if rid not in candidates or row.get("kind") != "inference":
                    continue
                stamp = datetime.fromisoformat(row["observed_at"])
                dispatch = datetime.fromtimestamp(candidates[rid] / 1e9, UTC)
                if not 0 <= (stamp - dispatch).total_seconds() <= 60:
                    continue
                if row.get("model_version") != RI_MODEL or row.get("manifest_sha256") != RI_PIN:
                    continue
                if row.get("enforcement_actions") != 0 or not RID.fullmatch(row["event_id"]):
                    continue
                score, latency = row["score"], row["latency_ms"]
                if row.get("status") != "SCORED" or not (
                    type(score) in (float, int)
                    and 0 <= score <= 1
                    and type(latency) in (float, int)
                    and math.isfinite(latency)
                    and latency >= 0
                ):
                    continue
                if rid in result and result[rid]["event_id"] != row["event_id"]:
                    result[rid] = {"status": "AMBIGUOUS", "event_id": None}
                    continue
                result[rid] = {
                    key: row[key]
                    for key in (
                        "event_id",
                        "observed_at",
                        "status",
                        "score",
                        "latency_ms",
                        "model_version",
                        "manifest_sha256",
                    )
                }
                result[rid]["scope"] = "ADVISORY_POST_OBSERVATION"
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
    return result


def collect(db, journal=None, *, policy_lookup=None, retain=RETAIN, ttl=TTL, grace=JOIN_GRACE_NS):
    now = time.time_ns()
    pending = db.execute(
        "SELECT seq,rid,fingerprint,payload FROM inbox WHERE queued_ns<=? ORDER BY seq LIMIT 16",
        (now - grace,),
    ).fetchall()
    if (
        not pending
        and not db.execute(
            "SELECT 1 FROM evidence WHERE committed_ns<? LIMIT 1", (now - ttl * 1_000_000_000,)
        ).fetchone()
    ):
        return
    decoded = [(seq, rid, fp, json.loads(raw)) for seq, rid, fp, raw in pending]
    live = {
        rid: row["dispatch_wall_ns"]
        for _, rid, _, row in decoded
        if row["scope"] == "LOCAL_MIRROR_ONLY"
    }
    ri = ri_results(journal, live) if live else {}
    contexts, context_status = (
        policy_lookup(live) if policy_lookup and live else ({}, "UNCONFIGURED")
    )
    from policy import attach

    db.execute("BEGIN IMMEDIATE")
    try:
        for seq, rid, fp, row in decoded:
            if not db.execute("SELECT 1 FROM inbox WHERE seq=?", (seq,)).fetchone():
                continue
            if row["scope"] == "LOCAL_MIRROR_ONLY":
                row["ri_v2"] = ri.get(rid, {"status": "UNAVAILABLE"})
                attach(row, contexts.get(rid), context_status)
            data = encode(row)
            db.execute(
                "INSERT INTO evidence(rid,fingerprint,vector,committed_ns,payload,sha256) VALUES (?,?,?,?,?,?)",
                (rid, fp, row["uri76_sha256"], now, data, sha256(data).hexdigest()),
            )
            db.execute("DELETE FROM inbox WHERE seq=?", (seq,))
            db.execute(
                "UPDATE state SET cursor=max(cursor,?), committed=committed+1 WHERE singleton=1",
                (seq,),
            )
        expired = db.execute(
            "DELETE FROM evidence WHERE committed_ns<? OR seq <= coalesce((SELECT seq FROM evidence ORDER BY seq DESC LIMIT 1 OFFSET ?),0)",
            (now - ttl * 1_000_000_000, retain),
        ).rowcount
        db.execute("UPDATE state SET rotated=rotated+? WHERE singleton=1", (expired,))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def stats(db):
    cursor, committed, rotated, duplicate, rejected = db.execute(
        "SELECT cursor,committed,rotated,duplicate,rejected FROM state"
    ).fetchone()
    retained, vectors, paired, nsa, abstain = db.execute("""
        SELECT count(*), count(DISTINCT vector),
        sum(json_extract(CAST(payload AS TEXT),'$.ri_v2.status')='SCORED' AND json_extract(CAST(payload AS TEXT),'$.r20.status')='SCORED'),
        sum(json_extract(CAST(payload AS TEXT),'$.source_mask_at_cutoff')='NSA'),
        sum(json_extract(CAST(payload AS TEXT),'$.r20.status')='ABSTAIN') FROM evidence
    """).fetchone()
    return {
        "cursor": cursor,
        "committed": committed,
        "rotated": rotated,
        "duplicates": duplicate,
        "rejected": rejected,
        "pending": db.execute("SELECT count(*) FROM inbox").fetchone()[0],
        "retained": retained,
        "vectors_retained": vectors,
        "paired_retained": paired or 0,
        "nsa_retained": nsa or 0,
        "abstain_retained": abstain or 0,
    }


def verify_commits(db):
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("Evidence database failed integrity check")
    for rid, vector, payload, checksum in db.execute(
        "SELECT rid,vector,payload,sha256 FROM evidence"
    ):
        row = json.loads(payload)
        if (
            sha256(payload).hexdigest() != checksum
            or row["request_id"] != rid
            or row["uri76_sha256"] != vector
        ):
            raise ValueError("Committed evidence digest mismatch")

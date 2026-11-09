"""Research admission index; extends existing SQLite/atomic-ledger primitives.

Event identities, request representations and feature views are different units.
Only normalized opaque metadata enters this index, never raw HTTP or secret values.
A/C labels remain different tasks. This is not the formal admission policy.
"""

import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, canonical_bytes, digest, fsync_dir

HEX = re.compile(r"[a-f0-9]{64}")
SLUG = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
ROLES = {"TRAIN", "CALIBRATION", "DEVELOPMENT", "EXTERNAL_STAGING_EXPOSED"}
FIELDS = {
    "source",
    "source_row",
    "request_key",
    "representation_key",
    "view_key",
    "groups",
    "role",
    "tier",
    "label",
    "label_task",
    "identity_verified",
    "label_verified",
    "workflow_key",
    "feature_valid",
    "body_state",
    "headers_available",
    "lineage_verified",
    "privacy_valid",
    "inherited_eligible",
    "reasons",
    "near_hash",
    "timestamp",
    "family",
    "method",
}


def simhash(symbols):
    """Fixed token SimHash; syntax similarity proxy, not semantic equivalence."""
    weights = [0] * 64
    for word, count in Counter(symbols.split()).items():
        value = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
        for bit in range(64):
            weights[bit] += count if value & (1 << bit) else -count
    return f"{sum(1 << i for i, n in enumerate(weights) if n > 0):016x}"


def validate(r):
    if set(r) != FIELDS:
        raise PipelineError("Unknown normalized admission schema")
    for k in ["source", "label_task", "body_state", "family", "method"]:
        if not isinstance(r[k], str) or not SLUG.fullmatch(r[k]):
            raise PipelineError("Unsafe admission category")
    if r["role"] not in ROLES or r["tier"] not in "ABCDE" or len(r["tier"]) != 1:
        raise PipelineError("Unknown role or label tier")
    if type(r["source_row"]) is not int or r["source_row"] < 0:
        raise PipelineError("Invalid source coordinate")
    if r["label"] is not None and (type(r["label"]) is not int or r["label"] not in (0, 1)):
        raise PipelineError("Invalid declared-task label")
    for k in ["request_key", "representation_key", "view_key", "workflow_key"]:
        if r[k] is not None and not HEX.fullmatch(str(r[k])):
            raise PipelineError("Admission keys must be opaque64hex")
    if (
        not isinstance(r["groups"], list)
        or len(r["groups"]) > 8
        or any(not HEX.fullmatch(str(g)) for g in r["groups"])
    ):
        raise PipelineError("Invalid lineage keys")
    for k in [
        "identity_verified",
        "label_verified",
        "feature_valid",
        "headers_available",
        "lineage_verified",
        "privacy_valid",
        "inherited_eligible",
    ]:
        if type(r[k]) is not bool:
            raise PipelineError("Admission flags must be explicit bools")
    if not isinstance(r["reasons"], list) or any(not SLUG.fullmatch(str(x)) for x in r["reasons"]):
        raise PipelineError("Unsafe reason category")
    if r["near_hash"] is not None and not re.fullmatch(r"[0-9a-f]{16}", r["near_hash"]):
        raise PipelineError("Invalid near-signature")
    if r["timestamp"] is not None and (
        not isinstance(r["timestamp"], (int, float)) or not 0 < r["timestamp"] < 4102444800
    ):
        raise PipelineError("Invalid observed time")
    canonical_bytes(r)


class AdmissionIndex:
    def __init__(self, directory, binding):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.root / "index.sqlite")
        self.db.executescript("""PRAGMA cache_size=-16384; PRAGMA temp_store=FILE;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS r(i INTEGER PRIMARY KEY,s TEXT,n INTEGER,req TEXT,raw TEXT,v TEXT,
          role TEXT,task TEXT,y INTEGER,near TEXT,j TEXT, UNIQUE(s,n));
        CREATE INDEX IF NOT EXISTS rq ON r(req); CREATE INDEX IF NOT EXISTS rr ON r(raw);
        CREATE INDEX IF NOT EXISTS rv ON r(v);
        CREATE TABLE IF NOT EXISTS parent(i INTEGER PRIMARY KEY,p INTEGER);
        CREATE TABLE IF NOT EXISTS g(k TEXT,i INTEGER,PRIMARY KEY(k,i));
        CREATE TABLE IF NOT EXISTS b(band INTEGER,k TEXT,i INTEGER,PRIMARY KEY(band,k,i));
        CREATE TABLE IF NOT EXISTS overflow(i INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS saturated(band INTEGER,k TEXT,PRIMARY KEY(band,k));
        """)
        expected = digest(binding)
        old = self.db.execute("SELECT v FROM meta WHERE k='binding'").fetchone()
        if old and old[0] != expected:
            raise PipelineError("Resume source/config/code/key fingerprint mismatch")
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('binding',?)", (expected,))
        self.db.commit()
        self.binding = expected
        self.reconcile()

    @property
    def cursor(self):
        return self.db.execute("SELECT count(*) FROM r").fetchone()[0]

    def reconcile(self):
        # SQLite commit is authoritative even if atomic progress projection lagged.
        count = self.cursor
        assert self.db.execute("SELECT coalesce(max(i)+1,0) FROM r").fetchone()[0] == count
        atomic_json(
            self.root / "progress.json",
            {
                "state": "INGESTING",
                "rows_committed": count,
                "binding": self.binding,
                "source_cursors": dict(self.db.execute("SELECT s,max(n) FROM r GROUP BY s")),
            },
        )

    def find(self, i):
        path = []
        while True:
            p = self.db.execute("SELECT p FROM parent WHERE i=?", (i,)).fetchone()[0]
            if p == i:
                break
            path.append(i)
            i = p
        for child in path:
            self.db.execute("UPDATE parent SET p=? WHERE i=?", (i, child))
        return i

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.db.execute("UPDATE parent SET p=? WHERE i=?", (min(a, b), max(a, b)))

    def append(self, records, chunk=256):
        if not 1 <= chunk <= 256:
            raise PipelineError("Admission chunk budget exceeded")
        start = self.cursor
        try:
            for i, r in enumerate(records, start):
                validate(r)
                self.db.execute(
                    "INSERT INTO r VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        i,
                        r["source"],
                        r["source_row"],
                        r["request_key"],
                        r["representation_key"],
                        r["view_key"],
                        r["role"],
                        r["label_task"],
                        r["label"],
                        r["near_hash"],
                        canonical_bytes(r).decode(),
                    ),
                )
                self.db.execute("INSERT INTO parent VALUES(?,?)", (i, i))
                # Exact identity/content/view relations plus all lineage bridges.
                for column, value in [
                    ("req", r["request_key"]),
                    ("raw", r["representation_key"]),
                    ("v", r["view_key"]),
                ]:
                    if value is not None:
                        other = self.db.execute(
                            f"SELECT min(i) FROM r WHERE {column}=?", (value,)
                        ).fetchone()[0]
                        self.union(i, other)
                for key in r["groups"]:
                    old = self.db.execute("SELECT min(i) FROM g WHERE k=?", (key,)).fetchone()[0]
                    if old is not None:
                        self.union(i, old)
                    self.db.execute("INSERT INTO g VALUES(?,?)", (key, i))
                if r["near_hash"] is not None:
                    h = int(r["near_hash"], 16)
                    for band in range(4):
                        key = f"{(h >> (16 * band)) & 65535:04x}"
                        count = self.db.execute(
                            "SELECT count(*) FROM b WHERE band=? AND k=?", (band, key)
                        ).fetchone()[0]
                        if count >= 256:
                            if not self.db.execute(
                                "SELECT 1 FROM saturated WHERE band=? AND k=?", (band, key)
                            ).fetchone():
                                self.db.execute(
                                    "INSERT OR IGNORE INTO overflow SELECT i FROM b WHERE band=? AND k=?",
                                    (band, key),
                                )
                                self.db.execute("INSERT INTO saturated VALUES(?,?)", (band, key))
                            self.db.execute("INSERT OR IGNORE INTO overflow VALUES(?)", (i,))
                        else:
                            for j, near in self.db.execute(
                                "SELECT r.i,r.near FROM b JOIN r USING(i) WHERE b.band=? AND b.k=?",
                                (band, key),
                            ).fetchall():
                                if (h ^ int(near, 16)).bit_count() <= 3:
                                    self.union(i, j)
                        if count < 256:
                            self.db.execute("INSERT INTO b VALUES(?,?,?)", (band, key, i))
                if (i + 1) % chunk == 0:
                    self.db.commit()
                    self.reconcile()
            self.db.commit()
            self.reconcile()
        except BaseException:
            self.db.rollback()
            raise

    def finalize(self):
        # Disk-backed components. All excluded rows remain graph bridges.
        self.db.executescript(
            "DROP TABLE IF EXISTS roots; CREATE TABLE roots(i INTEGER PRIMARY KEY,c INTEGER);"
        )
        for (i,) in self.db.execute("SELECT i FROM r ORDER BY i"):
            self.db.execute("INSERT INTO roots VALUES(?,?)", (i, self.find(i)))
        self.db.executescript("""CREATE INDEX rc ON roots(c);
          DROP TABLE IF EXISTS bad; CREATE TABLE bad(c INTEGER PRIMARY KEY);
          INSERT INTO bad SELECT c FROM roots JOIN r USING(i) GROUP BY c HAVING count(DISTINCT role)>1;
          DROP TABLE IF EXISTS conflicts; CREATE TABLE conflicts(i INTEGER PRIMARY KEY);
          INSERT OR IGNORE INTO conflicts SELECT r.i FROM r JOIN
            (SELECT req,task FROM r WHERE req IS NOT NULL GROUP BY req,task HAVING min(y)!=max(y)) q
            ON r.req=q.req AND r.task=q.task;
          INSERT OR IGNORE INTO conflicts SELECT r.i FROM r JOIN
            (SELECT raw,task FROM r WHERE raw IS NOT NULL GROUP BY raw,task HAVING min(y)!=max(y)) q
            ON r.raw=q.raw AND r.task=q.task;
          INSERT OR IGNORE INTO conflicts SELECT r.i FROM r JOIN
            (SELECT v,task FROM r WHERE v IS NOT NULL GROUP BY v,task HAVING min(y)!=max(y)) q
            ON r.v=q.v AND r.task=q.task;
        """)
        self.db.commit()
        aggregate = Counter()
        reasons = Counter()
        sources = {}
        tiers = Counter()
        composition = Counter()
        temporary = self.root / ".decisions.writing"
        with temporary.open("wb") as out:
            query = """SELECT r.i,r.j, roots.c, bad.c IS NOT NULL,
             conflicts.i IS NOT NULL, overflow.i IS NOT NULL,
             (SELECT min(x.i) FROM r x WHERE x.req=r.req),
             (SELECT min(x.i) FROM r x WHERE x.raw=r.raw)
             FROM r JOIN roots USING(i) LEFT JOIN bad USING(c)
             LEFT JOIN conflicts USING(i) LEFT JOIN overflow USING(i) ORDER BY r.i"""
            for i, j, component, cross, conflict, over, first_request, first_raw in self.db.execute(
                query
            ):
                r = json.loads(j)
                why = list(r["reasons"])
                row = Counter(TOTAL_SOURCE_ROWS=1)
                tiers[r["tier"]] += 1
                composition[f"{r['label_task']}:{r['label']}"] += 1
                if not r["identity_verified"] or r["request_key"] is None:
                    why.append("HTTP_TRANSACTION_IDENTITY_UNVERIFIED")
                elif first_request == i:
                    row["UNIQUE_HTTP_REQUESTS"] = 1
                if r["feature_valid"]:
                    row["FEATURE_COMPATIBLE"] = 1
                else:
                    why.append("FEATURE_INVALID")
                supported = (
                    r["tier"] in {"A", "B"}
                    and r["label_task"] == "attack_intent"
                    and r["label_verified"]
                    and r["label"] is not None
                )
                if supported:
                    row["LABEL_SUPPORTED"] = 1
                else:
                    why.append("TARGET_LABEL_UNSUPPORTED")
                if r["label_task"] != "attack_intent" or r["label"] is None:
                    row["UNKNOWN"] = 1
                for flag, code in [
                    ("lineage_verified", "LINEAGE_UNVERIFIED"),
                    ("privacy_valid", "PRIVACY_FAILED"),
                    ("inherited_eligible", "INHERITED_EXCLUSION"),
                ]:
                    if not r[flag]:
                        why.append(code)
                if cross:
                    why.append("CROSS_ROLE_CONNECTED_COMPONENT")
                if conflict:
                    why.append("CONTRADICTORY_DECLARED_TASK_LABEL")
                if over:
                    why.append("NEAR_BUCKET_OVERFLOW")
                if r["request_key"] and first_request != i:
                    why.append("DUPLICATE_TRANSACTION_TELEMETRY")
                if r["representation_key"] and first_raw != i:
                    why.append("REPEATED_REQUEST_REPRESENTATION")
                if not why:
                    decision = "STRICT_RESEARCH_ELIGIBLE"
                    row["STRICT_ELIGIBLE"] = 1
                    if r["role"] in {"TRAIN", "CALIBRATION", "DEVELOPMENT"}:
                        row[r["role"] + "_ADMITTED"] = 1
                else:
                    decision = "QUARANTINED"
                    row["QUARANTINED"] = 1
                why = sorted(set(why))
                reasons.update(why)
                aggregate.update(row)
                sources.setdefault(r["source"], Counter()).update(row)
                out.write(
                    canonical_bytes(
                        {
                            "row": i,
                            **r,
                            "component": component,
                            "decision": decision,
                            "decision_reasons": why,
                        }
                    )
                    + b"\n"
                )
            out.flush()
            os.fsync(out.fileno())
        temporary.replace(self.root / "decisions.jsonl")
        fsync_dir(self.root)
        for key in [
            "TOTAL_SOURCE_ROWS",
            "UNIQUE_HTTP_REQUESTS",
            "FEATURE_COMPATIBLE",
            "LABEL_SUPPORTED",
            "STRICT_ELIGIBLE",
            "TRAIN_ADMITTED",
            "CALIBRATION_ADMITTED",
            "DEVELOPMENT_ADMITTED",
            "QUARANTINED",
            "UNKNOWN",
        ]:
            aggregate.setdefault(key, 0)
        assert (
            aggregate["STRICT_ELIGIBLE"] + aggregate["QUARANTINED"]
            == aggregate["TOTAL_SOURCE_ROWS"]
        )
        content = hashlib.sha256()
        with (self.root / "decisions.jsonl").open("rb") as f:
            while b := f.read(1024**2):
                content.update(b)
        summary = {
            "binding": self.binding,
            "counts": dict(aggregate),
            "by_source": {s: dict(v) for s, v in sources.items()},
            "label_tiers": dict(tiers),
            "declared_task_composition": dict(composition),
            "quarantine_reasons_overlapping": dict(reasons),
            "unique_request_representations_within_namespaces": self.db.execute(
                "SELECT count(DISTINCT raw) FROM r"
            ).fetchone()[0],
            "unique_feature_views": self.db.execute("SELECT count(DISTINCT v) FROM r").fetchone()[
                0
            ],
            "distinct_workflow_proxies": self.db.execute(
                "SELECT count(DISTINCT json_extract(j,'$.workflow_key')) FROM r"
            ).fetchone()[0],
            "strict_feature_views": {},
            "decision_ledger_sha256": content.hexdigest(),
            "formal_admission_changed": False,
            "new_training": False,
            "accounting": "Unique_HTTP counts trusted receipt-backed events only. Publisher representations and aliases are separate namespaces, not additive physical requests.",
        }
        # Stream ledger to count qualified views using another disk table.
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS qualified_views(role TEXT,v TEXT,PRIMARY KEY(role,v))"
        )
        self.db.execute("DELETE FROM qualified_views")
        for line in (self.root / "decisions.jsonl").open():
            r = json.loads(line)
            if r["decision"] == "STRICT_RESEARCH_ELIGIBLE" and r["view_key"]:
                self.db.execute(
                    "INSERT OR IGNORE INTO qualified_views VALUES(?,?)", (r["role"], r["view_key"])
                )
        self.db.commit()
        summary["strict_feature_views"] = dict(
            self.db.execute("SELECT role,count(*) FROM qualified_views GROUP BY role")
        )
        summary["dataset_fingerprint"] = digest(summary)
        atomic_json(self.root / "summary.json", summary)
        atomic_json(
            self.root / "progress.json",
            {
                "state": "COMPLETED",
                "rows_committed": self.cursor,
                "binding": self.binding,
                "dataset_fingerprint": summary["dataset_fingerprint"],
            },
        )
        return summary

    def close(self):
        self.db.close()

"""Bounded one-top-up → frozen release → one training → evaluation continuation.

All counters refer to new release views; old15,890 views are never added again.
Historical sealed inputs are not read. Failed gates stop the chain.
"""

import hashlib
import hmac
import json
import math
import sqlite3
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pyarrow.parquet as pq
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix

from idps_ai.common import atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.features.rich_content import rich_request
from idps_ai.features.safe_content import HEADERS, symbolic_request
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.research.large_request import LargeRequest, parameter_count
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint


def order_for_epoch(rng, groups):
    queues = defaultdict(list)
    for i, g in enumerate(groups):
        queues[int(g)].append(i)
    for g in queues:
        rng.shuffle(queues[g])
    active = deque(map(int, rng.permutation(sorted(queues))))
    result = []
    while active:
        g = active.popleft()
        result.append(queues[g].pop())
        if queues[g]:
            active.append(g)
    return np.asarray(result, np.int64)


def release_reasons(db, cfg, complete):
    reasons = []
    if not complete:
        reasons.append("BOUNDED_PUBLIC_TOPUP_TIME_LIMIT; checkpoint preserved")
    counts = dict(db.execute("SELECT role,count(*) FROM examples WHERE quarantine=0 GROUP BY role"))
    if counts.get("TRAIN", 0) < cfg["targets"]["unique_TRAIN_examples"]:
        reasons.append("UNIQUE_TRAIN_SHORTFALL")
    distinct = db.execute(
        "SELECT count(DISTINCT request_hash) FROM examples WHERE quarantine=0"
    ).fetchone()[0]
    if distinct < cfg["targets"]["distinct_requests"]:
        reasons.append("DISTINCT_ELIGIBLE_REQUEST_SHORTFALL")
    for role in ["TRAIN", "CALIBRATION", "EVALUATION"]:
        for label in [0, 1]:
            n = db.execute(
                "SELECT count(*) FROM examples WHERE role=? AND intent=? AND quarantine=0",
                (role, label),
            ).fetchone()[0]
            if n < (50 if role == "TRAIN" else 20):
                reasons.append(f"{role}_INTENT_{label}_COVERAGE")
    for label in [0, 1]:
        n = db.execute(
            "SELECT count(*) FROM examples WHERE role='TRAIN' AND publisher=? AND quarantine=0",
            (label,),
        ).fetchone()[0]
        if n < 50:
            reasons.append(f"TRAIN_PUBLISHER_{label}_COVERAGE")
    overlaps = db.execute(
        "SELECT count(*) FROM (SELECT template FROM examples WHERE quarantine=0 GROUP BY template HAVING count(DISTINCT role)>1)"
    ).fetchone()[0]
    if overlaps:
        reasons.append("TEMPLATE_ROLE_LEAKAGE")
    return reasons


def load(p):
    return json.loads(Path(p).read_text())


class ConservativeNear:
    """Exact coordinate-radius necessary condition, bounded exact comparisons.

    Every true cosine neighbor survives coordinate filtering. If a candidate
    bucket exceeds the fixed budget, reject the query rather than claiming it
    is clean. No LSH recall assumption, no unbounded all-pairs matrix.
    """

    def __init__(self, references, cap=256):
        self.ref = np.asarray(references, np.float32)
        assert self.ref.ndim == 2 and np.isfinite(self.ref).all()
        self.cap = cap
        self.max_norm = (
            float(np.max(np.sum(self.ref.astype(np.float64) ** 2, axis=1))) if len(self.ref) else 0
        )
        self.dimensions = np.argsort(np.var(self.ref, axis=0))[-32:] if len(self.ref) else []
        self.orders = {int(j): np.argsort(self.ref[:, j], kind="stable") for j in self.dimensions}
        self.values = {j: self.ref[self.orders[j], j] for j in self.orders}

    def blocked(self, x):
        if not len(self.ref):
            return False, "NO_REFERENCES"
        x = np.asarray(x, np.float64)
        radius = math.sqrt(max(0, float(x @ x) + self.max_norm - 2 * (0.995 - 1e-7))) + 1e-7
        ranges = []
        for j, values in self.values.items():
            a, b = np.searchsorted(values, [x[j] - radius, x[j] + radius], side="left")
            b = int(np.searchsorted(values, x[j] + radius, side="right"))
            ranges.append((b - a, j, int(a), b))
        ranges.sort()
        n, j, a, b = ranges[0]
        if n == 0:
            return False, "CERTIFIED_EMPTY_RADIUS"
        ids = self.orders[j][a:b]
        # All32 necessary conditions are cheap and cannot discard a true neighbor.
        for _, j, _, _ in ranges[1:]:
            ids = ids[np.abs(self.ref[ids, j].astype(np.float64) - x[j]) <= radius]
            if not len(ids):
                return False, "CERTIFIED_EMPTY_RADIUS"
        if len(ids) > self.cap:
            return True, "CONSERVATIVE_NEAR_OVERFLOW"
        match = bool(np.any(self.ref[ids].astype(np.float64) @ x >= 0.995 - 1e-7))
        return match, "PROTECTED_NEAR" if match else "EXACT_CANDIDATES_CLEAR"


def open_release(root, cfg):
    path = root / "release-v1"
    path.mkdir(mode=0o700, exist_ok=True)
    db = sqlite3.connect(path / "index.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(
        """
      CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
      CREATE TABLE IF NOT EXISTS examples(id INTEGER PRIMARY KEY,view TEXT UNIQUE,request_hash TEXT,
        role TEXT,source TEXT,tier TEXT,intent INTEGER,publisher INTEGER,template TEXT,method TEXT,
        x BLOB,quarantine INTEGER DEFAULT0);
      CREATE INDEX IF NOT EXISTS roles ON examples(role,quarantine,id);
      CREATE INDEX IF NOT EXISTS groups_idx ON examples(template);
      CREATE TABLE IF NOT EXISTS seen(view TEXT PRIMARY KEY,reason TEXT);
      CREATE TABLE IF NOT EXISTS dispositions(reason TEXT PRIMARY KEY,n INTEGER);
      CREATE TABLE IF NOT EXISTS origins(source TEXT,position INTEGER,view TEXT,label TEXT,
        PRIMARY KEY(source,position));
    """.replace("DEFAULT0", "DEFAULT 0")
    )
    fp = digest(cfg)
    old = db.execute("SELECT v FROM meta WHERE k='config'").fetchone()
    assert old is None or old[0] == fp, "Release resume configuration changed"
    db.execute("INSERT OR IGNORE INTO meta VALUES('config',?)", (fp,))
    db.commit()
    return path, db


def disposition(db, reason):
    db.execute(
        "INSERT INTO dispositions VALUES(?,1) ON CONFLICT(reason) DO UPDATE SET n=n+1", (reason,)
    )


def protections(repo, root, cap):
    source = repo / "ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1"
    ready = load(source / "protection-ready.json")
    for name, sha in ready["files"].items():
        assert file_sha256(source / name) == sha
    with np.load(source / "protected-vectors.npz", allow_pickle=False) as z:
        full = [z["full"].copy(), z["runtime"].copy()]
    finalcfg = load(source / "final-training-config.json")
    for role in ["calibration", "evaluation"]:
        assert (
            file_sha256(source / "final-data" / f"{role}.npz")
            == finalcfg["data_files"][f"{role}.npz"]
        )
        with np.load(source / "final-data" / f"{role}.npz", allow_pickle=False) as z:
            full.append(z["x"][:, 76:].copy())
    pilot = (
        repo
        / "ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1/data"
    )
    for role in ["calibration", "evaluation"]:
        assert (
            file_sha256(pilot / f"{role}.npz")
            == load(source / "plan.json")["pilot_data_sha256"][f"{role}.npz"]
        )
        with np.load(pilot / f"{role}.npz", allow_pickle=False) as z:
            full.append(z["x"][:, 76:].copy())
    with np.load(source / "legacy-heldout.npz", allow_pickle=False) as z:
        safe = ConservativeNear(z["safe"].copy(), cap)
        rich = ConservativeNear(z["rich"].copy(), cap)
    db = sqlite3.connect(
        "file:" + str(source / "protection-build/index.sqlite") + "?mode=ro", uri=True
    )
    groups = {r[0] for r in db.execute("SELECT k FROM protected_group")}
    routes = {r[0] for r in db.execute("SELECT k FROM protected_route")}
    db.close()
    return (
        ConservativeNear(np.concatenate(full), cap),
        safe,
        rich,
        groups,
        routes,
        (source / "identity.key").read_bytes(),
    )


def selected_headers(value):
    if not isinstance(value, str):
        raise ValueError("Unobserved headers cannot be fabricated as observed empty headers")
    value = value or ""
    matches = list(HEADERS.finditer(value[:8192]))
    result = {}
    names = {"user-agent": "User-Agent", "accept": "Accept", "content-type": "Content-Type"}
    for i, m in enumerate(matches):
        key = m.group(1).lower()
        if key in names and key not in result:
            end = matches[i + 1].start() if i + 1 < len(matches) else min(len(value), 8192)
            result[key] = value[m.end() : end].strip()
    selected = {v: result.get(k, "") for k, v in names.items()}
    if any(len(v) > 1024 for v in selected.values()):
        raise ValueError("Unsupported live header length")
    return selected


def materialize(root, cfg, status, api):
    path, db = open_release(root, cfg)
    assert file_sha256(api.REPO / cfg["source"]["path"]) == cfg["source"]["sha256"]
    if (path / "readiness.json").exists():
        previous = load(path / "readiness.json")
        if previous["state"] == "PASS":
            assert previous["config_fingerprint"] == digest(cfg)
            assert previous["unique_TRAIN_examples"] >= cfg["targets"]["unique_TRAIN_examples"]
            for name, sha in previous["files"].items():
                assert file_sha256(path / name) == sha
            db.close()
            return previous
    status.write(
        phase="DATA_VALIDATION_AND_DEDUP",
        operation="ONE_BOUNDED_WAF_RUNTIME588_TOPUP",
        completed=0,
        total=cfg["source"]["rows"],
    )
    full, safe, rich, groups, routes, key = protections(
        api.REPO, root, cfg["topup"]["near_candidate_cap"]
    )
    vectorizer = HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=512,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    # CAL/EVAL request-derived features are used only for leakage exclusion here.
    q = api.open_index(root)
    q.execute(
        "UPDATE views SET conflict=1 WHERE template IN (SELECT h FROM template_roles WHERE conflict=1)"
    )
    q.commit()
    synth_refs = [
        np.frombuffer(r[0], np.float32)[76:].copy()
        for r in q.execute("SELECT feature FROM views WHERE role IN ('CALIBRATION','EVALUATION')")
    ]
    evalnear = ConservativeNear(
        np.asarray(synth_refs, np.float32).reshape(-1, 512), cfg["topup"]["near_candidate_cap"]
    )
    # Cross-role near CAL/EVAL cases are quarantined, never reassigned to TRAIN.
    role_refs = {
        role: ConservativeNear(
            np.asarray(
                [
                    np.frombuffer(r[0], np.float32)[76:].copy()
                    for r in q.execute("SELECT feature FROM views WHERE role=?", (role,))
                ],
                np.float32,
            ).reshape(-1, 512),
            cfg["topup"]["near_candidate_cap"],
        )
        for role in ["CALIBRATION", "EVALUATION"]
    }
    for view, role, template, blob, rhash, receipt, target, conflict in q.execute(
        "SELECT h,role,template,feature,request_hash,receipt,target,conflict FROM views ORDER BY h"
    ):
        if db.execute(
            "SELECT1 FROM seen WHERE view=?".replace("SELECT1", "SELECT 1"), (view,)
        ).fetchone():
            continue
        x = np.frombuffer(blob, np.float32)
        assert (
            x.shape == (588,) and np.isfinite(x).all() and hashlib.sha256(blob).hexdigest() == view
        )
        blocked, reason = full.blocked(x[76:])
        if not conflict and not blocked:
            blocked, reason = (
                evalnear.blocked(x[76:])
                if role == "TRAIN"
                else role_refs["EVALUATION" if role == "CALIBRATION" else "CALIBRATION"].blocked(
                    x[76:]
                )
            )
        reason = "CROSS_ROLE_TEMPLATE_OR_VIEW" if conflict else reason
        if conflict or blocked:
            disposition(db, reason)
        else:
            metadata = json.loads(receipt)
            db.execute(
                "INSERT INTO examples(view,request_hash,role,source,tier,intent,publisher,template,method,x) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    view,
                    rhash,
                    role,
                    "SYNTHETIC_EXECUTED",
                    "BRONZE",
                    target,
                    -1,
                    template,
                    metadata["method"],
                    blob,
                ),
            )
        db.execute("INSERT INTO seen VALUES(?,?)", (view, reason))
    db.commit()
    q.close()
    cursor_row = db.execute("SELECT v FROM meta WHERE k='public_cursor'").fetchone()
    cursor = int(cursor_row[0]) if cursor_row else 0
    old_elapsed = db.execute("SELECT v FROM meta WHERE k='topup_elapsed'").fetchone()
    elapsed = float(old_elapsed[0]) if old_elapsed else 0
    start = time.monotonic()
    seen = 0
    complete = False
    for batch in pq.ParquetFile(api.REPO / cfg["source"]["path"]).iter_batches(
        batch_size=128, use_threads=False
    ):
        end = seen + len(batch)
        if end <= cursor:
            seen = end
            continue
        for source_row, row in enumerate(batch.to_pylist(), start=seen):
            if source_row < cursor:
                continue
            label = row.get("label")
            db.execute(
                "INSERT OR IGNORE INTO origins VALUES(?,?,NULL,?)",
                (
                    "WAF_PUBLISHER",
                    source_row,
                    label if label in ["normal", "anomalous"] else "UNKNOWN",
                ),
            )
            method = row.get("method")
            url = row.get("url")
            if (
                method
                not in {
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                    "HEAD",
                    "OPTIONS",
                    "TRACE",
                    "CONNECT",
                }
                or not isinstance(url, str)
                or not 1 <= len(url) <= 4096
            ):
                disposition(db, "UNSUPPORTED_LIVE_INPUT")
                continue
            try:
                if not url.startswith("/"):
                    raise ValueError(
                        "Publisher absolute URL is not an observed live relative request target"
                    )
                request = {
                    "method": method,
                    "url": url,
                    "headers": selected_headers(row.get("headers")),
                    "body": None,
                }
                envelope = {
                    "schema_version": "nginx-ai-1",
                    "request_id": "a" * 32,
                    "timestamp": "2026-11-10T00:00:00+00:00",
                    "method": method,
                    "url": url,
                    "headers": request["headers"],
                }
                if len(json.dumps(envelope).encode()) + 256 > 8192:
                    raise ValueError("Unsupported live envelope size")
                x, template = api.features(request, vectorizer)
                original_safe, _ = symbolic_request(
                    method, url, row.get("headers"), row.get("body")
                )
                runtime_safe, _ = symbolic_request(
                    method,
                    url,
                    "\r\n".join(k + ": " + v for k, v in request["headers"].items() if v),
                    None,
                )
                hashes = {
                    hashlib.sha256(t.encode()).hexdigest() for t in [original_safe, runtime_safe]
                }
                route = hmac.new(
                    key, canonical_bytes(["route", [method, urlsplit(url).path]]), hashlib.sha256
                ).hexdigest()
            except (ValueError, TypeError):
                disposition(db, "INVALID_REQUEST")
                continue
            view = hashlib.sha256(x.tobytes()).hexdigest()
            db.execute(
                "UPDATE origins SET view=? WHERE source=? AND position=?",
                (view, "WAF_PUBLISHER", source_row),
            )
            original = row.get("label")
            publisher = 0 if original == "normal" else 1 if original == "anomalous" else -1
            existing = db.execute(
                "SELECT publisher,source FROM examples WHERE view=?", (view,)
            ).fetchone()
            if existing:
                if existing[1] == "WAF_PUBLISHER" and existing[0] != publisher:
                    db.execute(
                        "UPDATE examples SET publisher=-1,tier='UNLABELED' WHERE view=?", (view,)
                    )
                disposition(db, "DUPLICATE_FEATURE_VIEW")
                continue
            if db.execute(
                "SELECT1 FROM seen WHERE view=?".replace("SELECT1", "SELECT 1"), (view,)
            ).fetchone():
                disposition(db, "REPEATED_REJECTED_VIEW")
                continue
            reason = None
            if hashes & groups or route in routes:
                reason = "PROTECTED_TEMPLATE_OR_ROUTE"
            elif db.execute(
                "SELECT 1 FROM examples WHERE role<>'TRAIN' AND template=? LIMIT1".replace(
                    "LIMIT1", "LIMIT 1"
                ),
                (template,),
            ).fetchone():
                reason = "EVALUATION_LINEAGE"
            else:
                for index, vector in [
                    (full, x[76:]),
                    (evalnear, x[76:]),
                    (safe, vectorizer.transform([original_safe]).toarray()[0]),
                    (
                        rich,
                        vectorizer.transform(
                            [rich_request(method, url, row.get("headers"), row.get("body"))[0]]
                        ).toarray()[0],
                    ),
                ]:
                    blocked, why = index.blocked(vector)
                    if blocked:
                        reason = why
                        break
            if reason:
                disposition(db, reason)
            else:
                rhash = hmac.new(
                    key,
                    canonical_bytes(
                        [row.get(k) for k in ["method", "url", "protocol", "headers", "body"]]
                    ),
                    hashlib.sha256,
                ).hexdigest()
                db.execute(
                    "INSERT INTO examples(view,request_hash,role,source,tier,intent,publisher,template,method,x) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        view,
                        rhash,
                        "TRAIN",
                        "WAF_PUBLISHER",
                        "SILVER" if publisher >= 0 else "UNLABELED",
                        -1,
                        publisher,
                        template,
                        method,
                        x.tobytes(),
                    ),
                )
            db.execute("INSERT INTO seen VALUES(?,?)", (view, reason or "ELIGIBLE"))
        seen = end
        db.execute(
            "INSERT INTO meta VALUES('public_cursor',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (str(seen),),
        )
        db.execute(
            "INSERT INTO meta VALUES('topup_elapsed',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (str(elapsed + time.monotonic() - start),),
        )
        db.commit()
        if seen % 1024 == 0:
            n = db.execute(
                "SELECT count(*) FROM examples WHERE role='TRAIN' AND quarantine=0"
            ).fetchone()[0]
            status.write(completed=seen, new_eligible_TRAIN_examples=n, unique_TRAIN_examples=n)
            api.check_disk(root, cfg)
        if elapsed + time.monotonic() - start >= cfg["topup"]["seconds"]:
            break
    complete = seen == cfg["source"]["rows"]
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert (
        db.execute("SELECT count(*) FROM origins WHERE source='WAF_PUBLISHER'").fetchone()[0]
        == seen
    )
    counts = dict(db.execute("SELECT role,count(*) FROM examples WHERE quarantine=0 GROUP BY role"))
    distinct = db.execute(
        "SELECT count(DISTINCT request_hash) FROM examples WHERE quarantine=0"
    ).fetchone()[0]
    reasons = release_reasons(db, cfg, complete)
    fp = hashlib.sha256()
    for r in db.execute(
        "SELECT view,request_hash,role,source,tier,intent,publisher,template,method,x FROM examples WHERE quarantine=0 ORDER BY view"
    ):
        x = np.frombuffer(r[-1], np.float32)
        assert (
            x.shape == (588,) and np.isfinite(x).all() and hashlib.sha256(r[-1]).hexdigest() == r[0]
        )
        fp.update(canonical_bytes(list(r[:-1])))
        fp.update(r[-1])
    report = {
        "state": "PASS" if not reasons else "BLOCKED",
        "targets": cfg["targets"],
        "counts_by_role": counts,
        "unique_TRAIN_examples": counts.get("TRAIN", 0),
        "distinct_eligible_request_representations": distinct,
        "verified_physical_requests_new_campaign": load(root / "capture-complete.json")[
            "verified_receipts"
        ],
        "public_physical_identity": "UNVERIFIED; corpus representations only, not wire execution receipts",
        "tiers_TRAIN": dict(
            db.execute(
                "SELECT tier,count(*) FROM examples WHERE role='TRAIN' AND quarantine=0 GROUP BY tier"
            )
        ),
        "source_rows_accounted": seen,
        "topup_complete": complete,
        "source_positions_not_added_twice": True,
        "protected_near": "same-profile coordinate radius; exact bounded candidates; overflow quarantined",
        "dispositions": dict(db.execute("SELECT reason,n FROM dispositions")),
        "blockers": reasons,
        "dataset_fingerprint": fp.hexdigest(),
        "config_fingerprint": digest(cfg),
        "independent_review": "PENDING",
        "feature_contract": "runtime588 selected_headers_no_body; fixed encoding; no fitted statistics",
        "sealed_access": False,
        "training": "NOT_STARTED",
        "next": "TRAINING_PREFLIGHT" if not reasons else "STOP",
    }
    atomic_json(path / "readiness.json", report)
    if not reasons:
        files = {}
        for role in ["TRAIN", "CALIBRATION", "EVALUATION"]:
            n = counts.get(role, 0)
            arrays = {
                name: np.lib.format.open_memmap(
                    path / (role + "-" + name + ".npy"), mode="w+", dtype=dtype, shape=shape
                )
                for name, shape, dtype in [
                    ("x", (n, 588), np.float32),
                    ("y", (n, 2), np.int64),
                    ("groups", (n,), np.int64),
                ]
            }
            for i, (x, intent, publisher, template) in enumerate(
                db.execute(
                    "SELECT x,intent,publisher,template FROM examples WHERE role=? AND quarantine=0 ORDER BY view",
                    (role,),
                )
            ):
                arrays["x"][i] = np.frombuffer(x, np.float32)
                arrays["y"][i] = [intent, publisher]
                arrays["groups"][i] = int(template[:15], 16)
            for name, out in arrays.items():
                out.flush()
            del arrays
            for name in ["x", "y", "groups"]:
                files[role + "-" + name + ".npy"] = file_sha256(path / (role + "-" + name + ".npy"))
        report["files"] = files
        atomic_json(path / "readiness.json", report)
    db.close()
    return report


def train(root, cfg, release, status):
    status.write(phase="TRAINING_PREFLIGHT", completed=0, total=1, training="NOT_STARTED")
    path = root / "release-v1"
    run = root / "large-training-v1"
    run.mkdir(exist_ok=True, mode=0o700)
    for name, sha in release["files"].items():
        assert file_sha256(path / name) == sha
    x = np.load(path / "TRAIN-x.npy", mmap_mode="r")
    y = np.load(path / "TRAIN-y.npy", mmap_mode="r")
    groups = np.load(path / "TRAIN-groups.npy", mmap_mode="r")
    assert len(x) >= cfg["targets"]["unique_TRAIN_examples"]
    epochs = cfg["training"]["epochs"]
    batch = cfg["training"]["batch_size"]
    steps = epochs * math.ceil(len(x) / batch)
    binding = digest([release["dataset_fingerprint"], cfg])
    with RunLock(run):
        if (run / "latest.json").exists():
            loaded = load_checkpoint(run)
            state = loaded.state
            assert state["binding"] == binding
            model = LargeRequest.from_arrays(state["model"], loaded.model.arrays())
            order = loaded.permutation
            assert state["scheduler"]["step"] == model.steps == len(state["loss_history"])
            assert state["planned_steps"] == steps
            assert np.array_equal(np.sort(order), np.arange(len(x)))
        else:
            model = LargeRequest(seed=17)
            rng = np.random.default_rng(17)
            order = order_for_epoch(rng, groups)
            state = {
                "binding": binding,
                "dataset_fingerprint": release["dataset_fingerprint"],
                "epoch": 0,
                "cursor": 0,
                "RNG": rng.bit_generator.state,
                "scheduler": {"kind": "constant", "step": 0},
                "loss_history": [],
                "planned_steps": steps,
            }
            save_checkpoint(run, model, state, order)
            status.write(phase="TRAINING_PREFLIGHT", training="RUNNING", completed=0, total=1)
            checked = load_checkpoint(run)
            control = LargeRequest.from_arrays(checked.state["model"], checked.model.arrays())
            ids = order[:batch]
            loss = model.train_batch(x[ids], y[ids], cfg["training"]["learning_rate"])
            control.train_batch(x[ids], y[ids], cfg["training"]["learning_rate"])
            assert all(np.array_equal(v, control.arrays()[k]) for k, v in model.arrays().items())
            del control, checked
            state["cursor"] = len(ids)
            state["scheduler"]["step"] = model.steps
            state["loss_history"].append({"step": model.steps, "loss": loss})
            save_checkpoint(run, model, state, order)
            atomic_json(
                run / "actual-data-resume-proof.json",
                {
                    "state": "PASS",
                    "step": 1,
                    "same_next_update": True,
                    "dataset_fingerprint": release["dataset_fingerprint"],
                },
            )
        assert sum(v.size for v in model.parameters.values()) == parameter_count() == 10065928
        while model.steps < steps:
            status.write(
                phase="REAL_10M_TRAINING",
                completed=model.steps,
                total=steps,
                training="RUNNING",
                optimizer_updates=model.steps,
                epoch=state["epoch"],
                epochs=epochs,
                checkpoint=str(run / "latest.json"),
                unique_TRAIN_examples=len(x),
                training_loss=state["loss_history"][-1]["loss"] if state["loss_history"] else None,
            )
            ids = order[state["cursor"] : state["cursor"] + batch]
            loss = model.train_batch(x[ids], y[ids], cfg["training"]["learning_rate"])
            assert np.isfinite(loss)
            state["loss_history"].append({"step": model.steps, "loss": loss})
            state["cursor"] += len(ids)
            state["scheduler"]["step"] = model.steps
            if state["cursor"] == len(order):
                state["epoch"] += 1
                state["cursor"] = 0
                if state["epoch"] < epochs:
                    rng = np.random.default_rng()
                    rng.bit_generator.state = state["RNG"]
                    order = order_for_epoch(rng, groups)
                    state["RNG"] = rng.bit_generator.state
            if (
                model.steps % cfg["training"]["checkpoint_every_updates"] == 0
                or model.steps == steps
            ):
                checkpoint = save_checkpoint(run, model, state, order)
                checked = load_checkpoint(run)
                assert (
                    checked.model.steps == model.steps
                    and checked.state["scheduler"]["step"] == model.steps
                )
                status.write(
                    checkpoint=str(checkpoint),
                    training_loss=loss,
                    optimizer_updates=model.steps,
                    completed=model.steps,
                )
        atomic_json(
            run / "completed.json",
            {
                "state": "COMPLETED",
                "optimizer_updates": model.steps,
                "epochs": epochs,
                "dataset_fingerprint": release["dataset_fingerprint"],
                "checkpoint": load(run / "latest.json"),
            },
        )
    return model, run


def wilson(k, n):
    if not n:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def binary_metrics(y, s, threshold):
    prediction = s > threshold
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "precision": float(tp / max(1, tp + fp)),
        "recall": float(tp / max(1, tp + fn)),
        "F1": float(2 * tp / max(1, 2 * tp + fp + fn)),
        "AP": float(average_precision_score(y, s)),
        "FPR": float(fp / max(1, fp + tn)),
        "FNR": float(fn / max(1, fn + tp)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "FPR_Wilson": wilson(int(fp), int(fp + tn)),
        "recall_Wilson": wilson(int(tp), int(tp + fn)),
        "Brier": float(brier_score_loss(y, s)),
    }


def choose_threshold(y, s):
    order = np.argsort(s, kind="stable")
    scores = s[order]
    labels = y[order]
    positives = np.r_[0, np.cumsum(labels == 1)]
    negatives = np.r_[0, np.cumsum(labels == 0)]
    candidates = np.unique(np.r_[0.0, s, 1.0])
    a = np.searchsorted(scores, candidates, side="right")
    balanced = 0.5 * (
        (positives[-1] - positives[a]) / max(1, positives[-1])
        + negatives[a] / max(1, negatives[-1])
    )
    return float(candidates[np.flatnonzero(balanced == balanced.max())[-1]])


def evaluate(root, cfg, model, status):
    status.write(phase="LOCKED_MODEL_EVALUATION", completed=0, total=2, training="COMPLETED")
    path = root / "release-v1"
    scores = {}
    batch_latency = []
    single_latency = []
    frozen = ResearchMVP("request-v2", cpus=1)
    for role in ["CALIBRATION", "EVALUATION"]:
        x = np.load(path / (role + "-x.npy"), mmap_mode="r")
        y = np.load(path / (role + "-y.npy"), mmap_mode="r")
        candidate = []
        control = []
        for a in range(0, len(x), 64):
            t = time.monotonic()
            candidate.append(model.score_heads(x[a : a + 64])["synthetic_or_grounded_intent"])
            batch_latency.append((time.monotonic() - t) * 1000 / max(1, len(x[a : a + 64])))
            control.append(frozen.v2_model.predict(x[a : a + 64])[0])
        mask = y[:, 0] >= 0
        scores[role] = (y[mask, 0], np.concatenate(candidate)[mask], np.concatenate(control)[mask])
        if role == "CALIBRATION":
            for row in x[:64]:
                t = time.monotonic()
                model.score_heads(row[None, :])
                single_latency.append((time.monotonic() - t) * 1000)
        status.write(completed=len(scores))
    cy, cs, cf = scores["CALIBRATION"]
    ey, es, ef = scores["EVALUATION"]
    threshold = choose_threshold(cy, cs)
    control_threshold = choose_threshold(cy, cf)
    metrics = binary_metrics(ey, es, threshold)
    baseline = binary_metrics(ey, ef, frozen.v2_threshold)
    cal_control = binary_metrics(ey, ef, control_threshold)
    bins = []
    for a in np.linspace(0, 1, 11)[:-1]:
        mask = (es >= a) & (es < a + 0.1 if a < 0.9 else es <= 1)
        if mask.any():
            bins.append(
                {
                    "n": int(mask.sum()),
                    "mean_score": float(es[mask].mean()),
                    "positive_fraction": float(ey[mask].mean()),
                }
            )
    ece = sum(b["n"] * abs(b["mean_score"] - b["positive_fraction"]) for b in bins) / len(ey)
    rng = np.random.default_rng(17)
    thresholds = []
    for _ in range(32):
        ids = rng.integers(0, len(cy), len(cy))
        if len(np.unique(cy[ids])) == 2:
            thresholds.append(choose_threshold(cy[ids], cs[ids]))
    db = sqlite3.connect("file:" + str(path / "index.sqlite") + "?mode=ro", uri=True)
    metadata = db.execute(
        "SELECT method,source,tier,template FROM examples WHERE role='EVALUATION' AND quarantine=0 ORDER BY view"
    ).fetchall()
    db.close()
    subgroups = {}
    for column, name in [(0, "method"), (1, "source"), (2, "label_tier")]:
        for value in sorted({r[column] for r in metadata}):
            mask = np.array([r[column] == value for r in metadata])
            subgroups[name + ":" + value] = binary_metrics(ey[mask], es[mask], threshold)
    benign_post = np.array([r[0] == "POST" for r in metadata]) & (ey == 0)
    group_counts = Counter(r[3] for r in metadata)
    weights = np.array([1 / group_counts[r[3]] for r in metadata])
    group_ap = float(average_precision_score(ey, es, sample_weight=weights))
    g = cfg["integration_gates"]
    reasons = []
    if metrics["FPR_Wilson"][1] > g["FPR_Wilson_upper_max"]:
        reasons.append("FPR_BOUND_FAILED")
    if metrics["recall_Wilson"][0] < g["recall_Wilson_lower_min"]:
        reasons.append("RECALL_BOUND_FAILED")
    if sum(ey == 1) < g["intent_eval_min_positive"] or sum(ey == 0) < g["intent_eval_min_negative"]:
        reasons.append("INTENT_EVAL_COVERAGE")
    if benign_post.sum() < g["normal_POST_min"]:
        reasons.append("BENIGN_POST_EVAL_COVERAGE")
    if (
        metrics["AP"]
        < max(baseline["AP"], cal_control["AP"]) + g["AP_gain_over_same_task_baseline_min"]
    ):
        reasons.append("NO_PRECOMMITTED_AP_GAIN")
    single_p95 = float(np.quantile(single_latency, 0.95))
    if single_p95 > g["inference_p95_ms_max"]:
        reasons.append("SINGLE_REQUEST_LATENCY_LIMIT")
    report = {
        "state": "PASS" if not reasons else "BLOCKED",
        "metrics": metrics,
        "frozen_v2_baseline": baseline,
        "calibration_only_control": cal_control,
        "per_subgroup": subgroups,
        "per_family": "NOT_RECORDED_FOR_ALL_HISTORICAL_RECEIPTS",
        "benign_POST": {
            "n": int(benign_post.sum()),
            "FP": int(np.sum((es > threshold) & benign_post)),
        },
        "calibration": {
            "ECE10": ece,
            "bins": bins,
            "CAL_bootstrap_threshold_5_95": np.quantile(thresholds, [0.05, 0.95]).tolist()
            if thresholds
            else None,
        },
        "threshold_source": "CAL_ONLY strict> highest balanced-accuracy tie; no EVAL threshold selection",
        "latency_single_request_p95_ms": single_p95,
        "latency_batched_per_request_p95_ms": float(np.quantile(batch_latency, 0.95)),
        "group_sensitivity": {"equal_template_weight_AP": group_ap, "groups": len(group_counts)},
        "uncertainty": "Wilson row intervals do not prove independent events; group dependence remains",
        "natural_generalization": "NOT_ESTABLISHED; prospective within synthetic grammar only",
        "small_publisher_baseline": "TASK_INCOMPATIBLE with synthetic intent; never substitute publisher anomaly for attack intent",
        "blockers": reasons,
        "live_inference": "NOT_MEASURED",
        "promotion": False,
        "independent_review": "PENDING",
        "dataset_fingerprint": load(path / "readiness.json")["dataset_fingerprint"],
        "config_fingerprint": digest(cfg),
        "checkpoint": load(root / "large-training-v1/latest.json"),
    }
    atomic_json(root / "large-evaluation.json", report)
    return report


def continue_after_capture(root, cfg, status, api):
    report = materialize(root, cfg, status, api)
    terminal = {
        "run_id": root.name,
        "state": "BLOCKED",
        "data": report,
        "training": "NOT_STARTED",
        "evaluation": "NOT_STARTED",
        "local_integration": "NOT_STARTED",
        "local_release": "BLOCKED",
        "manual_firewall": "PENDING_APPROVAL; NOT_RUN",
        "next_automatic_action": "STOP",
    }
    if report["state"] == "PASS":
        model, run = train(root, cfg, report, status)
        terminal.update(training="COMPLETED", checkpoint=str(run / "latest.json"))
        evaluated = evaluate(root, cfg, model, status)
        terminal["evaluation"] = evaluated
        if evaluated["state"] == "PASS":
            # Existing Rust accepts only its independently pinned Frozenv2 identity.
            # Never spoof that identity or mutate protected Security Web files.
            terminal["local_integration"] = "BLOCKED_EXISTING_RUST_CANDIDATE_MODEL_CONTRACT"
    atomic_json(root / "terminal-status.json", terminal)
    status.write(
        phase="TERMINAL_STATUS",
        state="BLOCKED",
        next_automatic_action="STOP",
        blocker=report["blockers"] or terminal.get("evaluation"),
    )
    return terminal

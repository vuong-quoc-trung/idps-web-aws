import argparse
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.resumable_near import THRESHOLD, checkpoint_read, load_vectors

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(
    description="Focused final100K verification and fixed internal grouped split; no training"
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = repo / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"
out = args.output
out.mkdir(parents=True, exist_ok=True)


def load(p):
    return json.loads(p.read_text())


with threadpool_limits(limits=1):
    a = load(root / "materialized/summary.json")
    b = load(root / "rebuild/summary.json")
    assert a == b
    check = dict(a)
    assert check.pop("fingerprint") == digest(check)
    assert load(root / "attempts/recovery-a2/result.json")["state"] == "COMPLETED"
    assert load(root / "attempts/recovery-a2/thermal-report.json")["state"] == "COMPLETED"
    assert load(root / "completion.json")["old_shards_unchanged"]
    report = {
        "dataset_fingerprint": a["fingerprint"],
        "counts": a["counts"],
        "files": {},
        "db": {},
        "near": {},
    }
    for role in ["materialized", "rebuild"]:
        folder = root / role
        for name, sha in a["files"].items():
            assert file_sha256(folder / name) == sha
        with sqlite3.connect(f"file:{folder}/index.sqlite?mode=ro", uri=True) as db:
            assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            n, unique = db.execute('SELECT count(*),count(DISTINCT s||":"||n) FROM r').fetchone()
            assert n == unique == 100000
        report["db"][role] = "PASS_100000_UNIQUE_SOURCE_POSITIONS"
        cache = folder / "near-resumable-v1"
        m = load(cache / "vectors-manifest.json")
        vectors, counts, manifest = load_vectors(cache, m["source_binding"])
        p = load(cache / "progress.json")
        c = checkpoint_read(
            cache / "checkpoint.json", p["checkpoint_binding"], len(vectors), m["rows"], 128
        )
        assert (
            c["next_unique_anchor"] == 32735
            and sum(map(int, counts)) == 99927
            and c["pairs"] == 427968495
        )
        report["near"][role] = {
            "vectors": len(vectors),
            "rows": m["rows"],
            "pairs": c["pairs"],
            "fingerprint": m["fingerprint"],
        }
    assert report["near"]["materialized"] == report["near"]["rebuild"]
    rows = []
    source_tiers = collections.Counter()
    source_labels = collections.Counter()
    teacher = collections.Counter()
    for line in (root / "materialized/ledger.jsonl").open():
        m = json.loads(line)
        source_tiers[m["tier"]] += 1
        source_labels[str(m["original_label"])] += 1
        assert m["intent"] == "UNKNOWN_INTENT" and m["outcome"] == "UNKNOWN_OUTCOME"
        if m["source"] == "first-party":
            assert m["tier"] == "UNLABELED" and m["target"] is None
        else:
            assert m["tier"] == "SILVER" and m["target"] == int(m["original_label"] == "anomalous")
        if m["decision"] == "TRAINING_ELIGIBLE":
            rows.append(m)
    assert len(rows) == 3783
    training = [json.loads(s) for s in (root / "materialized/training-index.jsonl").open()]
    assert [v["row"] for v in training] == [v["row"] for v in rows]
    for m, v in zip(rows, training, strict=True):
        assert m["target"] == v["target"] and m["feature_ref"] == v["features"]
    expected = load(root / "attempts/recovery-a2/integrity.json")["shard_hashes"]
    matrices = {}
    norms = []
    for name, sha in expected.items():
        assert (
            file_sha256(root / "materialized" / name) == file_sha256(root / "rebuild" / name) == sha
        )
        with np.load(root / "materialized" / name, allow_pickle=False) as z:
            x = z["x"]
            assert (
                x.dtype == np.float32 and x.ndim == 2 and x.shape[1] == 588 and np.isfinite(x).all()
            )
            matrices[name] = x
    x = np.stack([matrices[m["feature_ref"]["shard"]][m["feature_ref"]["slot"]] for m in rows])
    y = np.array([m["target"] for m in rows], np.int64)
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        i, j = find(i), find(j)
        if i != j:
            parent[max(i, j)] = min(i, j)

    by = {}
    for i, m in enumerate(rows):
        g = m["component"]
        if g in by:
            union(i, by[g])
        else:
            by[g] = i
    near_pairs = 0
    content = x[:, 76:].astype(np.float64)
    for start in range(0, len(x), 128):
        ids = np.arange(start, min(start + 128, len(x)))
        scores = content[ids] @ content.T
        assert not np.any(np.abs(scores - THRESHOLD) <= 1e-12)
        aa, bb = np.where((scores >= THRESHOLD) & (ids[:, None] < np.arange(len(x))[None, :]))
        for i, j in zip(ids[aa], bb, strict=True):
            union(int(i), int(j))
            near_pairs += 1
    groups = np.array([rows[find(i)]["row"] for i in range(len(rows))], np.int64)
    # Frozen precommitted split rule: group+seed17 hash,70/15/15; no resampling for outcome.
    role = []
    for g in groups:
        bucket = (
            int(hashlib.sha256(f"student-publisher-v1:17:{g}".encode()).hexdigest()[:16], 16) % 100
        )
        role.append("TRAIN" if bucket < 70 else "CALIBRATION" if bucket < 85 else "EVALUATION")
    canonical = []
    seen = {}
    for i, m in enumerate(rows):
        key = m["view_key"]
        if key in seen:
            assert y[i] == y[seen[key]] and role[i] == role[seen[key]]
        else:
            seen[key] = i
            canonical.append(i)
    split_counts = {}
    for r in ["TRAIN", "CALIBRATION", "EVALUATION"]:
        ix = [i for i in canonical if role[i] == r]
        split_counts[r] = {
            "canonical_views": len(ix),
            "normal": sum(y[i] == 0 for i in ix),
            "anomalous": sum(y[i] == 1 for i in ix),
            "groups": len({int(groups[i]) for i in ix}),
        }
    report.update(
        source_tiers=dict(source_tiers),
        source_labels=dict(source_labels),
        eligible_components_before=len(by),
        eligible_components_after=len(set(groups)),
        eligible_near_pairs=near_pairs,
        split_counts=split_counts,
        teacher_pretrain_overlap=sum(m["teacher_pretrain_template_overlap"] for m in rows),
        eligible_publisher_classes=dict(collections.Counter(map(int, y))),
        source_window_by_label={
            str(k): v
            for k, v in collections.Counter(
                (int(m["source_row"] >= 1048576), m["target"]) for m in rows
            ).items()
        },
    )
    report = json.loads(json.dumps(report, default=lambda v: v.item()))
    atomic_json(out / "checked.json", report)
    np.savez(
        out / "ready-private.npz",
        x=x,
        y=y,
        groups=groups,
        role=np.array(role),
        canonical=np.array(canonical, np.int64),
        rows=np.array([m["row"] for m in rows], np.int64),
    )
    print(
        json.dumps({k: v for k, v in report.items() if k not in ["files", "db", "near"]}),
        flush=True,
    )

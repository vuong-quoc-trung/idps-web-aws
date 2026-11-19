"""Post-hoc coverage audit on earlier anchors of held accounts; all decisions stay frozen."""

import sys
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from login_data import HISTORY_WIDTH, RAW, peer_features, peer_snapshot
from login_study import apply, score
from sklearn.metrics import average_precision_score

from idps_ai.common import atomic_json, file_sha256, load_json


def evaluate(run):
    lock = load_json(run / "login-lock.json")
    plan = load_json(run / "early-actor-lock.json")
    for name, sha in plan["private_pins"].items():
        if file_sha256(run / name) != sha:
            raise ValueError("changed frozen artifact")
    if plan["evaluator_sha"] != file_sha256(__file__) or (run / "early-actors.json").exists():
        raise ValueError("supplementary audit already consumed or changed")
    arms = [lock["selected_learned_control"], lock["selected_deterministic_control"]]
    if arms != ["PEER", "PEER_NOVELTY"]:
        raise ValueError(
            "this audit requires both frozen heads to consume only the current peer view"
        )
    raw = load_json(run / "raw-index.json")
    peer_cut = raw["first_ms"] + (raw["last_ms"] - raw["first_ms"]) // 4
    table = peer_snapshot(run, raw, peer_cut)
    models = joblib.load(run / "login-heads.joblib")
    # Values 0-3 are per-actor reference, flags, learned reference alerts and learned flagged hits.
    counts = defaultdict(lambda: np.zeros(4, dtype=np.int64))
    by_score = {arm: defaultdict(lambda: np.zeros(2, dtype=np.int64)) for arm in arms}
    totals = {arm: np.zeros(6, dtype=np.int64) for arm in arms}
    paired = np.zeros(4, dtype=np.int64)
    for j in range(80, 100):
        name = f"{j:02d}.bin"
        path = run / "account-buckets" / name
        if file_sha256(path) != raw["bucket_shas"][name]:
            raise ValueError("source part changed")
        a = np.memmap(path, mode="r", dtype=RAW)
        for start in range(0, len(a), 65536):
            part = a[start : start + 65536]
            if not (part["user"] % 100 == j).all():
                raise ValueError("actor overlap")
            part = part[part["ts"] < raw["boundary_ms"]]
            if not len(part):
                continue
            yy = part["y"]
            flags = yy == 1
            z = peer_features(part, table, peer_cut)
            # PEER and PEER_NOVELTY never consume the unavailable history columns.
            d = {
                "x": np.column_stack((np.zeros((len(z), HISTORY_WIDTH), dtype="<f4"), z)),
                "valid": np.zeros(len(z), bool),
            }
            fires = []
            for arm in arms:
                policy = lock["arms"][arm]
                p = apply(score(d, arm, models[arm]), policy["sigmoid"])
                fire = p > policy["cutoff"]
                good = np.isfinite(p)
                totals[arm] += [
                    len(p),
                    flags.sum(),
                    good.sum(),
                    (good & flags).sum(),
                    (fire & flags).sum(),
                    (fire & ~flags).sum(),
                ]
                vals, idx = np.unique(p[good], return_inverse=True)
                yy_good = yy[good]
                for value, zero, one in zip(
                    vals,
                    np.bincount(idx, weights=1 - yy_good),
                    np.bincount(idx, weights=yy_good),
                    strict=True,
                ):
                    by_score[arm][float(value)] += np.array([zero, one], dtype=np.int64)
                fires.append(fire)
            ml, rule = fires
            paired += [
                (ml & ~rule & flags).sum(),
                (~ml & rule & flags).sum(),
                (ml & ~rule & ~flags).sum(),
                (~ml & rule & ~flags).sum(),
            ]
            users, idx = np.unique(part["user"], return_inverse=True)
            grouped = np.column_stack(
                [np.bincount(idx, weights=v) for v in (~flags, flags, ml & ~flags, ml & flags)]
            ).astype(np.int64)
            for user, v in zip(users, grouped, strict=True):
                counts[int(user)] += v
    metrics = {}
    for arm, (rows, pos, avail, pos_avail, tp, fp) in totals.items():
        bins = by_score[arm]
        ps = np.asarray(list(bins))
        ww = np.stack(list(bins.values()))
        target = np.tile([0, 1], len(ps))
        flat_weights = ww.ravel()
        keep = flat_weights > 0
        metrics[arm] = {
            "rows": int(rows),
            "flags": int(pos),
            "scored": int(avail),
            "scored_flags": int(pos_avail),
            "TP": int(tp),
            "FP_reference": int(fp),
            "effective_recall": float(tp / pos) if pos else None,
            "reference_alert_rate": float(fp / (rows - pos)),
            "precision": float(tp / (tp + fp)) if tp + fp else None,
            "AP_scored": float(
                average_precision_score(
                    target[keep], np.repeat(ps, 2)[keep], sample_weight=flat_weights[keep]
                )
            )
            if pos_avail
            else None,
        }
    c = np.stack(list(counts.values()))
    rng = np.random.default_rng(3403)
    boot = []
    for _ in range(400):
        v = rng.poisson(1, len(c)) @ c
        if v[1]:
            boot.append([v[3] / v[1], v[2] / v[0]])
    result = {
        "scope": "EXPLORATORY_EARLIER_ANCHORS_SAME_HELD_ACCOUNTS",
        "plan_sha": file_sha256(run / "early-actor-lock.json"),
        "metrics": metrics,
        "actors": len(c),
        "flagged_actors": int(np.sum(c[:, 1] > 0)),
        "paired_learned_only_flags_rule_only_flags_learned_only_negative_rule_only_negative": paired.tolist(),
        "actor_bootstrap_95_recall_alert_rate": np.quantile(boot, [0.025, 0.975], axis=0).tolist()
        if boot
        else None,
        "valid_bootstrap_draws": len(boot),
        "native_admitted": 0,
    }
    atomic_json(run / "early-actors.json", result)


if __name__ == "__main__":
    evaluate(Path(sys.argv[1]))

"""Actor-disjoint fitting, selection, calibration and one frozen temporal transfer on RBA."""

import hashlib
import sys
import time
from pathlib import Path

import joblib
import numpy as np
from login_data import HERE, HISTORY_WIDTH, NAMES
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

from idps_ai.common import atomic_json, file_sha256, load_json

BLOCKS = {
    "FIT": range(50),
    "SELECT": range(50, 65),
    "CAL_FIT": range(65, 72),
    "CAL_OP": range(72, 80),
    "TRANSFER": range(80, 100),
}
COLUMNS = {
    "SUPPORT": [0, 1, 2],
    "NETWORK": [0, 1, 2, 3, 4, 5, 6, 7, 8, 19],
    "DEVICE": [0, 1, 2, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20],
    "JOINT": list(range(HISTORY_WIDTH)),
    "PEER": list(range(HISTORY_WIDTH, len(NAMES))),
    "HISTORY_AND_PEER": list(range(len(NAMES))),
}


def blocks(run, role):
    meta = load_json(run / "projection.json")
    root = run / "login-inputs"
    for j in BLOCKS[role]:
        index = meta["role_bins"][j]
        path = root / f"{j:02d}.npz"
        if file_sha256(path) != index["sha256"]:
            raise ValueError("projected observations changed")
        if "parts" in index:
            parts = index["parts"]
            with np.load(path, allow_pickle=False) as entry:
                if (
                    list(entry["part_names"]) != [e["file"] for e in parts]
                    or list(entry["part_shas"]) != [e["sha256"] for e in parts]
                    or sum(e["rows"] for e in parts) != index["sampled"]
                ):
                    raise ValueError("large partition index changed")
        else:
            parts = [{"file": path.name, "sha256": index["sha256"]}]
        for part in parts:
            src = (root / part["file"]).resolve()
            if not src.is_relative_to(root.resolve()) or file_sha256(src) != part["sha256"]:
                raise ValueError("changed role part")
            with np.load(src, allow_pickle=False) as a:
                d = {k: a[k] for k in ("x", "u", "valid", "y")}
            if not np.all(d["u"] % 100 == j) or len(d["u"]) != part.get("rows", len(d["u"])):
                raise ValueError("actor or row count outside role")
            for lo in range(0, len(d["y"]), 65536):
                yield {k: v[lo : lo + 65536] for k, v in d.items()}


def read(run, role):
    rows = list(blocks(run, role))
    out = {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}
    out["w"] = np.where((out["y"] == 0) & (role in ("FIT", "SELECT")), 32.0, 1.0)
    return out


def cutoff(y, p, w):
    ix = (y == 0) & (w > 0) & np.isfinite(p)
    if not ix.any():
        return 1.0
    z, inv = np.unique(p[ix], return_inverse=True)
    counts = np.bincount(inv.ravel(), weights=w[ix])
    tails = np.cumsum(counts[::-1])[::-1]
    return float(z[np.flatnonzero(tails > counts.sum() * 0.005)[-1]])


def measure(y, p, t, w):
    fire = p > t
    good = np.isfinite(p)
    pos = y == 1
    neg = ~pos
    tp = w[fire & pos].sum()
    fp = w[fire & neg].sum()

    def div(a, b):
        return float(a / b) if b else None

    out = {
        "rows": len(y),
        "scored_rows": int(good.sum()),
        "source_flag_count": int(y.sum()),
        "weight_total": float(w.sum()),
        "TP": float(tp),
        "FP": float(fp),
        "FN": float(w[pos].sum() - tp),
        "TN": float(w[neg].sum() - fp),
        "effective_recall": div(tp, w[pos].sum()),
        "reference_alert_rate": div(fp, w[neg].sum()),
        "precision": div(tp, tp + fp),
        "coverage": div(w[good].sum(), w.sum()),
        "coverage_positive": div(w[good & pos].sum(), w[pos].sum()),
        "AP": None,
        "Brier_scored": None,
        "ECE10_scored": None,
    }
    if good.any():
        v = p[good]
        lab = y[good]
        weight = w[good]
        bins = np.minimum((v * 10).astype(int), 9)
        out["Brier_scored"] = float(np.average((v - lab) ** 2, weights=weight))
        out["ECE10_scored"] = float(
            np.abs(np.bincount(bins, weights=(v - lab) * weight, minlength=10)).sum() / weight.sum()
        )
        if len(np.unique(lab)) == 2:
            out["AP"] = float(average_precision_score(lab, v, sample_weight=weight))
    return out


def supported(d, arm):
    peer = d["x"][:, HISTORY_WIDTH] > 0
    if arm in ("PEER", "PEER_NOVELTY"):
        return peer
    if arm == "HISTORY_AND_PEER":
        return peer | d["valid"]
    return d["valid"]


def score(d, arm, ck):
    x = d["x"]
    valid = supported(d, arm)
    p = np.full(len(x), np.nan)
    if arm == "CONSTANT":
        p[:] = 0.0
        return p
    if not valid.any():
        return p
    v = x[valid]
    if arm == "NEW_ASN_RULE":
        out = v[:, 6] * (v[:, 7] == 0)
    elif arm == "JOINT_NOVELTY":
        known = v[:, 3:18:3]
        freq = v[:, 4:18:3]
        out = np.sum(known * (1 - freq), axis=1) / np.maximum(1, known.sum(axis=1))
    elif arm == "PEER_NOVELTY":
        out = v[:, HISTORY_WIDTH + 2 :: 2].sum(axis=1) / np.maximum(
            1, v[:, HISTORY_WIDTH + 1 :: 2].sum(axis=1)
        )
    elif arm == "JOINT_TREE":
        out = ck.predict_proba(v[:, :HISTORY_WIDTH])[:, 1]
    else:
        scaler, lr = ck
        out = lr.predict_proba(scaler.transform(v[:, COLUMNS[arm]]))[:, 1]
    p[valid] = out
    return p


def train(run):
    if (run / "login-lock.json").exists():
        raise ValueError("model and thresholds already frozen")
    fit, sel = read(run, "FIT"), read(run, "SELECT")
    if set(fit["u"]) & set(sel["u"]):
        raise ValueError("actor overlap")
    arms = {"CONSTANT": None, "NEW_ASN_RULE": None, "JOINT_NOVELTY": None, "PEER_NOVELTY": None}
    fit_support = {}
    for arm in (*COLUMNS, "JOINT_TREE"):
        valid = supported(fit, arm)
        x = fit["x"][valid]
        y = fit["y"][valid]
        positive_users = len(np.unique(fit["u"][valid & (fit["y"] == 1)]))
        fit_support[arm] = positive_users
        if positive_users < 2 or not np.any(y == 0):
            continue
        w = fit["w"][valid].copy()
        for k in (0, 1):
            w[y == k] *= len(y) / (2 * w[y == k].sum())
        if arm == "JOINT_TREE":
            arms[arm] = HistGradientBoostingClassifier(
                max_iter=45,
                max_depth=3,
                max_leaf_nodes=7,
                min_samples_leaf=40,
                l2_regularization=8,
                early_stopping=False,
                random_state=34,
            ).fit(x[:, :HISTORY_WIDTH], y, sample_weight=w)
        else:
            cols = COLUMNS[arm]
            sc = StandardScaler().fit(x[:, cols], sample_weight=w)
            lr = LogisticRegression(C=0.3, max_iter=300, random_state=34).fit(
                sc.transform(x[:, cols]), y, sample_weight=w
            )
            arms[arm] = sc, lr
    diagnostics = {}
    for arm, model in arms.items():
        p = score(sel, arm, model)
        t = cutoff(sel["y"], p, sel["w"])
        diagnostics[arm] = {"threshold": t, **measure(sel["y"], p, t, sel["w"])}
    choices = [k for k in arms if k not in ("CONSTANT", "NEW_ASN_RULE", "SUPPORT")]
    selected = (
        max(
            choices,
            key=lambda k: (diagnostics[k]["effective_recall"] or 0, diagnostics[k]["AP"] or 0),
        )
        if np.any(supported(sel, "HISTORY_AND_PEER") & (sel["y"] == 1))
        else "JOINT_NOVELTY"
    )

    def choose(names):
        return max(
            names,
            key=lambda k: (diagnostics[k]["effective_recall"] or 0, diagnostics[k]["AP"] or 0),
        )

    controls = [k for k, m in arms.items() if m is None]
    learned = [k for k, m in arms.items() if m is not None]
    rule_ref = choose(controls)
    learned_ref = choose(learned) if learned else None
    delays = []
    fit_supported = supported(fit, selected)
    for i in np.flatnonzero(fit_supported)[:129]:
        one = {"x": fit["x"][i : i + 1], "valid": fit["valid"][i : i + 1]}
        began = time.perf_counter_ns()
        score(one, selected, arms[selected])
        delays.append((time.perf_counter_ns() - began) / 1e6)
    file = run / "login-heads.joblib"
    joblib.dump(arms, file)
    # Independent calibration accounts never participate in architecture selection.
    cal, op = read(run, "CAL_FIT"), read(run, "CAL_OP")
    decisions = {}
    for arm, model in arms.items():
        pc = score(cal, arm, model)
        good = np.isfinite(pc)
        npos = len(np.unique(cal["u"][good & (cal["y"] == 1)]))
        nneg = len(np.unique(cal["u"][good & (cal["y"] == 0)]))
        coef = None
        if npos >= 2 and nneg >= 2 and np.unique(pc[good]).size >= 2:
            sigmoid = LogisticRegression(C=1.0, max_iter=200).fit(
                logit(np.clip(pc[good], 1e-6, 1 - 1e-6))[:, None], cal["y"][good]
            )
            if sigmoid.coef_[0, 0] > 0:
                coef = [float(sigmoid.coef_[0, 0]), float(sigmoid.intercept_[0])]
        pop = apply(score(op, arm, model), coef)
        t = cutoff(op["y"], pop, op["w"])
        decisions[arm] = {"sigmoid": coef, "cutoff": t, "CAL_OP": measure(op["y"], pop, t, op["w"])}

    def stats(d):
        return {
            "sample_rows": len(d["y"]),
            "users": len(np.unique(d["u"])),
            "positives": int(d["y"].sum()),
            "positive_users": len(np.unique(d["u"][d["y"] == 1])),
            "scored_positives": int(np.sum(d["valid"] & (d["y"] == 1))),
        }

    lock = {
        "model_sha": file_sha256(file),
        "schema": NAMES,
        "plan_sha": file_sha256(HERE / "plan.json"),
        "code_sha": file_sha256(Path(__file__)),
        "data_code_sha": file_sha256(HERE / "login_data.py"),
        "projection_sha": file_sha256(run / "projection.json"),
        "selected": selected,
        "selected_deterministic_control": rule_ref,
        "selected_learned_control": learned_ref,
        "latency_on_supported_FIT_batch1": {
            "n": max(len(delays) - 1, 0),
            "first_ms": delays[0] if delays else None,
            "warm_p50_p95_ms": np.quantile(delays[1:], [0.5, 0.95]).tolist()
            if len(delays) > 1
            else None,
            "scope": "Python scoring including normalization, projected vector ready; in-process load already complete",
        },
        "selection": diagnostics,
        "arms": decisions,
        "support": {
            k: stats(d)
            for k, d in [("FIT", fit), ("SELECT", sel), ("CAL_FIT", cal), ("CAL_OP", op)]
        },
        "supported_fit_positive_accounts_by_arm": fit_support,
    }
    atomic_json(run / "login-lock.json", lock)


def apply(p, coef):
    return expit(coef[0] * logit(np.clip(p, 1e-6, 1 - 1e-6)) + coef[1]) if coef is not None else p


def cluster_interval(u, y, fire):
    ids, idx = np.unique(u, return_inverse=True)
    idx = idx.ravel()
    rng = np.random.default_rng(3402)
    neg = np.bincount(idx, weights=(y == 0))
    pos = np.bincount(idx, weights=(y == 1))
    fp = np.bincount(idx, weights=(y == 0) & fire)
    tp = np.bincount(idx, weights=(y == 1) & fire)
    # Poisson bootstrap by actor, keeping repeated observations and abstentions together.
    ratios = [[], []]
    for _ in range(400):
        m = rng.poisson(1, len(ids))
        for vector, den, out in ((tp, pos, ratios[0]), (fp, neg, ratios[1])):
            a = np.sum(m * den)
            if a:
                out.append(np.sum(m * vector) / a)
    return {
        "actors": len(ids),
        "positive_actors": int((pos > 0).sum()),
        "valid_draws": [len(r) for r in ratios],
        "recall_and_reference_alert_rate_95": [
            np.quantile(r, [0.025, 0.975]).tolist() if r else None for r in ratios
        ],
    }


def transfer(run):
    f = load_json(run / "login-lock.json")
    path = run / "login-heads.joblib"
    if any(
        (f[k] != file_sha256(p))
        for k, p in [
            ("model_sha", path),
            ("projection_sha", run / "projection.json"),
            ("code_sha", Path(__file__)),
            ("plan_sha", HERE / "plan.json"),
            ("data_code_sha", HERE / "login_data.py"),
        ]
    ):
        raise ValueError("frozen inputs changed")
    if (run / "login-transfer.json").exists():
        raise ValueError("transfer result already committed")
    arms = joblib.load(path)
    n = sum(
        load_json(run / "projection.json")["role_bins"][j]["sampled"] for j in BLOCKS["TRANSFER"]
    )
    if not n:
        raise ValueError("empty evaluation interval")
    # Materialize scalar predictions and group fingerprints, never the entire dense held matrix.
    fixed = f["arms"]
    ps = {arm: np.empty(n, dtype=np.float64) for arm in arms}
    y = np.empty(n, dtype=np.uint8)
    actor = np.empty(n, dtype=np.uint64)
    valid = np.empty(n, dtype=bool)
    peer = np.empty(n, dtype=bool)
    nprior = np.empty(n, dtype=np.uint8)
    raw_scores = np.empty(n, dtype=np.float32)
    ids = np.empty(n, dtype="V32")
    pos = 0
    for d in blocks(run, "TRANSFER"):
        sl = slice(pos, pos + len(d["y"]))
        x = np.ascontiguousarray(d["x"], dtype="<f4")
        ids[sl] = np.fromiter(
            (hashlib.sha256(row).digest() for row in x), dtype="V32", count=len(x)
        )
        y[sl], actor[sl], valid[sl] = d["y"], d["u"], d["valid"]
        peer[sl] = supported(d, "PEER")
        nprior[sl] = np.rint(x[:, 0] * 5).astype(np.uint8)
        raw_scores[sl] = score(d, "NEW_ASN_RULE", None)
        for arm, m in arms.items():
            ps[arm][sl] = apply(score(d, arm, m), fixed[arm]["sigmoid"])
        pos = sl.stop
    if pos != n:
        raise ValueError("held denominator changed")
    d = {"u": actor, "valid": valid, "w": np.broadcast_to(1.0, (n,))}
    _, inv, count = np.unique(ids, return_inverse=True, return_counts=True)
    vw = 1 / count[inv.ravel()]
    metrics = {
        a: {
            "request": measure(y, p, fixed[a]["cutoff"], d["w"]),
            "vector": measure(y, p, fixed[a]["cutoff"], vw),
        }
        for a, p in ps.items()
    }
    chosen = f["selected"]
    flag = ps[chosen] > fixed[chosen]["cutoff"]
    # The predeclared boolean novelty control may flag nobody at <=0.5%; also show its unthresholded burden.
    rule = ps["NEW_ASN_RULE"] > fixed["NEW_ASN_RULE"]["cutoff"]
    raw = raw_scores > 0.5
    paired = {
        k: {
            "gained_positive": int(np.sum((y == 1) & flag & ~r)),
            "lost_positive": int(np.sum((y == 1) & ~flag & r)),
            "gained_reference_alert": int(np.sum((y == 0) & flag & ~r)),
            "lost_reference_alert": int(np.sum((y == 0) & ~flag & r)),
        }
        for k, r in [("budget_rule", rule), ("raw_novelty_rule", raw)]
    }
    learned_ref = f["selected_learned_control"]
    rule_ref = f["selected_deterministic_control"]
    match = None
    if learned_ref:
        learner = ps[learned_ref] > fixed[learned_ref]["cutoff"]
        control = ps[rule_ref] > fixed[rule_ref]["cutoff"]
        match = {
            "learned": learned_ref,
            "rule": rule_ref,
            "learned_only_incidents": int(np.sum((y == 1) & learner & ~control)),
            "rule_only_incidents": int(np.sum((y == 1) & ~learner & control)),
            "learned_only_reference_alerts": int(np.sum((y == 0) & learner & ~control)),
            "rule_only_reference_alerts": int(np.sum((y == 0) & ~learner & control)),
        }
    rate = np.bincount(inv.ravel(), weights=y)
    # Diagnostic slices are descriptive and are never candidates for re-selection.
    support_groups = {
        "no_trustworthy_history": ~d["valid"],
        "one_prior": d["valid"] & (nprior == 1),
        "two_to_four_prior": d["valid"] & (nprior >= 2) & (nprior <= 4),
        "five_prior": d["valid"] & (nprior == 5),
    }
    actors, loads = np.unique(actor, return_counts=True)
    other = actor != actors[loads.argmax()]
    dominant = {
        "largest_actor_rows": int(loads.max()),
        "largest_actor_flags": int(y[~other].sum()),
        "other_actors": measure(
            y[other], ps[chosen][other], fixed[chosen]["cutoff"], d["w"][other]
        ),
    }
    record = {
        "largest_actor_sensitivity": dominant,
        "history_slices": {
            k: measure(y[sel], ps[chosen][sel], fixed[chosen]["cutoff"], d["w"][sel])
            for k, sel in support_groups.items()
        },
        "frozen_sha": file_sha256(run / "login-lock.json"),
        "metrics": metrics,
        "paired": paired,
        "learned_vs_selected_rule": match,
        "bootstrap": cluster_interval(d["u"], y, flag),
        "distinct_reference_vectors": len(count),
        "mixed_reference_vectors": int(((rate > 0) & (rate < count)).sum()),
        "history_coverage_all": float(d["valid"].mean()),
        "peer_coverage_all": float(peer.mean()),
        "RBA_task": "synthesized publisher incident flag vs no flag; no independently verified native negatives",
        "raw_rule": measure(y, raw_scores, 0.5, d["w"]),
        "T07_RELEASE": False,
    }
    atomic_json(run / "login-transfer.json", record)


if __name__ == "__main__":
    mode, r = sys.argv[1:]
    (train if mode == "train" else transfer)(Path(r))

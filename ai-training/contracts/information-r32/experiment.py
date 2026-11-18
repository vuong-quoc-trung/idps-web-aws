"""Matched low-FPR research study; keep model fitting, selection and held-domain tests distinct."""

import argparse
import os
import time
from pathlib import Path

import joblib
import numpy as np
from dataset import BASELINE, NAMES, need, verify
from rank_pilot import gate, macro, metrics
from scipy import sparse
from scipy.optimize import minimize
from scipy.special import expit, logit
from sklearn.ensemble import ExtraTreesClassifier
from symbols import BODY_START

from idps_ai.common import atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session

ARMS = ("SYMBOL_ONLY", "URI_RESIDUAL", "BODY_AND_URI_RESIDUAL", "TREE_BLEND")
RIDGE = 0.0003


def logodds(p):
    return logit(np.clip(p, 1e-7, 1 - 1e-7))


def sparse_head(x, y, w, offset):
    # No global intercept on a residual: an empty observation leaves B16 unchanged.
    def objective(b):
        s = offset + x @ b
        loss = w @ (np.logaddexp(0, s) - y * s) + 0.5 * RIDGE * (b @ b)
        return loss, np.asarray(x.T @ (w * (expit(s) - y))).ravel() + RIDGE * b

    result = minimize(
        objective,
        np.zeros(x.shape[1]),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 140, "ftol": 1e-10},
    )
    need(
        result.status in (0, 1)
        and np.isfinite(result.x).all()
        and result.fun <= objective(np.zeros(x.shape[1]))[0],
        "LOSS_OR_OPTIMIZER_FAILURE",
    )
    return result.x, {
        "iterations": int(result.nit),
        "status": int(result.status),
        "loss": float(result.fun),
        "initial": float(objective(np.zeros(x.shape[1]))[0]),
    }


def probabilities(session, x):
    slices = [
        session.run(["score"], {"input": x[i : i + 2048]})[0].reshape(-1)
        for i in range(0, len(x), 2048)
    ]
    p = np.concatenate(slices).astype(float)
    need(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all(), "B16_SCORES")
    return p


def keys(x, z):
    # The digest is over a fixed-width numeric prefix and sorted finite column IDs.
    import hashlib

    return np.array(
        [
            hashlib.sha256(
                a.tobytes()
                + z.indices[z.indptr[i] : z.indptr[i + 1]].astype("<i4", copy=False).tobytes()
            ).digest()
            for i, a in enumerate(x)
        ],
        dtype="V32",
    )


def census(ids, y):
    _, inv = np.unique(ids, return_inverse=True)
    inv = inv.reshape(-1)
    freq = np.zeros((int(inv.max()) + 1, 2), dtype=np.int64)
    np.add.at(freq, (inv, y), 1)
    return {
        "distinct": len(freq),
        "mixed_groups": int(np.all(freq > 0, axis=1).sum()),
        "minority_mass": int(freq.min(axis=1).sum()),
    }


def read_data(run, stage):
    folder = run / stage
    data = {}
    census_report = {}
    session = cpu_session(BASELINE, 1)
    for name in NAMES:
        witness = load_json(folder / (name + ".json"))
        need(witness["plan_sha256"] == file_sha256(run / "plan.json"), "ETL_PLAN_MISMATCH")
        for path, sha in witness["files"].items():
            need(file_sha256(folder / path) == sha, "STUDY_SHARD_CHANGED")
        z = sparse.load_npz(folder / (name + "-symbols.npz")).astype(np.float32)
        with np.load(folder / (name + ".npz"), allow_pickle=False) as a:
            x, y, groups, n, mass = a["x"], a["y"], a["group"], int(a["nfit"]), a["mass"]
        base = probabilities(session, x)
        census_report[name] = {}
        for role, ix in (("FIT", slice(0, n)), ("TUNING", slice(n, None))):
            v, sy, lab = x[ix], z[ix], y[ix]
            base_ids = v.view(dtype=np.dtype((np.void, v.dtype.itemsize * v.shape[1]))).reshape(-1)
            uni, inv, ct = np.unique(base_ids, return_inverse=True, return_counts=True)
            detailed = keys(v, sy)
            uri = keys(v, sy[:, :BODY_START])
            census_report[name][role] = {
                "n": len(v),
                "classes": np.bincount(lab, minlength=2).tolist(),
                "groups": len(np.unique(groups[ix])),
                "URI100": census(base_ids, lab),
                "plus_uri": census(uri, lab),
                "plus_uri_body": census(detailed, lab),
                "nonempty_body_features_by_label": np.bincount(
                    lab[np.diff(sy[:, BODY_START:].indptr) > 0], minlength=2
                ).tolist(),
            }
            if role == "FIT":
                w = mass.copy().astype(float)
                for label in (0, 1):
                    sel = lab == label
                    w[sel] /= 2 * w[sel].sum()
            else:
                w = 1.0 / ct[inv.reshape(-1)]
            data[name, role] = {
                "x": v,
                "z": sy,
                "y": lab,
                "group": groups[ix],
                "base": base[ix],
                "w": w,
                "keys": detailed,
            }
        need(
            not np.intersect1d(data[name, "FIT"]["keys"], data[name, "TUNING"]["keys"]).size,
            "ROLE_VECTOR_OVERLAP",
        )

    # An augmented row contains URI100, so checking its prefix across publishers
    # fences both raw+symbol models and the URI-only/tree comparator.
    def prefix(x):
        return x.view(dtype=np.dtype((np.void, x.dtype.itemsize * x.shape[1]))).reshape(-1)

    all_fit = np.concatenate([prefix(data[s, "FIT"]["x"]) for s in NAMES])
    all_tune = np.concatenate([prefix(data[s, "TUNING"]["x"]) for s in NAMES])
    need(not np.intersect1d(all_fit, all_tune).size, "CROSS_SOURCE_ROLE_VECTOR_OVERLAP")
    return data, census_report


def fit(run, data, names, arm, tag):
    y = np.concatenate([data[n, "FIT"]["y"] for n in names])
    weights = np.concatenate([data[n, "FIT"]["w"] for n in names]) / len(names)
    path = run / (tag + ".joblib")
    if arm == "TREE_BLEND":
        x = np.vstack([data[n, "FIT"]["x"] for n in names])
        model = ExtraTreesClassifier(
            n_estimators=96,
            max_depth=14,
            min_samples_leaf=4,
            max_features=0.7,
            n_jobs=1,
            random_state=3201,
        )
        model.fit(x, y, sample_weight=weights)
        diagnostics = {"trees": len(model.estimators_)}
    else:
        z = sparse.vstack([data[n, "FIT"]["z"] for n in names], format="csr", dtype=np.float64)
        base = np.concatenate([data[n, "FIT"]["base"] for n in names])
        if arm == "URI_RESIDUAL":
            z = z[:, :BODY_START]
        offset = np.zeros(len(y)) if arm == "SYMBOL_ONLY" else logodds(base)
        model, diagnostics = sparse_head(z, y, weights, offset)
    tmp = path.with_suffix(".tmp")
    joblib.dump(model, tmp, compress=3)
    tmp.replace(path)
    return model, {
        "sha256": file_sha256(path),
        "file": path.name,
        "fit_sources": list(names),
        "count": len(y),
        **diagnostics,
    }


def predict(model, arm, frame):
    if arm == "TREE_BLEND":
        prob = model.predict_proba(frame["x"])[:, 1]
        return expit((logodds(frame["base"]) + logodds(prob)) / 2)
    z = frame["z"]
    if arm == "URI_RESIDUAL":
        z = z[:, :BODY_START]
    s = z @ model
    return expit(s if arm == "SYMBOL_ONLY" else logodds(frame["base"]) + s)


def cluster_delta(frame, candidate, base, cut, base_cut):
    _, idx = np.unique(frame["group"], return_inverse=True)
    idx = idx.reshape(-1)
    lab = frame["y"].astype(float)
    t = np.bincount(idx, weights=lab)
    diff = ((candidate > cut).astype(int) - (base > base_cut).astype(int)) * lab
    d = np.bincount(idx, weights=diff)
    rng = np.random.default_rng(3201)
    values = []
    for _ in range(1000):
        draw = rng.integers(len(t), size=len(t))
        denom = t[draw].sum()
        if denom:
            values.append(d[draw].sum() / denom)
    return {
        "clusters": len(t),
        "valid_draws": len(values),
        "delta_recall_95pct": np.quantile(values, [0.025, 0.975]).tolist(),
    }


def run(out, stage):
    began = time.monotonic()
    verify(out, "study")
    plan = load_json(out / "plan.json")
    arms = ARMS
    if stage == "full":
        previous = load_json(out / "pilot-result.json")
        need(
            previous["advance"] and previous["plan_sha256"] == file_sha256(out / "plan.json"),
            "FULL_FIT_GATE",
        )
        arms = (previous["selected"],)
    data, cens = read_data(out, stage)
    folder = out / stage
    frames = {n: data[n, "TUNING"] for n in NAMES}
    weights = {
        n: {"original_request": np.ones(len(f["y"])), "vector_balanced": f["w"]}
        for n, f in frames.items()
    }
    base = {n: f["base"] for n, f in frames.items()}
    result = {"B16": metrics(base, frames, weights)}
    models, comparisons, diagnostics = {}, {}, {}
    for arm in arms:
        model, models[arm] = fit(folder, data, NAMES, arm, arm)
        scores = {n: predict(model, arm, f) for n, f in frames.items()}
        result[arm] = metrics(scores, frames, weights)
        comparisons[arm] = gate(result["B16"], result[arm], plan)
        diagnostics[arm] = {}
        for n, f in frames.items():
            cut = result[arm]["development_threshold"]
            base_cut = result["B16"]["development_threshold"]
            diagnostics[arm][n] = {
                **cluster_delta(f, scores[n], base[n], cut, base_cut),
                "brier": float(np.mean((scores[n] - f["y"]) ** 2)),
                "recovered_FN": int(
                    np.sum((f["y"] == 1) & (scores[n] > cut) & (base[n] <= base_cut))
                ),
                "lost_TP": int(np.sum((f["y"] == 1) & (scores[n] <= cut) & (base[n] > base_cut))),
            }
        print(
            arm,
            "macro",
            macro(result[arm]["common_budget"]),
            "transfer",
            comparisons[arm]["held_source_worst_fpr"],
            flush=True,
        )
    excluded = {}
    if stage == "pilot":
        for n in NAMES:
            names = [s for s in NAMES if s != n]
            model, models["EXCLUDE_" + n] = fit(folder, data, names, "SYMBOL_ONLY", "EXCLUDE_" + n)
            scores = {s: predict(model, "SYMBOL_ONLY", f) for s, f in frames.items()}
            # Only the other two TUNING domains set this cutoff.
            excluded[n] = metrics(scores, frames, weights)["held_source_transfer"][n]
    selected = max(
        arms, key=lambda a: (comparisons[a]["advance"], comparisons[a]["macro_recall_gain"])
    )
    atomic_json(
        out / (stage + "-result.json"),
        {
            "plan_sha256": file_sha256(out / "plan.json"),
            "stage": stage,
            "models": models,
            "census": cens,
            "results": result,
            "comparison": comparisons,
            "paired_clusters": diagnostics,
            "unseen_auxiliary_source": excluded,
            "selected": selected,
            "advance": comparisons[selected]["advance"],
            "seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("stage", choices=("pilot", "full"))
    a.add_argument("out", type=Path)
    args = a.parse_args()
    os.umask(0o077)
    run(args.out, args.stage)

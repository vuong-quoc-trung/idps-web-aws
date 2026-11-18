"""Fit on publisher TRAIN, lock coefficients and cutoffs, then measure transfer once."""

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.preprocessing import StandardScaler

from publisher import HERE, arrays, read
from history import ORDER, SCHEMA
from dataset import BASELINE, B16_PIN
from idps_ai.common import atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session

ARMS = ("B16", "URI100_LOGISTIC", "MEDIAN_GAP_RULE", "ROUTE_HISTORY", "CADENCE", "JOINT_HISTORY")
SLICES = {"ROUTE_HISTORY": slice(0, 4), "CADENCE": slice(4, 8), "JOINT_HISTORY": slice(0, 8)}


def features(data, arm):
    return data["hist"][:, SLICES[arm]] if arm in SLICES else data["uri"]


def take(data, mask):
    return {k: v[mask] for k, v in data.items()}


def fit(data, arm):
    x, y = features(data, arm), data["y"]
    counts = Counter(data["id"])
    weights = np.array([1 / counts[i] for i in data["id"]])
    for label in (0, 1):
        weights[y == label] *= len(counts) / (2 * weights[y == label].sum())
    scaler = StandardScaler().fit(x, sample_weight=weights)
    lr = LogisticRegression(C=0.5, max_iter=1000).fit(scaler.transform(x), y, sample_weight=weights)
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
    }


def linear(x, model):
    return expit(
        (x - np.array(model["mean"])) / model["scale"] @ model["coef"] + model["intercept"]
    )


def scores(data, arm, model):
    if arm == "B16":
        if file_sha256(BASELINE) != B16_PIN:
            raise ValueError("unexpected B16 artifact")
        return cpu_session(BASELINE, 1).run(["score"], {"input": data["uri"]})[0].ravel()
    if arm == "MEDIAN_GAP_RULE":
        return np.exp(-data["hist"][:, 5])
    return linear(features(data, arm), model)


def threshold(y, p):
    negatives = np.sort(p[y == 0])[::-1]
    if len(negatives) == 0:
        raise ValueError("missing negative support")
    return float(negatives[len(negatives) // 100])


def measure(y, p, t, weights=None):
    w = np.ones(len(y)) if weights is None else weights
    h = p > t
    pos, neg = w[y == 1].sum(), w[y == 0].sum()
    tp, fp = w[h & (y == 1)].sum(), w[h & (y == 0)].sum()
    good = np.isfinite(p)
    result = {
        "n": len(y),
        "positive": int(y.sum()),
        "fp": float(fp),
        "tp": float(tp),
        "recall": float(tp / pos) if pos else None,
        "fpr": float(fp / neg) if neg else None,
        "precision": float(tp / (tp + fp)) if tp + fp else None,
        "coverage": float(w[good].sum() / w.sum()),
    }
    if good.any() and len(np.unique(y[good])) == 2:
        a, b, v = p[good], y[good], w[good]
        ece = 0.0
        for i in range(10):
            selected = np.minimum((a * 10).astype(int), 9) == i
            ece += abs(np.sum((a[selected] - b[selected]) * v[selected])) / v.sum()
        result.update(
            ap=float(average_precision_score(b, a, sample_weight=v)),
            brier=float(np.average((a - b) ** 2, weights=v)),
            ece=float(ece),
        )
    return result


def census(vector, y):
    _, inv = np.unique(vector, axis=0, return_inverse=True)
    inv = inv.ravel()
    pos = np.bincount(inv, weights=y)
    neg = np.bincount(inv, weights=1 - y)
    return {
        "distinct": len(pos),
        "mixed": int(np.sum((pos > 0) & (neg > 0))),
        "minority_mass": int(np.minimum(pos, neg).sum()),
        "rows": len(y),
    }


def summarize(data, arm, model, t):
    eligible = np.isfinite(data["hist"][:, 0])
    if not eligible.any():
        raise ValueError("no eligible window")
    p = np.full(len(eligible), np.nan)
    hist_arm = arm not in ("URI100_LOGISTIC", "B16")
    valid = eligible if hist_arm else np.ones_like(eligible)
    p[valid] = scores(take(data, valid), arm, model)
    y = data["y"]
    common = take(data, eligible)
    vx = features(common, arm) if arm != "MEDIAN_GAP_RULE" else common["hist"][:, 5:6]
    _, inv, ns = np.unique(vx, axis=0, return_inverse=True, return_counts=True)
    ids, first = np.unique(common["id"], return_index=True)
    result = {
        "all": measure(y, p, t),
        "common": measure(y[eligible], p[eligible], t),
        "first_supported_per_session": measure(y[eligible][first], p[eligible][first], t),
        "vector_balanced_common": measure(y[eligible], p[eligible], t, 1 / ns[inv.ravel()]),
        "families": {
            k: measure(y[idx], p[idx], t)
            for k in np.unique(data["kind"])
            if (idx := data["kind"] == k).any()
        },
    }
    # Resample complete sessions within publisher classes; same session gets one draw.
    c = []
    for label in (0, 1):
        sessions = np.unique(data["id"][y == label])
        pairs = np.array(
            [(np.sum((p > t) & (data["id"] == s)), np.sum(data["id"] == s)) for s in sessions]
        )
        draws = np.random.default_rng(3300 + label).integers(0, len(pairs), (1000, len(pairs)))
        totals = pairs[draws].sum(axis=1)
        c.append(np.quantile(totals[:, 0] / totals[:, 1], [0.025, 0.975]).tolist())
    result["session_bootstrap95_all"] = {"fpr": c[0], "recall": c[1]}
    return result


def schema_census(data):
    ix = np.isfinite(data["hist"][:, 0])
    x, y, h = data["uri"][ix], data["y"][ix], data["hist"][ix]
    return {
        k: census(v, y)
        for k, v in {
            "uri100": x,
            "uri100_plus_route": np.c_[x, h[:, :4]],
            "uri100_plus_history": np.c_[x, h],
        }.items()
    }


def study(run, mode):
    lock, result = run / "frozen.json", run / "transfer.json"
    if (lock if mode == "fit" else result).exists():
        raise ValueError("immutable output already exists")
    phase = "phase1" if mode == "fit" else "phase2"
    if mode == "transfer":
        frozen = load_json(lock)
        if (
            file_sha256(HERE / "protocol.json") != frozen["protocol_sha"]
            or frozen["code"] != code_pins()
        ):
            raise ValueError("frozen protocol or study code changed")
    rows, labels, availability, roster = read(run, phase)
    data = arrays(rows)
    if mode == "fit":
        tune_ids = {
            sid
            for k in sorted(set(labels.values()))
            for sid in sorted(s for s, a in labels.items() if a == k)[::4]
        }
        tune = np.isin(data["id"], list(tune_ids))
        train = take(data, ~tune & np.isfinite(data["hist"][:, 0]))
        dev = take(data, tune)
        common = take(dev, np.isfinite(dev["hist"][:, 0]))
        if set(train["id"]) & set(dev["id"]):
            raise ValueError("session overlap")
        arms, metrics = {}, {}
        for arm in ARMS:
            m = {} if arm in ("B16", "MEDIAN_GAP_RULE") else fit(train, arm)
            t = (
                0.9420260190963745
                if arm == "B16"
                else threshold(common["y"], scores(common, arm, m))
            )
            arms[arm] = {"model": m, "cutoff_strict": t}
            metrics[arm] = summarize(dev, arm, m, t)
        winner = max(
            SLICES,
            key=lambda k: (
                metrics[k]["all"]["recall"],
                metrics[k]["common"]["ap"],
                -len(arms[k]["model"]["coef"]),
            ),
        )
        atomic_json(
            run / "fit-result.json",
            {
                "arms": metrics,
                "census_fit": schema_census(train),
                "census_tuning": schema_census(dev),
                "fit_scored": len(train["y"]),
                "fit_sessions_scored": len(set(train["id"])),
                "tuning_sessions": len(tune_ids),
                "availability_before_split": availability,
                "annotated_classes": roster,
            },
        )
        atomic_json(
            lock,
            {
                "schema": SCHEMA,
                "order": ORDER,
                "selected": winner,
                "arms": arms,
                "phase1_ids": sorted(labels),
                "fit_report_sha": file_sha256(run / "fit-result.json"),
                "protocol_sha": file_sha256(HERE / "protocol.json"),
                "code": code_pins(),
                "b16_sha": B16_PIN,
            },
        )
    else:
        if set(labels) & set(frozen["phase1_ids"]):
            raise ValueError("cross-phase session reuse")
        metrics = {
            k: summarize(data, k, v["model"], v["cutoff_strict"]) for k, v in frozen["arms"].items()
        }
        atomic_json(
            result,
            {
                "frozen_sha": file_sha256(lock),
                "arms": metrics,
                "census": schema_census(data),
                "availability": availability,
                "annotated_classes": roster,
                "publisher_phase": "phase2",
                "exact_session_overlap": 0,
                "official_t07": False,
            },
        )


def code_pins():
    return {name: file_sha256(HERE / name) for name in ("study.py", "publisher.py", "history.py")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("fit", "transfer"))
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    study(args.run, args.mode)

"""FIT-only local support from different templates and publishers for frozen B16."""

import argparse
import time
from pathlib import Path

import joblib
import numpy as np
from dataset import NAMES, need
from experiment import cluster_delta, logodds, read_data
from rank_pilot import gate, macro, metrics
from scipy.special import expit
from sklearn.neighbors import NearestNeighbors

from idps_ai.common import atomic_json, file_sha256, load_json

K = 32
GROUPS = 3
ARMS = ("SUPPORTED_VOTE", "BENIGN_VETO")


def local_evidence(near, dist, groups, positive, radius, excluded=None):
    count = len(near)
    signed = np.zeros(count)
    scale = np.zeros(count)
    spread = np.full(count, np.inf)
    for i, (ids, d) in enumerate(zip(near, dist, strict=True)):
        seen = set() if excluded is None else {excluded[i]}
        chosen = []
        for j, (key, gap) in enumerate(zip(ids, d, strict=True)):
            group = groups[key]
            if group in seen:
                continue
            seen.add(group)
            chosen.append(j)
            if len(chosen) == GROUPS:
                break
        if len(chosen) != GROUPS:
            continue
        spread[i] = d[chosen[-1]]
        if spread[i] > radius:
            continue
        # One bounded vote per distinct neighboring lineage, including mixed labels.
        signed[i] = (2 * positive[ids[chosen]] - 1).mean()
        scale[i] = 1.0
    return signed, scale, spread


def fitted(frame, scale):
    x = frame["x"]
    unique, first, inv = np.unique(x, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    mass = frame["w"]
    posterior = np.bincount(inv, weights=frame["y"] * mass) / np.bincount(inv, weights=mass)
    groups = frame["group"][first]
    need(np.array_equal(groups[inv], frame["group"]), "NEIGHBOR_COMPONENT_AMBIGUOUS")
    bank = np.ascontiguousarray(unique * scale, dtype=np.float32)
    ix = NearestNeighbors(n_neighbors=K, algorithm="brute", metric="euclidean", n_jobs=1).fit(bank)
    anchors = np.random.default_rng(3202).choice(len(bank), min(768, len(bank)), replace=False)
    d, n = ix.kneighbors(bank[anchors])
    _, _, spread = local_evidence(n, d, groups, posterior, np.inf, excluded=groups[anchors])
    radius = float(np.median(spread[np.isfinite(spread)]))
    need(radius > 0 and np.isfinite(radius), "NEIGHBOR_RADIUS")
    return ix, groups, posterior, radius


def study(out, stage):
    began = time.monotonic()
    parent = load_json(out / "plan.json")
    plan = load_json(out / "neighbors-plan.json")
    need(
        file_sha256(__file__) == plan["code"]
        and file_sha256(out / "pilot-result.json") == plan["preceding_pilot"],
        "NEIGHBOR_PROTOCOL_CHANGED",
    )
    arms = ARMS
    if stage == "full":
        chosen = load_json(out / "neighbors-pilot.json")
        need(chosen["advance"], "NEIGHBOR_FULL_GATE")
        arms = (chosen["selected"],)
    data, _ = read_data(out, stage)
    tune = {n: data[n, "TUNING"] for n in NAMES}
    weights = {
        n: {"original_request": np.ones(len(f["y"])), "vector_balanced": f["w"]}
        for n, f in tune.items()
    }
    # Equal influence of FIT domains on dimension scaling, no target statistics.
    scale = 1 / np.maximum(
        np.sqrt(np.mean([np.var(data[n, "FIT"]["x"], axis=0) for n in NAMES], axis=0)), 0.1
    )
    fit = {n: fitted(data[n, "FIT"], scale) for n in NAMES}
    dest = out / stage / "neighborhood.joblib"
    tmp = dest.with_suffix(".tmp")
    joblib.dump((scale, fit), tmp, compress=3)
    tmp.replace(dest)
    base = {n: f["base"] for n, f in tune.items()}
    evidence, coverage = {}, {}
    for n, f in tune.items():
        u, inv = np.unique(f["x"], axis=0, return_inverse=True)
        votes = []
        coverage[n] = {}
        for src, (index, groups, pos, radius) in fit.items():
            ds, ns = index.kneighbors(np.ascontiguousarray(u * scale, dtype=np.float32))
            v, s, _ = local_evidence(ns, ds, groups, pos, radius)
            votes.append((v * s)[inv.reshape(-1)])
            coverage[n][src] = float(s[inv.reshape(-1)].mean())
        # The second most supportive source determines corroboration. A zero vote
        # is neutral for missing support; a single source cannot move the score.
        median = np.median(votes, axis=0)
        evidence[n] = median
        coverage[n]["corroborated_fraction"] = float(np.mean(median != 0))
    results = {"B16": metrics(base, tune, weights)}
    comparisons, uncertainty = {}, {}
    for arm in arms:
        scores = {
            n: expit(
                logodds(base[n])
                + 2 * (evidence[n] if arm == "SUPPORTED_VOTE" else np.minimum(evidence[n], 0))
            )
            for n in NAMES
        }
        results[arm] = metrics(scores, tune, weights)
        comparisons[arm] = gate(results["B16"], results[arm], parent)
        uncertainty[arm] = {
            n: cluster_delta(
                tune[n],
                scores[n],
                base[n],
                results[arm]["development_threshold"],
                results["B16"]["development_threshold"],
            )
            for n in NAMES
        }
        print(arm, macro(results[arm]["common_budget"]), flush=True)
    selected = max(
        arms, key=lambda a: (comparisons[a]["advance"], comparisons[a]["macro_recall_gain"])
    )
    atomic_json(
        out / ("neighbors-" + stage + ".json"),
        {
            "results": results,
            "comparison": comparisons,
            "selected": selected,
            "advance": comparisons[selected]["advance"],
            "cluster_intervals": uncertainty,
            "support": coverage,
            "radius": {n: v[-1] for n, v in fit.items()},
            "checkpoint": file_sha256(dest),
            "plan_sha256": file_sha256(out / "neighbors-plan.json"),
            "seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("plan", "pilot", "full"))
    p.add_argument("out", type=Path)
    a = p.parse_args()
    if a.phase == "plan":
        need(not (a.out / "neighbors-plan.json").exists(), "PLAN_ALREADY_LOCKED")
        atomic_json(
            a.out / "neighbors-plan.json",
            {
                "code": file_sha256(__file__),
                "preceding_pilot": file_sha256(a.out / "pilot-result.json"),
                "parent_plan": file_sha256(a.out / "plan.json"),
                "budget": "two fixed neighborhood corrections, one research phase, same R31 development gate",
                "hypothesis": "nonlinear local class evidence across different templates and publishers can remove high-scoring benign tail cases",
                "arms": list(ARMS),
                "k": K,
                "distinct_groups_per_source": GROUPS,
                "fit_radius_anchor_count": 768,
                "scale_floor": 0.1,
                "frozen_external": "Public corpus SHA 9126e43da413bee16cb543a8d0b9187819d312303f83c83e57d8bda3b1ecfd86 reserved for one post-selection assessment; no model tuning.",
            },
        )
    else:
        study(a.out, a.phase)

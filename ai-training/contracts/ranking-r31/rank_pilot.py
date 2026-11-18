"""Train bounded low-FPR readouts on FIT and evaluate on publisher TUNING."""

import argparse
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint, validate_generation
from idps_ai.training.tabular import forward

HERE = Path(__file__).resolve().parent
sys.path[:0] = [
    str(HERE.parent / name)
    for name in ("quality-study-r30", "quality-acceleration-r26", "development-bulk-v1")
]
from calibration_pilot import (  # noqa: E402  # noqa: E402
    B16_PIN,
    BASELINE,
    CAP,
    FOLDERS,
    ROOT,
    collision_bound,
    compare,
    cut_at_cap,
    role,
    score,
    waf_tuning,
)
from r26_learning import cells  # noqa: E402

PARENT = ROOT / "augmentation-b/training/model/checkpoints/step-000000000400-fead25dafe62"
PARENT_PIN = "0f0b0d8ab173d8c7ff0dba43809837d240c5dd307f75c340b6706fda9593d6e7"
WAF = ROOT / "data-v2/waf-r26.npz"
TAIL = 0.05
SAMPLE = 24
ARMS = ("WITHIN_SOURCE", "CROSS_SOURCE")
ROUNDS = 2
MAX_ITER = 70
TRUST = 0.12
RIDGE = 0.005
MARGIN = 0.5


def need(condition, reason):
    if not condition:
        raise PipelineError(reason)


def create_plan(out):
    plan = out / "plan.json"
    need(not plan.exists(), "PLAN_ALREADY_LOCKED")
    manifest = load_json(ROOT / "data-v2/waf-manifest.json")
    need(
        manifest["roles_preserved"]
        and not manifest["protected_payloads_read"]
        and not manifest["publisher_eval_test_heldout_read"],
        "WAF_ROLE_MISMATCH",
    )
    pins = {
        str(BASELINE): B16_PIN,
        str(WAF): manifest["dataset_sha256"],
        str(PARENT / "manifest.json"): PARENT_PIN,
    }
    for folder in FOLDERS.values():
        root = ROOT / folder
        manifest = load_json(root / "manifest.json")
        for name in ("FIT", "TUNING"):
            pins[str(root / f"{name.lower()}.npz")] = manifest["roles"][name]["sha256"]
    for name in (
        "quality-study-r30/calibration_pilot.py",
        "quality-acceleration-r26/r26_learning.py",
    ):
        path = HERE.parent / name
        pins[str(path)] = file_sha256(path)
    atomic_json(
        plan,
        {
            "version": "idps-r31-rank-pilot-v1",
            "code_sha256": file_sha256(__file__),
            "pins": pins,
            "parent_checkpoint": PARENT_PIN,
            "fit_scope": "Locked WAF FIT pilot_position/mass and all Notes/SRBH FIT; counts and mixed labels retained",
            "full_scope_if_accepted": "Same optimization and passes with all original FIT rows",
            "selection_scope": "Publisher TUNING only; shared strict cutoff with 1% cap per source, original and vector weighted",
            "transfer_scope": "Threshold from other two TUNING sources, scored on the excluded source. Backbone and readout can see that source FIT.",
            "arms": list(ARMS),
            "objective": {
                "tail": TAIL,
                "margin": MARGIN,
                "stratified_hard_negatives_per_domain": SAMPLE,
                "retention": TRUST,
                "ridge": RIDGE,
                "rounds": ROUNDS,
                "lbfgs_maxiter": MAX_ITER,
            },
            "advance_min_macro_recall_gain": 0.05,
            "advance_max_original_or_vector_recall_regression_per_source": 0.02,
            "advance_held_source_fpr_cap": CAP,
            "advance_held_source_macro_recall_gain_must_be_positive": True,
            "test_or_stress_used": False,
        },
    )


def waf_fit(full):
    with np.load(WAF, allow_pickle=False) as z:
        n = int(z["nfit"])
        labels = z["y"][:n]
        need(n == 400_000, "WAF_FIT_CARDINALITY_MISMATCH")
        if full:
            positions, mass = np.arange(n), None
        else:
            positions = z["pilot_position"]
            order = np.argsort(positions, kind="stable")
            positions, mass = positions[order], z["pilot_mass"][order]
            need(
                len(positions) == len(np.unique(positions))
                and positions.min() >= 0
                and positions.max() < n
                and np.isfinite(mass).all()
                and (mass > 0).all(),
                "WAF_PILOT_FIT_SCOPE_MISMATCH",
            )
    result = np.empty((len(positions), 100), dtype=np.float32)
    with zipfile.ZipFile(WAF) as archive, archive.open("x.npy") as stream:
        need(np.lib.format.read_magic(stream) == (1, 0), "WAF_TENSOR_HEADER")
        shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
        need(
            shape == (406042, 244) and not fortran and dtype == np.dtype("<f4"), "WAF_TENSOR_SCOPE"
        )
        for start in range(0, n, 8192):
            end = min(start + 8192, n)
            width = (end - start) * shape[1] * 4
            chunk = stream.read(width)
            need(len(chunk) == width, "WAF_FIT_TENSOR_TRUNCATED")
            left, right = np.searchsorted(positions, [start, end])
            values = np.frombuffer(chunk, dtype=dtype).reshape(-1, shape[1])
            result[left:right] = values[positions[left:right] - start, :100]
    return result, labels[positions], mass


def representations(model, x):
    states, scores = [], []
    for start in range(0, len(x), 1024):
        hidden, _, cache = forward(model, x[start : start + 1024])
        logits = cache[-1][1].astype(np.float64)
        states.append(hidden.astype(np.float64))
        scores.append(logsumexp(logits[:, 1:], axis=1) - logits[:, 0])
    return np.concatenate(states), np.concatenate(scores)


def weighted_tail(ids, scores, weights):
    # Account for partial weight of the first negative crossing the tail boundary.
    order = ids[np.argsort(-scores[ids], kind="stable")]
    mass = weights[order]
    cdf = np.cumsum(mass)
    ranks = (np.arange(SAMPLE) + 0.5) * TAIL * cdf[-1] / SAMPLE
    return order[np.searchsorted(cdf, ranks)]


def objective(theta, features, base, row_mass, pair_sets):
    residual = features @ theta
    scores = base + residual
    grad_score = 2 * TRUST * row_mass * residual
    f = TRUST * np.dot(row_mass, residual**2) + RIDGE * np.dot(theta, theta)
    for positive, weight, hard in pair_sets:
        d = MARGIN + scores[hard][None, :] - scores[positive][:, None]
        mass = weight[:, None] / (len(pair_sets) * len(hard))
        f += np.sum(np.logaddexp(0.0, d) * mass)
        g = expit(d) * mass
        grad_score[positive] -= g.sum(axis=1)
        np.add.at(grad_score, hard, g.sum(axis=0))
    return float(f), features.T @ grad_score + 2 * RIDGE * theta


def fit_head(out, name, features, base, y, row_mass, domain, binding):
    params = np.zeros(features.shape[1], np.float64)
    previous = []
    for round_index in range(ROUNDS):
        path = out / f"{name.lower()}-round{round_index + 1}.json"
        if path.exists():
            saved = load_json(path)
            need(
                saved["binding"] == binding
                and saved["prior_round_sha256"]
                == (file_sha256(previous[-1]) if previous else None),
                "READOUT_RESUME_BINDING_MISMATCH",
            )
            params = np.asarray(saved["coefficients"], np.float64)
            need(
                params.shape == (features.shape[1],) and np.isfinite(params).all(),
                "INVALID_RESUMED_READOUT",
            )
            previous.append(path)
            continue
        scores = base + features @ params
        positives, negatives = [], []
        for i in range(3):
            pos = np.flatnonzero((domain == i) & (y == 1))
            neg = np.flatnonzero((domain == i) & (y == 0))
            need(len(pos) > 0 and len(neg) > 0, "MISSING_FIT_CLASS")
            positives.append((pos, row_mass[pos] / row_mass[pos].sum()))
            negatives.append(weighted_tail(neg, scores, row_mass))
        pairs = [
            (ids, w, hs)
            for i, (ids, w) in enumerate(positives)
            for j, hs in enumerate(negatives)
            if name == "CROSS_SOURCE" or i == j
        ]
        initial, _ = objective(params, features, base, row_mass, pairs)
        result = minimize(
            objective,
            params,
            jac=True,
            method="L-BFGS-B",
            args=(features, base, row_mass, pairs),
            options={"maxiter": MAX_ITER, "ftol": 1e-10, "gtol": 1e-6},
        )
        need(
            result.status in (0, 1)
            and np.isfinite(result.fun)
            and np.isfinite(result.x).all()
            and result.fun <= initial + 1e-9,
            "READOUT_OPTIMIZATION_FAILED",
        )
        params = result.x
        atomic_json(
            path,
            {
                "binding": binding,
                "prior_round_sha256": file_sha256(previous[-1]) if previous else None,
                "coefficients": params.tolist(),
                "loss_before": initial,
                "loss_after": float(result.fun),
                "iterations": int(result.nit),
                "optimizer_status": int(result.status),
                "pair_components": len(pairs),
                "distinct_sampled_hard_negatives": [len(np.unique(hs)) for hs in negatives],
            },
        )
        previous.append(path)
    return params, [file_sha256(path) for path in previous]


def metrics(scores, frames, weights):
    def cutoff(names):
        return max(
            cut_at_cap(scores[name], weight * (frames[name]["y"] == 0))
            for name in names
            for weight in weights[name].values()
        )

    def cell(name, threshold):
        return {
            scope: compare(frames[name]["y"], scores[name], threshold, weight)
            for scope, weight in weights[name].items()
        }

    fixed = cutoff(frames)
    return {
        "development_threshold": fixed,
        "common_budget": {name: cell(name, fixed) for name in frames},
        "held_source_transfer": {
            name: cell(name, cutoff(tuple(key for key in frames if key != name))) for name in frames
        },
    }


def macro(block):
    return float(np.mean([cell["original_request"]["recall"] for cell in block.values()]))


def gate(baseline, candidate, spec):
    improvement = macro(candidate["common_budget"]) - macro(baseline["common_budget"])
    transfer_gain = macro(candidate["held_source_transfer"]) - macro(
        baseline["held_source_transfer"]
    )
    delta = {
        name: {
            label: candidate["common_budget"][name][label]["recall"]
            - baseline["common_budget"][name][label]["recall"]
            for label in labels
        }
        for name, labels in baseline["common_budget"].items()
    }
    worst = max(
        m["FPR"] for cell in candidate["held_source_transfer"].values() for m in cell.values()
    )
    max_tune_tpr_loss = min(d for cell in delta.values() for d in cell.values())
    passed = (
        improvement >= spec["advance_min_macro_recall_gain"]
        and max_tune_tpr_loss
        >= -spec["advance_max_original_or_vector_recall_regression_per_source"]
        and worst <= spec["advance_held_source_fpr_cap"]
        and transfer_gain > 0
    )
    return {
        "macro_recall_gain": improvement,
        "recall_gain_by_source": delta,
        "held_source_macro_recall_gain": transfer_gain,
        "held_source_worst_fpr": worst,
        "advance": passed,
    }


def run(out, full):
    began = time.monotonic()
    plan = out / "plan.json"
    spec = load_json(plan)
    need(spec["code_sha256"] == file_sha256(__file__), "IMPLEMENTATION_CHANGED_AFTER_PLAN")
    for name, sha in spec["pins"].items():
        need(file_sha256(name) == sha, "PILOT_INPUT_PIN_MISMATCH")
    validate_generation(PARENT, PARENT_PIN)
    parent = load_checkpoint(PARENT).model
    need(
        parent.kind == "residual_glu" and parent.input_dim == 100 and parent.steps == 400, "NOT_B16"
    )
    arms = ARMS
    if full:
        prior = load_json(out / "pilot.json")
        need(
            prior["plan_sha256"] == file_sha256(plan) and prior["full_train_justified"],
            "PILOT_GATE_FAILED",
        )
        arms = (prior["selected"],)
    work = out / ("full" if full else "pilot")
    work.mkdir(exist_ok=True, mode=0o700)
    binding = file_sha256(plan) + ("-full" if full else "-pilot")

    cohorts, labels, weights, domains, input_counts = [], [], [], [], {}
    wx, wy, wm = waf_fit(full)
    fit = {"WAF": (wx, wy, wm)}
    for name, folder in FOLDERS.items():
        frame = role(folder, "FIT")
        fit[name] = frame["x"], frame["y"], None
    for i, (name, (x, y, w)) in enumerate(fit.items()):
        nx, ny, nw, summary = cells(x, y, 100, w)
        cohorts.append(nx)
        labels.append(ny)
        weights.append(nw)
        domains.append(np.full(len(ny), i))
        input_counts[name] = summary
    del fit, wx, wy, wm, nx, x
    train_x = np.concatenate(cohorts)
    y, row_mass, domain = map(np.concatenate, (labels, weights, domains))
    row_mass /= row_mass.sum()
    hidden, parent_logits = representations(parent, train_x)
    center = row_mass @ hidden
    scale = np.maximum(np.sqrt(row_mass @ ((hidden - center) ** 2)), 0.05)
    features = (hidden - center) / scale
    del hidden
    coefficients, stages = {}, {}
    for name in arms:
        coefficients[name], stages[name] = fit_head(
            work, name, features, parent_logits, y, row_mass, domain, binding
        )
    frames = {"WAF": waf_tuning(WAF)}
    frames.update({name: role(folder, "TUNING") for name, folder in FOLDERS.items()})
    session = cpu_session(BASELINE, 1)
    tuning_weights, scores, collision = {}, {"B16": {}}, {}
    scores.update({name: {} for name in arms})
    for name, frame in frames.items():
        values, vw, inverse, counts = score(session, frame)
        scores["B16"][name] = values
        tuning_weights[name] = {"original_request": np.ones(len(values)), "vector_balanced": vw}
        collision[name] = collision_bound(frame["y"], inverse, len(counts))
        h, z = representations(parent, frame["x"])
        for arm in arms:
            scores[arm][name] = expit(z + ((h - center) / scale) @ coefficients[arm])
    results = {name: metrics(arm, frames, tuning_weights) for name, arm in scores.items()}
    comparisons = {name: gate(results["B16"], results[name], spec) for name in arms}
    selected = max(
        arms,
        key=lambda name: (comparisons[name]["advance"], comparisons[name]["macro_recall_gain"]),
    )
    accepted = comparisons[selected]["advance"]
    if accepted:
        w = coefficients[selected] / scale
        # Adding a scalar to attack-vs-benign log odds is equivalent to lowering logit 0.
        atomic_json(
            work / "merged-head.json",
            {
                "subtract_from_benign_column": w.tolist(),
                "add_to_benign_bias": float(center @ w),
                "parent_sha256": PARENT_PIN,
                "plan_sha256": file_sha256(plan),
            },
        )
    return {
        "scope": "PUBLISHER_DEVELOPMENT_ONLY",
        "plan_sha256": file_sha256(plan),
        "phase": "FULL_FIT" if full else "PILOT_FIT",
        "elapsed_seconds": time.monotonic() - began,
        "fit_sources": input_counts,
        "fit_weighted_cells": len(y),
        "OPTIMIZATION_checkpoints_sha256": stages,
        "TUNING_class_counts": {
            n: np.bincount(f["y"], minlength=2).tolist() for n, f in frames.items()
        },
        "TUNING_collision_diagnostics": collision,
        "TUNING_metrics": results,
        "comparison": comparisons,
        "selected": selected,
        "full_train_justified": accepted and not full,
        "calibration_justified": accepted and full,
        "decision": ("ADVANCE_FROZEN_READOUT" if accepted else "KEEP_B16"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "pilot", "full"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode == "plan":
        create_plan(args.output)
    else:
        target = args.output / (args.mode + ".json")
        need(not target.exists(), "PHASE_ALREADY_COMPLETED")
        atomic_json(target, run(args.output, args.mode == "full"))

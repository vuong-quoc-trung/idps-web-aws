"""Run bounded URI76 objective ablations and prepare a shadow-only handoff."""

import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import onnx
from r18_data import check, read, status
from r18_train import logistic_onnx, shadow
from r19_metrics import metrics_both
from r19_train import SEED, partition, training_cells
from r20_calibration import threshold
from r20_quality import PINS, R19, cpu_benchmark, role
from sklearn.linear_model import LogisticRegression

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint

R20 = R19.with_name("t09-r20-quality-OktqJbDt")
R20_ONNX = "1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525"
R20_SELECTION = "1a352cd7beb490f8fa9f36e8cad46f6862155249d619ed05e2c2d7eeadd113fc"
R10 = R19.with_name("t09-r10-context-20261117")
R10_LEDGER = R10 / "campaign-1-a1/adapter/guest/receipt-ledger.jsonl"
SCHEMES = ("uniform_vector", "class_mass_preserved", "hard_normal")
BASE = "r20_isotonic"


def lock(path, value):
    if path.exists():
        check(read(path) == value, f"Locked record differs: {path.name}")
    else:
        atomic_json(path, value)


def predict(session, x):
    return session.run(["score"], {"input": x})[0]


def weight_ablation(counts, frozen_fit_scores, scheme):
    """Change one weighting choice while retaining every original label cell."""
    groups, labels, cell, balance, _ = training_cells(counts)
    if scheme == "uniform_vector":
        cell = counts[groups, labels] / counts.sum(axis=1)[groups]
        by_class = np.bincount(labels, weights=cell, minlength=2)
        balance = by_class.sum() / (2 * by_class)
    elif scheme == "class_mass_preserved":
        balance = np.ones_like(balance)
    elif scheme == "hard_normal":
        # FIT-only score quantile over vectors with benign mass. Compare with
        # the same class-balanced objective and redistribute negative mass.
        cutoff = np.quantile(frozen_fit_scores[counts[:, 0] > 0], 0.9)
        cell = cell * np.where((labels == 0) & (frozen_fit_scores[groups] >= cutoff), 4.0, 1.0)
        by_class = np.bincount(labels, weights=cell, minlength=2)
        balance = by_class.sum() / (2 * by_class)
    else:
        raise ValueError(f"Unknown weighting scheme: {scheme}")
    return groups, labels, cell * balance[labels]


def dual_cut(counts, scores):
    return max(threshold(counts, scores), threshold(counts, scores, vector_balance=True))


def advances(candidate, baseline, *, tuning):
    for unit, row in candidate.items():
        reference = baseline[unit]
        if row["fpr"] > 0.01 + 1e-12 or row["ap"] < reference["ap"] - 0.005:
            return False
        minimum_gain = 0.02 if tuning and unit == "original_request" else 0.0
        if row["recall"] < reference["recall"] + minimum_gain:
            return False
    return True


def native_evidence(out):
    sys.path.insert(0, str(REPO_ROOT / "ai-training/contracts/local-acceptance-v1"))
    from readiness import R10_SHA, engineering, receipts, reviewed

    native = reviewed()
    witness = engineering()
    same_uri = [
        row
        for row in receipts(R10_LEDGER, R10_SHA).values()
        if "representation_history" in row["uri76"]
    ]
    vectors, history_keys = set(), set()
    maximum_ns = 0
    for row in same_uri:
        projected = row["uri76"]
        history = projected["representation_history"]
        check(
            history["scope"] == "THIS_RECEIVER_OBSERVED_STREAM_ONLY"
            and history["window_covered_since_receiver_start"]
            and not history["history_truncated"]
            and row["cutoff_ns"] == 1_000_000_000
            and row["clock_guard_ns"] == 1_000_000
            and projected["projection_offset_ns"] <= row["cutoff_ns"] - row["clock_guard_ns"],
            "Historical projection lacks valid request-time history",
        )
        key = projected["projection_sha256"]
        vectors.add(key)
        history_keys.add((key, history["prior_same_uri76_vector"]))
        maximum_ns = max(maximum_ns, projected["projection_offset_ns"])
    check(len(vectors) == 1 and len(history_keys) == len(same_uri) == 3, "R10 ablation changed")
    atomic_json(
        out / "native.json",
        {
            "intake": {key: value for key, value in native.items() if key != "requests"},
            "archive": {key: value for key, value in witness.items() if key != "rows"},
            "history_control": {
                "scope": "BENIGN_ENGINEERING_ONLY",
                "request_count": len(same_uri),
                "distinct_uri76": len(vectors),
                "distinct_uri76_with_prior_same_vector_count": len(history_keys),
                "projection_offset_max_ns": maximum_ns,
                "detection_ablation": "BLOCKED_NO_TWO_CLASS_REQUEST_BOUND_COHORT",
            },
        },
    )


def run(out):
    status(out, "PIN_AND_PREFLIGHT")
    for name, sha in PINS.items():
        check(file_sha256(R19 / name) == sha, f"Frozen R19 digest differs: {name}")
    check(file_sha256(R20 / "bundle/swiglu.onnx") == R20_ONNX, "R20 ONNX differs")
    check(file_sha256(R20 / "calibration-selection.json") == R20_SELECTION, "R20 threshold differs")
    checkpoint_pin = read(R19 / "training/model/best.json")
    checkpoint = R19 / "training/model" / checkpoint_pin["path"]
    check(
        file_sha256(checkpoint / "manifest.json") == checkpoint_pin["manifest_sha256"],
        "R19 checkpoint manifest",
    )
    # The loader also verifies every pinned state file in the generation.
    saved = load_checkpoint(checkpoint)
    check(saved.model.steps == checkpoint_pin["global_step"], "R19 checkpoint cursor")
    lock(
        out / "plan.json",
        {
            "scope": "WAF_PUBLISHER_TRAIN_NORMAL_ANOMALOUS_DEVELOPMENT",
            "runner_sha256": file_sha256(__file__),
            "data_sha256": PINS["waf-r19.npz"],
            "anchor_onnx_sha256": R20_ONNX,
            "anchor_selection_sha256": R20_SELECTION,
            "training": {
                "objective_ablations": list(SCHEMES),
                "seed": SEED,
                "solver": "lbfgs",
                "C": 1,
                "max_iter": 400,
            },
            "threshold": "Strict >, lock on grouped R19 TUNING with request and vector FPR <=1%",
            "selection": "TUNING only: gain >=2pp request recall, no vector recall loss, AP loss <=0.005 on both, FPR <=1% on both; maximize request recall then vector recall then request AP",
            "exposed_holdout": "Report all arms after lock. One preselected candidate can only be vetoed (gain lost, AP loss >0.005, or either FPR >1%). No fallback selection from exposed data.",
        },
    )
    native_evidence(out)
    status(out, "FIT_AND_TUNING")
    fit_x, fit_y = partition(R19, "fit")
    tune_x, tune_y, tune_groups = role("tuning")
    models = {
        "r19_logistic": cpu_session(R19 / "bundle/logistic.onnx", 1),
        "r19_swiglu": cpu_session(R19 / "bundle/swiglu.onnx", 1),
        BASE: cpu_session(R20 / "bundle/swiglu.onnx", 1),
    }
    frozen = predict(models["r19_swiglu"], fit_x)
    scope = read(R20 / "bundle/model-scope.json")
    base_threshold = read(R20 / "calibration-selection.json")["cutoff"]
    check(scope["tuning_calibration"]["threshold"] == base_threshold, "R20 scope binding")
    cuts = {BASE: base_threshold}
    tuning, weights = {}, {}
    for scheme in SCHEMES:
        group, labels, weight = weight_ablation(fit_y, frozen, scheme)
        estimator = LogisticRegression(max_iter=400, random_state=SEED).fit(
            fit_x[group],
            labels,
            sample_weight=weight,
        )
        check(estimator.n_iter_.max() < 400, f"{scheme} solver did not converge")
        path = out / f"{scheme}.onnx"
        onnx.save_model(logistic_onnx(estimator), path)
        models[scheme] = cpu_session(path, 1)
        np.testing.assert_allclose(
            predict(models[scheme], tune_x),
            estimator.predict_proba(tune_x)[:, 1],
            rtol=1e-5,
            atol=1e-6,
        )
        weights[scheme] = {
            "class_mass": np.bincount(labels, weights=weight, minlength=2).tolist(),
            "vector_label_cells": len(group),
            "onnx_sha256": file_sha256(path),
        }
    for name, model in models.items():
        score = predict(model, tune_x)
        if name != BASE:
            cuts[name] = dual_cut(tune_y, score)
        tuning[name] = metrics_both(tune_y, score, cuts[name])
    candidates = [name for name in SCHEMES if advances(tuning[name], tuning[BASE], tuning=True)]
    nominated = max(
        candidates,
        default=None,
        key=lambda name: (
            tuning[name]["original_request"]["recall"],
            tuning[name]["vector_balanced"]["recall"],
            tuning[name]["original_request"]["ap"],
        ),
    )
    lock(
        out / "selection.json",
        {
            "nominated_on_tuning": nominated,
            "thresholds": cuts,
            "tuning": tuning,
            "tuning_components": len(np.unique(tune_groups)),
            "weighting": weights,
        },
    )
    status(out, "LOCKED_EXPOSED_HOLDOUT")
    x, counts, groups = role("holdout")
    check(not np.intersect1d(groups, tune_groups).size, "Tuning and holdout component overlap")
    holdout, mixed, latency = {}, {}, {}
    is_mixed = np.all(counts > 0, axis=1)
    for name, model in models.items():
        score = predict(model, x)
        holdout[name] = metrics_both(counts, score, cuts[name])
        mixed[name] = metrics_both(counts[is_mixed], score[is_mixed], cuts[name])
        latency[name] = cpu_benchmark(model, x)
    check(
        holdout[BASE]["original_request"]["confusion_tn_fp_fn_tp"] == [925, 9, 873, 1419],
        "R20 anchor changed",
    )
    candidate = (
        nominated
        if nominated and advances(holdout[nominated], holdout[BASE], tuning=False)
        else None
    )
    if candidate:
        bundle = out / "bundle"
        bundle.mkdir(mode=0o700, exist_ok=True)
        shutil.copyfile(out / f"{candidate}.onnx", bundle / "logistic.onnx")
        shutil.copyfile(R20 / "bundle/swiglu.onnx", bundle / "swiglu.onnx")
        scope["models"]["logistic"] = weights[candidate]["onnx_sha256"]
        atomic_json(bundle / "model-scope.json", scope)
        shadow(out)
    atomic_json(
        out / "evaluation.json",
        {
            "scope": "EXPOSED_WAF_DEVELOPMENT_HOLDOUT",
            "holdout_original_requests": int(counts.sum()),
            "holdout_vectors": len(counts),
            "holdout_components": len(np.unique(groups)),
            "holdout": holdout,
            "mixed_only": mixed,
            "cpu_latency": latency,
            "selected_r21_candidate": candidate,
            "selected_for_shadow": candidate or BASE,
            "anchor_checkpoint": {
                **checkpoint_pin,
                "generation": str(checkpoint.relative_to(REPO_ROOT)),
            },
            "sealed_test_read": False,
            "hybrid_allowed": False,
        },
    )
    atomic_json(
        out / "status.json",
        {
            "state": "COMPLETED",
            "run_id": out.name,
            "selected_for_shadow": candidate or BASE,
            "native_release": "BLOCKED_NO_INDEPENDENT_CAL_TEST_AND_COMMON_ROSTER",
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)

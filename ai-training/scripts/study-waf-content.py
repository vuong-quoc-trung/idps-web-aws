#!/usr/bin/env python3
"""One frozen, internal WAF NORMAL/ANOMALOUS study; never a security acceptance test."""

from __future__ import annotations

import argparse
import resource
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.features.request_preprocessing import bounded_spec
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model
from idps_ai.training.resources import resource_envelope


def _metrics(labels, scores, threshold):
    predicted = scores > threshold
    positive = labels == 1
    negative = labels == 0
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & negative))
    return {
        "publisher_anomalous_recall": tp / max(int(positive.sum()), 1),
        "publisher_normal_fpr": fp / max(int(negative.sum()), 1),
        "publisher_label_precision": tp / max(int(predicted.sum()), 1),
        "publisher_anomalous_pr_auc": float(average_precision_score(labels, scores)),
        "publisher_normal_false_positives_per_10000": 10000 * fp / max(int(negative.sum()), 1),
        "rows": len(labels),
        "publisher_normal_rows": int(negative.sum()),
        "publisher_anomalous_rows": int(positive.sum()),
    }


def _score(model, values):
    return np.concatenate(
        [model.predict(values[start : start + 4096])[0] for start in range(0, len(values), 4096)]
    )


def _fit_model(name, values, labels, train, calibration, validation, plan, output):
    model = Model(
        values.shape[1],
        64,
        "deep_mlp",
        seed=plan["seed"],
        objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
    )
    rng = np.random.default_rng(plan["seed"])
    order = rng.permutation(train)
    cursor = 0
    losses = []
    started = time.monotonic()
    for _ in range(plan["updates"]):
        if cursor + plan["batch_size"] > len(order):
            order = rng.permutation(train)
            cursor = 0
        batch = order[cursor : cursor + plan["batch_size"]]
        cursor += plan["batch_size"]
        losses.append(
            model.train_batch(
                values[batch],
                np.full(len(batch), -1, np.int64),
                plan["learning_rate"],
                binary_targets=labels[batch],
            )
        )
    fit_seconds = time.monotonic() - started
    directory = output / name
    save_checkpoint(
        directory,
        model,
        {
            "plan_sha256": plan["plan_sha256"],
            "scope": "WAF publisher anomaly internal research",
            "source_role": "train",
            "validation_or_test_rows_used_for_fitting": 0,
        },
        order.astype(np.int64),
    )
    loaded = load_checkpoint(directory)
    if loaded.model.steps != plan["updates"] or any(
        not np.array_equal(model.arrays()[key], loaded.model.arrays()[key])
        for key in model.arrays()
    ):
        raise PipelineError("WAF research checkpoint readback mismatch")
    cal_scores = _score(model, values[calibration])
    threshold = float(np.quantile(cal_scores[labels[calibration] == 0], 0.99, method="higher"))
    val_scores = _score(model, values[validation])
    probe = values[validation[: min(1024, len(validation))]]
    _score(model, probe)
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        _score(model, probe)
        timings.append(1000 * (time.perf_counter() - start) / len(probe))
    result = {
        "name": name,
        "input_features": values.shape[1],
        "parameters": sum(value.size for value in model.parameters.values()),
        "updates": model.steps,
        "first_20_train_batch_loss_mean": float(np.mean(losses[:20])),
        "last_20_train_batch_loss_mean": float(np.mean(losses[-20:])),
        "fit_seconds": fit_seconds,
        "threshold_source": "calibration publisher-normal 99th percentile, strict greater than",
        "threshold": threshold,
        "calibration": _metrics(labels[calibration], cal_scores, threshold),
        "internal_validation": _metrics(labels[validation], val_scores, threshold),
        "model_only_ms_per_row_p95_batch1024": float(np.quantile(timings, 0.95)),
        "checkpoint": str(directory),
        "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
    }
    return result, val_scores


def run(plan_path, output):
    plan_path, output = Path(plan_path), Path(output)
    if output.exists():
        raise PipelineError("WAF study output already exists")
    plan = load_json(plan_path)
    if plan.get("plan_sha256") != digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise PipelineError("WAF study plan self-hash mismatch")
    if (
        plan.get("scope") != "internal_publisher_normal_vs_anomalous"
        or plan.get("updates") != 300
        or plan.get("batch_size") != 128
        or file_sha256(__file__) != plan.get("script_sha256")
        or file_sha256(plan["dataset"]) != plan["dataset_sha256"]
        or file_sha256(plan["curation_report"]) != plan["curation_report_sha256"]
    ):
        raise PipelineError("Frozen WAF study inputs or budget changed")
    training_root = Path(__file__).resolve().parents[1]
    if plan.get("training_code_sha256") != {
        name: file_sha256(training_root / name)
        for name in (
            "src/idps_ai/training/models.py",
            "src/idps_ai/training/deep.py",
            "src/idps_ai/training/partial.py",
            "src/idps_ai/training/checkpoint.py",
        )
    }:
        raise PipelineError("WAF model/checkpoint code changed after plan freeze")
    curated = load_json(plan["curation_report"])
    if (
        curated.get("report_sha256")
        != digest({k: v for k, v in curated.items() if k != "report_sha256"})
        or curated["data_file_sha256"] != plan["dataset_sha256"]
    ):
        raise PipelineError("WAF curation report integrity failed")
    with np.load(plan["dataset"], allow_pickle=False) as data:
        numeric, content = data["numeric"], data["content"]
        labels, roles, groups, views = data["label"], data["role"], data["group"], data["view"]
    if (
        numeric.shape != (len(labels), 76)
        or content.shape != (len(labels), 512)
        or not np.isfinite(numeric).all()
        or not np.isfinite(content).all()
        or len(set(views)) != len(views)
        or not np.isin(labels, [0, 1]).all()
        or not np.isin(roles, [0, 1, 2]).all()
    ):
        raise PipelineError("Invalid WAF numeric-only research tensor")
    for a, b in ((0, 1), (0, 2), (1, 2)):
        if set(groups[roles == a]) & set(groups[roles == b]):
            raise PipelineError("WAF template leakage across roles")
    train, calibration, validation = (np.flatnonzero(roles == role) for role in (0, 1, 2))
    if any(
        min(np.bincount(labels[index], minlength=2)) < 100
        for index in (train, calibration, validation)
    ):
        raise PipelineError("WAF internal roles lack publisher-label coverage")
    output.mkdir(parents=True, mode=0o700)
    arms = {}
    val_scores = {}
    for name, values in (
        ("numeric_mlp", numeric),
        ("content_mlp", np.concatenate((numeric, content), axis=1)),
    ):
        arms[name], val_scores[name] = _fit_model(
            name, values, labels, train, calibration, validation, plan, output
        )
    method_indices = [
        i for i, name in enumerate(bounded_spec()["columns"]) if name.startswith("method_")
    ]
    method = LogisticRegression(C=1.0, max_iter=200, random_state=plan["seed"])
    method.fit(numeric[train][:, method_indices], labels[train])
    cal_method = method.predict_proba(numeric[calibration][:, method_indices])[:, 1]
    val_method = method.predict_proba(numeric[validation][:, method_indices])[:, 1]
    method_threshold = float(
        np.quantile(cal_method[labels[calibration] == 0], 0.99, method="higher")
    )
    arms["method_only_logistic"] = {
        "input_features": len(method_indices),
        "parameters": len(method.coef_.ravel()) + len(method.intercept_),
        "threshold": method_threshold,
        "calibration": _metrics(labels[calibration], cal_method, method_threshold),
        "internal_validation": _metrics(labels[validation], val_method, method_threshold),
    }
    report = {
        "format_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "scope": plan["scope"],
        "labels": "publisher normal/anomalous; anomalous not independently confirmed malicious",
        "rows": len(labels),
        "role_class_coverage": curated["role_class_coverage"],
        "arms": arms,
        "interpretation": "Internal grouped-template publisher-label comparison only; no independent application/campaign/time evaluation, no formal admission or champion",
        "validation_reused_for_tuning": False,
        "test_or_heldout_opened": False,
        "formal_admitted": 0,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    report["report_sha256"] = digest(report)
    atomic_json(output / "report.json", report)
    (output / "report.json").chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = run(args.plan, args.output)
    print({"rows": result["rows"], "arms": list(result["arms"]), "report": args.output})

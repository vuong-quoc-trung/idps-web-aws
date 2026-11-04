#!/usr/bin/env python3
"""Bounded train-only WAMM signal check against a shuffled-label control."""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.training.checkpoint import save_checkpoint
from idps_ai.training.models import Model
from idps_ai.training.resources import resource_envelope

TRAINING_FILES = (
    "src/idps_ai/training/models.py",
    "src/idps_ai/training/deep.py",
    "src/idps_ai/training/partial.py",
    "src/idps_ai/training/checkpoint.py",
)


def _loss(model, x, labels):
    score = np.clip(model.predict(x)[0].astype(np.float64), 1e-7, 1 - 1e-7)
    target = labels.astype(np.float64) * 0.995 + 0.0025
    return float(np.mean(-(target * np.log(score) + (1 - target) * np.log1p(-score))))


def run(plan_path, output):
    plan_path, output = Path(plan_path), Path(output)
    if output.exists():
        raise PipelineError("Train-only output already exists")
    plan = load_json(plan_path)
    if plan.get("plan_sha256") != digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise PipelineError("Training plan self-hash mismatch")
    if plan.get("scope") != "publisher_label_train_only_no_evaluation":
        raise PipelineError("Training plan scope changed")
    if plan.get("updates") != 200 or plan.get("batch_size") != 128:
        raise PipelineError("Unreviewed optimizer budget")
    if file_sha256(__file__) != plan["script_sha256"]:
        raise PipelineError("Training script changed after plan freeze")
    training_root = Path(__file__).resolve().parents[1]
    if plan.get("training_code_sha256") != {
        name: file_sha256(training_root / name) for name in TRAINING_FILES
    }:
        raise PipelineError("Model or checkpoint code changed after plan freeze")
    if file_sha256(plan["staging"]) != plan["staging_sha256"]:
        raise PipelineError("Training corpus changed after plan freeze")
    if file_sha256(plan["qa_report"]) != plan["qa_report_sha256"]:
        raise PipelineError("QA report changed after plan freeze")
    qa = load_json(plan["qa_report"])
    if (
        qa.get("report_sha256") != digest({k: v for k, v in qa.items() if k != "report_sha256"})
        or not qa.get("RESEARCH_FIT_READY")
        or qa.get("RESEARCH_EVAL_READY")
        or qa.get("FORMAL_READY")
    ):
        raise PipelineError("Train-only QA scope is not valid")
    table = pq.read_table(plan["staging"])
    if table.column_names != ["view_sha256", "label", "occurrence_rows", "features"]:
        raise PipelineError("Unexpected numeric training schema")
    if (
        table.num_rows
        != qa["data_accounting"]["numeric_views_after_quarantine_and_exposed_overlap"]
    ):
        raise PipelineError("Training view count differs from QA")
    x = table.column("features").combine_chunks().values.to_numpy().reshape(table.num_rows, 76)
    labels = np.asarray(table.column("label").to_pylist(), np.int64)
    keys = table.column("view_sha256").to_pylist()
    if (
        len(set(keys)) != len(keys)
        or not np.isin(labels, [0, 1]).all()
        or not np.isfinite(x).all()
        or any(
            hashlib.sha256(row.tobytes()).hexdigest() != key
            for row, key in zip(x, keys, strict=True)
        )
    ):
        raise PipelineError("Training views are corrupt or conflicting")
    rng = np.random.default_rng(plan["seed"])
    order = rng.permutation(len(x))
    shuffled = labels.copy()
    rng.shuffle(shuffled)
    probe = order[:1024]
    output.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    results = {}
    for name, targets in (("publisher", labels), ("shuffled_control", shuffled)):
        model = Model(
            76,
            plan["width"],
            "deep_mlp",
            seed=plan["seed"],
            objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
        )
        target_start = _loss(model, x[probe], targets[probe])
        true_start = _loss(model, x[probe], labels[probe])
        losses = []
        for step in range(plan["updates"]):
            batch = order[step * plan["batch_size"] : (step + 1) * plan["batch_size"]]
            loss = model.train_batch(
                x[batch],
                np.full(len(batch), -1, dtype=np.int64),
                plan["learning_rate"],
                binary_targets=targets[batch],
            )
            if not np.isfinite(loss):
                raise PipelineError("Nonfinite train-only loss")
            losses.append(loss)
        directory = output / name
        save_checkpoint(
            directory,
            model,
            {
                "plan_sha256": plan["plan_sha256"],
                "scope": plan["scope"],
                "label_tier": "PUBLISHER_LABELED" if name == "publisher" else "SHUFFLED_CONTROL",
                "source": "WAMM SR-BH derivative; not independent evaluation",
                "fit_rows": plan["updates"] * plan["batch_size"],
                "validation_rows_decoded": 0,
                "test_rows_decoded": 0,
            },
            order.astype(np.int64),
        )
        results[name] = {
            "parameters": sum(value.size for value in model.parameters.values()),
            "updates": model.steps,
            "fit_target_probe_loss_start": target_start,
            "fit_target_probe_loss_end": _loss(model, x[probe], targets[probe]),
            "publisher_probe_loss_start": true_start,
            "publisher_probe_loss_end": _loss(model, x[probe], labels[probe]),
            "first_20_batch_loss_mean": float(np.mean(losses[:20])),
            "last_20_batch_loss_mean": float(np.mean(losses[-20:])),
            "checkpoint": str(directory),
            "checkpoint_manifest_sha256": file_sha256(
                directory / load_json(directory / "latest.json")["path"] / "manifest.json"
            ),
        }
    report = {
        "format_version": 1,
        "plan_sha256": plan["plan_sha256"],
        "scope": plan["scope"],
        "source": "WAMM publisher labels; SR-BH derivative",
        "unique_numeric_views": len(x),
        "publisher_benign_views": int((labels == 0).sum()),
        "publisher_anomalous_views": int((labels == 1).sum()),
        "fit_unique_views_per_run": plan["updates"] * plan["batch_size"],
        "probe_rows_are_inside_fit": True,
        "results": results,
        "elapsed_seconds": time.monotonic() - started,
        "validation_or_test_rows_decoded": 0,
        "recall": None,
        "fpr": None,
        "pr_auc": None,
        "formal_admission": 0,
        "conclusion_scope": "Optimization and label-signal diagnostic only; no detection or generalization claim",
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
    print({"updates": result["results"]["publisher"]["updates"], "report": args.output})

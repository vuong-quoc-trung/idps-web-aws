#!/usr/bin/env python3
"""Frozen-score, grouped uncertainty and shortcut diagnostics for a WAF study."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.features.request_preprocessing import bounded_spec
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope


def _score(model, values):
    return np.concatenate(
        [model.predict(values[start : start + 4096])[0] for start in range(0, len(values), 4096)]
    )


def _rates(y, scores, threshold):
    positive, negative = y == 1, y == 0
    predicted = scores > threshold
    return {
        "publisher_anomalous_recall": float(np.mean(predicted[positive]))
        if positive.any()
        else None,
        "publisher_normal_fpr": float(np.mean(predicted[negative])) if negative.any() else None,
        "publisher_anomalous_pr_auc": float(average_precision_score(y, scores))
        if positive.any() and negative.any()
        else None,
        "normal": int(negative.sum()),
        "anomalous": int(positive.sum()),
    }


def analyze(dataset, curation_report, study_report, study_root, output):
    dataset, output = Path(dataset), Path(output)
    if output.exists():
        raise PipelineError("WAF analysis output already exists")
    curated, study = load_json(curation_report), load_json(study_report)
    for report in (curated, study):
        if report.get("report_sha256") != digest(
            {k: v for k, v in report.items() if k != "report_sha256"}
        ):
            raise PipelineError("WAF frozen report self-hash mismatch")
    if file_sha256(dataset) != curated["data_file_sha256"]:
        raise PipelineError("WAF frozen dataset changed")
    with np.load(dataset, allow_pickle=False) as data:
        numeric, content, labels, roles, groups = (
            data[name] for name in ("numeric", "content", "label", "role", "group")
        )
    val = roles == 2
    y, group = labels[val], groups[val]
    values = {
        "numeric_mlp": numeric[val],
        "content_mlp": np.concatenate((numeric[val], content[val]), axis=1),
    }
    scores, thresholds = {}, {}
    for name in values:
        expected = study["arms"][name]
        loaded = load_checkpoint(Path(study_root) / name)
        if (
            loaded.model.steps != 300
            or file_sha256(loaded.path / "manifest.json") != expected["checkpoint_manifest_sha256"]
        ):
            raise PipelineError("Frozen WAF checkpoint changed")
        scores[name] = _score(loaded.model, values[name])
        thresholds[name] = expected["threshold"]
        actual = _rates(y, scores[name], thresholds[name])
        for key in (
            "publisher_anomalous_recall",
            "publisher_normal_fpr",
            "publisher_anomalous_pr_auc",
        ):
            if abs(actual[key] - expected["internal_validation"][key]) > 1e-9:
                raise PipelineError("Frozen WAF score/report mismatch")
    columns = bounded_spec()["columns"]
    method_slices = {}
    for name in ("GET", "POST", "OTHER"):
        index = columns.index("method_" + name)
        mask = numeric[val, index] == 1
        method_slices[name] = {
            model: _rates(y[mask], score[mask], thresholds[model])
            for model, score in scores.items()
        }
    unique, inverse = np.unique(group, return_inverse=True)
    members = [np.flatnonzero(inverse == i) for i in range(len(unique))]
    rng = np.random.default_rng(91)
    differences = {
        name: []
        for name in (
            "publisher_anomalous_recall",
            "publisher_normal_fpr",
            "publisher_anomalous_pr_auc",
        )
    }
    for _ in range(300):
        selected = rng.integers(0, len(members), len(members))
        rows = np.concatenate([members[i] for i in selected])
        if len(set(y[rows])) != 2:
            continue
        content_rate = _rates(y[rows], scores["content_mlp"][rows], thresholds["content_mlp"])
        numeric_rate = _rates(y[rows], scores["numeric_mlp"][rows], thresholds["numeric_mlp"])
        for name in differences:
            differences[name].append(content_rate[name] - numeric_rate[name])
    intervals = {
        name: {
            "point_difference": _rates(y, scores["content_mlp"], thresholds["content_mlp"])[name]
            - _rates(y, scores["numeric_mlp"], thresholds["numeric_mlp"])[name],
            "group_bootstrap_95pct": [
                float(np.quantile(values, 0.025)),
                float(np.quantile(values, 0.975)),
            ],
        }
        for name, values in differences.items()
    }
    report = {
        "format_version": 1,
        "dataset_sha256": file_sha256(dataset),
        "curation_report_sha256": file_sha256(curation_report),
        "study_report_sha256": file_sha256(study_report),
        "validation_rows": len(y),
        "validation_symbolic_template_groups": len(unique),
        "method_slices": method_slices,
        "paired_content_minus_numeric": intervals,
        "bootstrap_scope": "300 group resamples, frozen checkpoints and calibration thresholds; quantifies internal sampling only, not label/source uncertainty",
        "model_selection": None,
        "independent_attack_quality": None,
    }
    report["report_sha256"] = digest(report)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "curation-report", "study-report", "study-root", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    with resource_envelope(4, 16):
        result = analyze(
            args.dataset, args.curation_report, args.study_report, args.study_root, args.output
        )
    print({"validation_rows": result["validation_rows"], "report": args.output})

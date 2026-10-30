"""Fixed, label-blind campaign split within validation; final test remains sealed."""

from collections import defaultdict
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError
from idps_ai.data.dataset import iter_rows
from idps_ai.training.evaluation import evaluate, threshold_at_fpr


def validation_groups(dataset):
    rows = [
        r
        for r in iter_rows(Path(dataset) / "requests.parquet")
        if r["split"] == "val" and r["label"] is not None
    ]
    first = {}
    for r in rows:
        group = r.get("group_key") or r.get("campaign_key")
        if not group:
            raise PipelineError("Independent validation requires campaign/group identity")
        first[group] = min(first.get(group, float("inf")), r["timestamp"])
    ordered = sorted(first, key=lambda g: (first[g], g))
    if len(ordered) < 2:
        raise PipelineError("Need at least two validation groups for calibration/selection")
    n = max(1, len(ordered) // 3)
    calibration = set(ordered[:n])
    groups = [r.get("group_key") or r["campaign_key"] for r in rows]
    indices = np.arange(len(rows))
    mask = np.array([g in calibration for g in groups])
    return {
        "calibration_groups": ordered[:n],
        "selection_groups": ordered[n:],
        "groups": groups,
        "calibration_indices": indices[mask],
        "selection_indices": indices[~mask],
        "split_rule": "first third of groups by earliest timestamp, chosen without labels or scores",
        "environment_holdout": False,
        "limitation": "Same lab environment; independent campaigns do not prove deployment generalization",
    }


def bootstrap_groups(labels, scores, threshold, groups, repeats=200, seed=43):
    # Resample whole campaigns with a fixed threshold, never individual correlated requests.
    by_group = defaultdict(list)
    for i, g in enumerate(groups):
        by_group[g].append(i)
    names = sorted(by_group)
    rng = np.random.default_rng(seed)
    values = defaultdict(list)
    for _ in range(repeats):
        chosen = rng.choice(names, len(names), replace=True)
        indices = np.concatenate([by_group[g] for g in chosen])
        y = np.asarray(labels)[indices] != 0
        predicted = np.asarray(scores)[indices] >= threshold
        tp = int(np.sum(y & predicted))
        fp = int(np.sum(~y & predicted))
        fn = int(np.sum(y & ~predicted))
        tn = int(np.sum(~y & ~predicted))
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        for k, v in {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-12),
            "fpr": fp / max(tn + fp, 1),
        }.items():
            values[k].append(v)
    return {
        "method": "campaign bootstrap, fixed threshold, percentile95",
        "repeats": repeats,
        "seed": seed,
        "group_count": len(names),
        "intervals": {k: np.percentile(v, [2.5, 97.5]).tolist() for k, v in values.items()},
        "warning": "Few independent campaigns and one topology cannot certify a production false-positive budget",
    }


def evaluate_independent(labels, scores, probabilities, protocol, bootstrap_repeats=200):
    labels = np.asarray(labels)
    scores = np.asarray(scores)
    if len(labels) != len(protocol["groups"]) or len(scores) != len(labels):
        raise PipelineError("Validation row alignment mismatch")
    ci, si = protocol["calibration_indices"], protocol["selection_indices"]
    calibration = threshold_at_fpr((labels[ci] != 0).astype(np.int64), scores[ci])
    calibration["fit_partition"] = "val_calibration_groups"
    selected = evaluate(
        labels[si],
        scores[si],
        calibration["threshold"],
        probabilities[si] if probabilities is not None else None,
    )
    selected["partition"] = "val_selection_groups"
    tn, fp = selected["confusion_matrix"][0]
    selected["fpr"] = fp / max(tn + fp, 1)
    for name, f in selected["families"].items():
        if "confusion_matrix_vs_benign" not in f:
            continue
        (tn, fp), (fn, tp) = f["confusion_matrix_vs_benign"]
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f.update(
            precision_vs_benign=precision,
            recall=recall,
            f1_vs_benign=2 * precision * recall / max(precision + recall, 1e-12),
        )
    return {
        "format_version": 1,
        "calibration": calibration,
        "selection": selected,
        "test_labels_used": False,
        "calibration_groups": protocol["calibration_groups"],
        "selection_groups": protocol["selection_groups"],
        "bootstrap": bootstrap_groups(
            labels[si],
            scores[si],
            calibration["threshold"],
            [protocol["groups"][i] for i in si],
            repeats=bootstrap_repeats,
        ),
        "scope": "fixed final checkpoint, independently grouped calibration/selection inside validation; not an environment holdout",
    }

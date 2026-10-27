"""Validation-only threshold fitting and honest binary/family evaluation."""

import time

import numpy as np
from sklearn.metrics import (
    auc,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from idps_ai.common import CLASSES, PipelineError


def threshold_at_fpr(labels, scores, max_fpr=0.01):
    labels, scores = np.asarray(labels), np.asarray(scores)
    if not np.isfinite(scores).all() or not np.isin(labels, [0, 1]).all():
        raise PipelineError("Invalid calibration labels/scores")
    if len(np.unique(labels)) != 2:
        raise PipelineError(
            "Threshold calibration needs reviewed benign and attack validation examples"
        )
    fpr, tpr, thresholds = roc_curve(labels, scores, drop_intermediate=False)
    eligible = np.flatnonzero(fpr <= max_fpr)
    best = eligible[np.argmax(tpr[eligible])]
    threshold = float(thresholds[best])
    if not np.isfinite(threshold):
        threshold = float(np.nextafter(np.float32(np.max(scores)), np.float32(np.inf)))
    else:
        below = scores[scores < threshold]
        if len(below):
            lower = float(np.max(below))
            midpoint = float(np.float32((threshold + lower) / 2))
            if midpoint > lower:
                threshold = midpoint
    return {
        "threshold": threshold,
        "validation_fpr": float(np.mean(scores[labels == 0] >= threshold)),
        "validation_recall": float(np.mean(scores[labels == 1] >= threshold)),
        "target_fpr": max_fpr,
        "fit_partition": "val",
        "benign_count": int((labels == 0).sum()),
        "finite_sample_warning": "Empirical FPR only; small synthetic samples do not certify production FPR",
    }


def evaluate(labels, scores, threshold, probabilities=None):
    family = np.asarray(labels, dtype=np.int64)
    binary = (family != 0).astype(np.int64)
    scores = np.asarray(scores)
    predicted = (scores >= threshold).astype(np.int64)
    both = len(np.unique(binary)) == 2
    curve = threshold_at_fpr(binary, scores) if both else None
    precision_curve, recall_curve, _ = (
        precision_recall_curve(binary, scores) if both else ([], [], [])
    )
    report = {
        "rows": len(family),
        "threshold": threshold,
        "pr_auc_average_precision": float(average_precision_score(binary, scores))
        if both
        else None,
        "pr_auc_trapezoidal": float(auc(recall_curve, precision_curve)) if both else None,
        "roc_auc": float(roc_auc_score(binary, scores)) if both else None,
        "precision": float(precision_score(binary, predicted, zero_division=0)),
        "recall": float(recall_score(binary, predicted, zero_division=0)),
        "f1": float(f1_score(binary, predicted, zero_division=0)),
        "confusion_matrix": confusion_matrix(binary, predicted, labels=[0, 1]).tolist(),
        "recall_at_fpr_le_1pct": curve["validation_recall"] if curve else None,
        "recall_at_fpr_note": "ROC diagnostic only; deployed threshold remains validation-fitted and is not retuned on test",
        "families": {},
    }
    for index, name in enumerate(CLASSES):
        selected = (family == index) | (family == 0)
        actual_family = family == index
        if index == 0:
            report["families"][name] = {
                "count": int(actual_family.sum()),
                "false_positives": int(((family == 0) & (predicted == 1)).sum()),
            }
        else:
            report["families"][name] = {
                "count": int(actual_family.sum()),
                "detected": int((actual_family & (predicted == 1)).sum()),
                "confusion_matrix_vs_benign": confusion_matrix(
                    binary[selected], predicted[selected], labels=[0, 1]
                ).tolist(),
            }
    if probabilities is not None:
        predicted_family = np.argmax(probabilities[:, 1:], axis=1) + 1
        predicted_family[predicted == 0] = 0
        report["multiclass_confusion_matrix"] = confusion_matrix(
            family, predicted_family, labels=list(range(len(CLASSES)))
        ).tolist()
        report["multiclass_labels"] = list(CLASSES)
    return report


def latency_ms(call, sample, repeats=100):
    for _ in range(5):
        call(sample)
    times = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        call(sample)
        times.append((time.perf_counter_ns() - start) / 1e6)
    return dict(zip(("p50", "p95", "p99"), [float(x) for x in np.percentile(times, [50, 95, 99])]))

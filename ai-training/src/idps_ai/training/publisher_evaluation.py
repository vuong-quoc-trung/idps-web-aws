"""Publisher-binary metrics; no attack-family inference or evaluation-set fitting."""

import math

import numpy as np
from sklearn.metrics import average_precision_score

from idps_ai.common import PipelineError


def wilson(k, n):
    if n == 0:
        return None
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, mid - half), min(1.0, mid + half)]


def validate(y, s):
    y = np.asarray(y)
    s = np.asarray(s, np.float64)
    if (
        y.shape != s.shape
        or y.ndim != 1
        or not len(y)
        or not np.isin(y, [0, 1]).all()
        or not np.isfinite(s).all()
    ):
        raise PipelineError("Invalid publisher binary evaluation inputs")
    return y, s


def fit_balanced_threshold(y, s):
    """CAL-only strict> operating points; exact rational tie, highest threshold."""
    y, s = validate(y, s)
    n0 = int(np.sum(y == 0))
    n1 = int(np.sum(y == 1))
    if not n0 or not n1:
        raise PipelineError("Calibration requires both publisher classes")
    candidates = np.r_[np.nextafter(s.min(), -np.inf), np.unique(s)]
    best = None
    for threshold in candidates:
        flag = s > threshold
        tp = int(np.sum(flag & (y == 1)))
        tn = int(np.sum(~flag & (y == 0)))
        key = (tp * n0 + tn * n1, float(threshold))
        if best is None or key > best[0]:
            best = (key, float(threshold))
    return {
        "threshold": best[1],
        "comparator": ">",
        "fit_partition": "CALIBRATION",
        "objective": "balanced_accuracy",
        "tie_break": "highest_threshold",
        "calibration_normal": n0,
        "calibration_anomalous": n1,
        "candidate_count": int(len(candidates)),
    }


def metrics(y, s, threshold):
    y, s = validate(y, s)
    flag = s > threshold
    tp, fp, tn, fn = [
        int(np.sum(mask))
        for mask in [flag & (y == 1), flag & (y == 0), ~flag & (y == 0), ~flag & (y == 1)]
    ]

    def ratio(a, b):
        return a / b if b else None

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    fpr = ratio(fp, fp + tn)
    return {
        "rows": len(y),
        "normal": tn + fp,
        "anomalous": tp + fn,
        "threshold": float(threshold),
        "comparator": ">",
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "confusion_matrix_normal_anomaly": [[tn, fp], [fn, tp]],
        "precision": precision,
        "recall": recall,
        "F1": ratio(2 * tp, 2 * tp + fp + fn),
        "average_precision": float(average_precision_score(y, s))
        if len(np.unique(y)) == 2
        else None,
        "FPR": fpr,
        "accuracy": (tp + tn) / len(y),
        "balanced_accuracy": (recall + 1 - fpr) / 2
        if recall is not None and fpr is not None
        else None,
        "nominal_iid_Wilson95": {
            "precision": wilson(tp, tp + fp),
            "recall": wilson(tp, tp + fn),
            "FPR": wilson(fp, fp + tn),
        },
        "uncertainty_scope": "nominal iid intervals; within-group dependence/source-selection/label noise not certified",
    }


def group_metrics(y, s, threshold, groups):
    y, s = validate(y, s)
    g = np.asarray(groups)
    _, inverse, counts = np.unique(g, return_inverse=True, return_counts=True)
    weights = 1 / counts[inverse]
    flag = s > threshold

    def ratio(a, b):
        den = float(np.sum(weights[b]))
        return float(np.sum(weights[a])) / den if den else None

    precision = ratio(flag & (y == 1), flag)
    recall = ratio(flag & (y == 1), y == 1)
    fpr = ratio(flag & (y == 0), y == 0)
    return {
        "groups": len(counts),
        "weighting": "inverse size per recorded exact+near component",
        "precision": precision,
        "recall": recall,
        "FPR": fpr,
        "F1": 2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else 0.0,
        "average_precision": float(average_precision_score(y, s, sample_weight=weights))
        if len(np.unique(y)) == 2
        else None,
    }

"""Same-budget ranking and grouped threshold transfer for R24 development."""

import numpy as np
from r19_metrics import metrics_both
from r20_calibration import threshold
from r23_pilot import grouped_scores
from sklearn.model_selection import GroupKFold

TARGETS = (0.005, 0.01)


def fp_cut(labels, scores, budget):
    benign = np.sort(scores[labels == 0])[::-1]
    if not 0 <= budget < len(benign) or not np.isfinite(scores).all():
        raise ValueError("Invalid benign support, score or FP budget")
    return float(benign[budget])  # A strict > never breaks a tied benign group.


def confusion(y, flags):
    tn = int(np.count_nonzero((y == 0) & ~flags))
    fp = int(np.count_nonzero((y == 0) & flags))
    fn = int(np.count_nonzero((y == 1) & ~flags))
    tp = int(np.count_nonzero((y == 1) & flags))
    return {
        "tn_fp_fn_tp": [tn, fp, fn, tp],
        "recall": tp / (tp + fn) if tp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
    }


def evaluate(x, y, scores, groups, context):
    total_benign = int(np.count_nonzero(y == 0))
    truth, vector_scores = grouped_scores(x, y, scores)
    matched = {}
    for target in TARGETS:
        budget = int(np.floor(total_benign * target))
        cut = fp_cut(y, scores, budget)
        matched[str(target)] = {
            "allowed_fp": budget,
            "metrics": metrics_both(truth, vector_scores, cut),
        }
    # All arms use the same component folds. Scores come from FIT; operating
    # thresholds are estimated on the other four folds only.
    folds = list(GroupKFold(5).split(x, y, groups))
    transferred = {}
    for target in TARGETS:
        flags = np.zeros(len(y), dtype=bool)
        records = []
        for learn, valid in folds:
            counts, values = grouped_scores(x[learn], y[learn], scores[learn])
            if min(counts.sum(axis=0)) <= 0 or min(np.bincount(y[valid], minlength=2)) <= 0:
                raise ValueError("Component fold lacks either class")
            cut = max(
                threshold(counts, values, target=target),
                threshold(counts, values, vector_balance=True, target=target),
            )
            flags[valid] = scores[valid] > cut
            records.append(
                {
                    "cut": cut,
                    "groups": len(np.unique(groups[valid])),
                    **confusion(y[valid], flags[valid]),
                }
            )
        transferred[str(target)] = {
            "aggregate": confusion(y, flags),
            "folds": records,
            "subgroups": {
                name: confusion(y[include], flags[include])
                for name, include in (
                    ("GET", context[:, 0] == 0),
                    ("POST", context[:, 0] == 1),
                    ("other_method", context[:, 0] == 2),
                    ("origin_form", context[:, 1] == 0),
                    ("absolute_form", context[:, 1] == 1),
                )
            },
        }
    return {
        "matched_fp_tuning_envelope": matched,
        "grouped_threshold_transfer_exposed_tuning": transferred,
    }

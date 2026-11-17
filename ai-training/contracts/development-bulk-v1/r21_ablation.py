"""Measure existing request-time feature groups with a fixed FIT/DEV protocol."""

import argparse
import os
from pathlib import Path

import numpy as np
from r18_data import check, read
from r19_metrics import metrics_both
from r19_train import SEED, partition, training_cells
from r20_quality import PINS, R19, role
from r21_quality import dual_cut, lock
from sklearn.linear_model import LogisticRegression

from idps_ai.common import atomic_json, file_sha256

DROP = {
    "path_structure": ("path_dot_segment_count", "path_parent_segment_count", "slash_count"),
    "query_structure": (
        "query_entropy",
        "query_length",
        "parameter_count",
        "duplicate_parameter_count",
        "empty_parameter_count",
        "max_parameter_length",
        "mean_parameter_length",
        "numeric_parameter_ratio",
        "parameter_length_std",
    ),
    "encoding": (
        "decoded_query_length",
        "decoded_uri_length",
        "encoding_contraction_ratio",
        "encoding_rounds",
        "invalid_escape_count",
        "percent_escape_count",
    ),
    "availability": ("query_lexical_available", "structure_available", "uri_lexical_available"),
}


def group_counts(x, counts):
    # Each exact reduced vector must receive one prediction. All original
    # label counts remain in its denominator even if the vector is mixed.
    distinct, inverse = np.unique(x, axis=0, return_inverse=True)
    total = np.zeros((len(distinct), 2), dtype=counts.dtype)
    np.add.at(total, inverse, counts)
    return distinct, total, inverse


def overlap(fit, tuning):
    def row_keys(x):
        value = np.ascontiguousarray(np.where(x == 0, 0, x))
        return value.view(np.dtype((np.void, x.shape[1] * x.itemsize))).ravel()

    return np.isin(row_keys(fit), row_keys(tuning))


def run(out):
    for name in ("dataset-manifest.json", "waf-r19.npz"):
        check(file_sha256(R19 / name) == PINS[name], "R19 partition digest mismatch")
    names = read(R19 / "dataset-manifest.json")["schema"]["columns"]
    drops = {
        "full_uri76": [],
        "method": [name for name in names if name.startswith("method_")],
        **DROP,
    }
    lock(
        out / "feature-plan.json",
        {
            "scope": "WAF_PUBLISHER_DEV_ONLY",
            "runner_sha256": file_sha256(__file__),
            "dataset_sha256": PINS["waf-r19.npz"],
            "drop_columns": drops,
            "fixed_objective": "Frozen R19 logistic lbfgs objective, C=1, max_iter=400 and count weights",
            "common_fit_embargo": "Remove FIT groups sharing an exact or floor(16*x) reduced vector with TUNING in any arm. Keep the same FIT and TUNING for all arms.",
            "estimands": "original requests and exact reduced vectors, group labels retain fractional mass",
            "threshold_rule": "Descriptive TUNING operating envelope with both FPR <=1%, no HOLDOUT inference",
        },
    )
    fit_x, fit_counts = partition(R19, "fit")
    tune_x, counts, _ = role("tuning")
    columns = {}
    excluded = np.zeros(len(fit_x), dtype=bool)
    for name, removed in drops.items():
        check(set(removed) <= set(names), f"Unknown feature in ablation {name}")
        keep = [j for j, key in enumerate(names) if key not in removed]
        columns[name] = keep
        left, right = fit_x[:, keep], tune_x[:, keep]
        excluded |= overlap(left, right) | overlap(np.floor(16 * left), np.floor(16 * right))
    excluded_originals = int(fit_counts[excluded].sum())
    fit_x, fit_counts = fit_x[~excluded], fit_counts[~excluded]
    groups, labels, mass, balance, _ = training_cells(fit_counts)
    result = {}
    for name, keep in columns.items():
        model = LogisticRegression(max_iter=400, random_state=SEED).fit(
            fit_x[groups][:, keep],
            labels,
            sample_weight=mass * balance[labels],
        )
        check(model.n_iter_.max() < 400, f"{name} solver did not converge")
        x, pooled, inverse = group_counts(tune_x[:, keep], counts)
        score = model.predict_proba(x)[:, 1].astype(np.float32)
        cut = dual_cut(pooled, score)
        result[name] = {
            "tuning_original_requests": int(pooled.sum()),
            "tuning_distinct_representations": len(x),
            "tuning_mixed_representations": int(np.all(pooled > 0, axis=1).sum()),
            "original_and_current_representation": metrics_both(pooled, score, cut),
            "paired_uri76_reference": metrics_both(counts, score[inverse], cut)["vector_balanced"],
        }
    atomic_json(
        out / "feature-ablation.json",
        {
            "scope": "DESCRIPTIVE_TUNING_ONLY",
            "fit_controls": result,
            "common_fit_embargo": {
                "removed_vectors": int(excluded.sum()),
                "removed_original_requests": excluded_originals,
                "kept_vectors": len(fit_x),
                "kept_original_requests": int(fit_counts.sum()),
            },
            "unobserved": [
                "causal_history",
                "sessions",
                "native_source_context",
                "request_time_header_stats",
            ],
            "holdout_read": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)

# isort: skip_file

"""Frozen-point generalization and CAL cohort diagnosis; never selects a model."""

import os

import numpy as np
from sklearn.metrics import average_precision_score

from common import PARENT, atomic_json, output_arg, read
from calibration import role
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import schema
from r20_calibration import threshold
from r23_pilot import grouped_scores
from r25_external import load as external


def basic(y, scores, cut):
    p = scores > cut
    n, a = int((y == 0).sum()), int((y == 1).sum())
    fp, tp = int(((y == 0) & p).sum()), int(((y == 1) & p).sum())
    bins = np.minimum((scores * 10).astype(int), 9)
    ece = sum(abs(float((y[bins == k] - scores[bins == k]).sum())) for k in range(10)) / max(
        1, len(y)
    )
    return {
        "normal_anomalous": [n, a],
        "confusion_tn_fp_fn_tp": [n - fp, fp, a - tp, tp],
        "recall": tp / a if a else None,
        "fpr": fp / n if n else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "AP": float(average_precision_score(y, scores)) if n and a else None,
        "Brier": float(np.mean((y - scores) ** 2)) if len(y) else None,
        "ECE": ece if len(y) else None,
    }


def detail(frame, scores, cut, width):
    x, y = frame["x"][:, :width], frame["y"]
    columns = schema()["columns"]
    methods = {
        "GET": x[:, columns.index("method_GET")] == 1,
        "POST": x[:, columns.index("method_POST")] == 1,
    }
    methods["OTHER"] = ~(methods["GET"] | methods["POST"])
    unique, inverse = np.unique(x, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    counts = np.zeros((len(unique), 2), np.int64)
    np.add.at(counts, (inverse, y), 1)
    fn = (y == 1) & (scores <= cut)
    missed = []
    for group in np.unique(frame["group"]):
        mask = frame["group"] == group
        total = int((fn & mask).sum())
        if total:
            missed.append(
                {
                    "group": int(group),
                    "false_negatives": total,
                    "normal_anomalous": np.bincount(y[mask], minlength=2).tolist(),
                    "positive_score_quantiles": np.quantile(
                        scores[mask & (y == 1)], [0, 0.25, 0.5, 0.75, 1]
                    ).tolist(),
                }
            )
    truth, values = grouped_scores(x, y, scores)
    local_cut = max(
        threshold(truth, values, target=0.005), threshold(truth, values, True, target=0.005)
    )
    return {
        "by_method": {name: basic(y[mask], scores[mask], cut) for name, mask in methods.items()},
        "normal_anomalous": np.bincount(y, minlength=2).tolist(),
        "groups": len(np.unique(frame["group"])),
        "mixed_vectors": int(np.all(counts > 0, axis=1).sum()),
        "minority_mass": int(counts.min(axis=1).sum()),
        "FN_in_mixed_vectors": int((fn & (counts[inverse, 0] > 0)).sum()),
        "total_FN": int(fn.sum()),
        "largest_FN_groups": sorted(missed, key=lambda r: r["false_negatives"], reverse=True)[:8],
        "score_quantiles_by_class": {
            str(cls): np.quantile(scores[y == cls], [0, 0.25, 0.5, 0.75, 0.9, 0.99, 1]).tolist()
            for cls in (0, 1)
        },
        "per_source_CAL_only_cut_diagnostic_not_deployed": local_cut,
        "at_per_source_cut_diagnostic": basic(y, scores, local_cut),
    }


def run(out):
    lock = read(out / "evaluation-lock.json")
    selected = read(out / "model-selection.json")["selected"]
    models = {
        name: (cpu_session(out / "bundle" / spec["calibrated_file"], 1), spec)
        for name, spec in lock["models"].items()
    }
    details = {}
    for name in ("R26A", selected):
        session, spec = models[name]
        details[name] = {}
        for source, folder in (("NOTES", "notes"), ("SRBH", "source2-recovery")):
            frame = role(folder, "CAL_OP")
            scores = session.run(["score"], {"input": frame["x"][:, : spec["width"]]})[0]
            details[name][source] = detail(frame, scores, spec["cutoff"], spec["width"])
    transfer = {}
    for filename in ("csic_2010_normalTrafficTraining.txt", "xml_train.txt"):
        x, methods, meta = external(filename)
        frame = {
            "x": x,
            "y": np.zeros(len(x), np.int8),
            "group": np.arange(len(x)),
            "coordinate": np.arange(len(x)),
        }
        report = {}
        for name in ("R20", "R25", "R26A", selected):
            session, spec = models[name]
            scores = session.run(["score"], {"input": x[:, : spec["width"]]})[0]
            positive = scores > spec["cutoff"]
            unique, first = np.unique(x[:, : spec["width"]], axis=0, return_index=True)
            report[name] = {
                "FPR": float(positive.mean()),
                "FP": int(positive.sum()),
                "records": len(x),
                "vector_balanced_FPR": float(positive[first].mean()),
                "unique_vectors": len(unique),
                "by_method": {
                    method: {
                        "records": int((methods == i).sum()),
                        "FPR": float(positive[methods == i].mean())
                        if (methods == i).any()
                        else None,
                    }
                    for i, method in enumerate(("GET", "POST", "OTHER"))
                },
            }
        transfer[filename] = {"source": meta, "models": report}
    # Compare actual effective diversity, not the inflated original denominator.
    from r26_recovery_pilot import data
    from r26_verify import effective_diversity

    train, _ = data(PARENT, False)
    diversity = [effective_diversity(x, y, 100)[0] for x, y, _ in train]
    union = len(np.unique(np.concatenate([x[:, :100] for x, _, _ in train]), axis=0))
    ess = 9 / sum(1 / part["kish_original"] for part in diversity)
    old_evaluation = read(PARENT / "evaluation.json")
    atomic_json(
        out / "diagnosis.json",
        {
            "CAL_cohort_analysis": details,
            "external_benign_stress": transfer,
            "old_NOTES_TEST_aggregate_reused_without_payload_access": {
                "original": old_evaluation["RESEARCH_TEST"]["R26_SWIGLU"]["original_request"],
                "scope": "Post-selection frozen R26A report only; never B selection or rescore",
            },
            "diversity": {
                "originals": 433261,
                "union_unique_URI100": union,
                "source_reports": diversity,
                "equal_source_Kish_original": ess,
            },
            "thresholds_changed_from_stress": False,
            "new_training_after_this_diagnosis": False,
            "interpretation": "CAL_OP and old research TEST differ in template/label mixture and method support. A high AP or a small zero-FP slice is insufficient. Cross-source transfer and mixed-label ambiguity remain; do not use stress labels to tune.",
            "new_feature_experiment": "NOT_JUSTIFIED: known URI164/HTTP244 ablations already rejected; no newly reviewed two-class causal context cohort",
            "raw_target_or_sensitive_payloads_persisted": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

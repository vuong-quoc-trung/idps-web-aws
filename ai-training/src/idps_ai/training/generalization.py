"""Development shortcut probes and frozen, request-only external stress tests.

These diagnostics neither select a champion nor open the original final test.
Missing-view external results are distribution-shift evidence, not a comparable
three-source production benchmark. Public binary labels never become families.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score
from sklearn.tree import DecisionTreeClassifier

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.http_benchmark import iter_benchmark
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import transform
from idps_ai.training.evaluation import threshold_at_fpr
from idps_ai.training.protocol import validation_groups


def grouped_binary_metrics(labels, scores, groups, threshold, replicates=200, seed=17):
    """Fixed-operating-point diagnostics; never estimate independence from row count.

    Cluster intervals resample observed groups with replacement. Fewer than eight
    groups cannot support the interval here. Even many group IDs do not establish
    independence or label truth; callers must report their actual provenance.
    """
    y, p, g = np.asarray(labels), np.asarray(scores, np.float64), np.asarray(groups)
    if (
        y.ndim != 1
        or y.shape != p.shape
        or y.shape != g.shape
        or not len(y)
        or not np.isin(y, [0, 1]).all()
        or not np.isfinite(p).all()
        or not 50 <= replicates <= 1000
        or not np.isfinite(threshold)
    ):
        raise PipelineError("Invalid grouped evaluation sample")
    unique, inverse = np.unique(g, return_inverse=True)
    predictions = p >= threshold
    # Aggregate confusion counts per cluster; bootstrap costs O(groups), not rows.
    counts = np.column_stack(
        [
            np.bincount(inverse, weights=(y == a) & (predictions == b), minlength=len(unique))
            for a, b in [(0, 0), (0, 1), (1, 0), (1, 1)]
        ]
    )
    intervals = None
    if len(unique) >= 8:
        rng = np.random.default_rng(seed)
        values = []
        for _ in range(replicates):
            tn, fp, fn, tp = counts[rng.integers(0, len(unique), len(unique))].sum(axis=0)
            values.append(
                [
                    fp / (tn + fp) if tn + fp else np.nan,
                    tp / (tp + fn) if tp + fn else np.nan,
                    tp / (tp + fp) if tp + fp else np.nan,
                ]
            )
        intervals = {}
        for i, name in enumerate(["fpr", "recall", "precision"]):
            valid = np.array(values)[:, i]
            valid = valid[np.isfinite(valid)]
            intervals[name] = (
                np.quantile(valid, [0.025, 0.975]).tolist()
                if len(valid) >= replicates * 0.9
                else None
            )
    n = int(np.sum(y == 0))
    wilson = None
    if n:
        phat = float(np.mean(predictions[y == 0]))
        z = 1.959963984540054
        center = (phat + z * z / (2 * n)) / (1 + z * z / n)
        radius = z * np.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        wilson = [max(0.0, float(center - radius)), min(1.0, float(center + radius))]
    return {
        "metrics": binary_metrics(y, p, threshold),
        "threshold": float(threshold),
        "threshold_fitted": False,
        "observed_groups": len(unique),
        "cluster_bootstrap_95pct": intervals,
        "bootstrap_replicates": replicates,
        "iid_wilson_FPR_95pct": wilson,
        "independent_label_review": False,
        "limits": "Intervals conditional on publisher/runner labels and group definition. Wilson assumes IID; group bootstrap assumes independent clusters. Neither proves these assumptions, coverage on new domains, or safety of zero observed FPs. Fewer than8groups: cluster interval intentionally unavailable.",
    }


def calibration_audit(labels, scores, bins=10):
    """Diagnostic probability reliability, not threshold fitting or acceptance."""
    y, p = np.asarray(labels, np.float64), np.asarray(scores, np.float64)
    if (
        y.shape != p.shape
        or y.ndim != 1
        or not len(y)
        or not np.isin(y, [0, 1]).all()
        or not np.isfinite(p).all()
        or (p < 0).any()
        or (p > 1).any()
        or not 2 <= bins <= 50
    ):
        raise PipelineError("Invalid probability calibration observations")
    clipped = np.clip(p, 1e-12, 1 - 1e-12)
    rows, error = [], 0.0
    groups = np.minimum((p * bins).astype(np.int64), bins - 1)
    for i in range(bins):
        mask = groups == i
        if not mask.any():
            continue
        confidence, frequency = float(p[mask].mean()), float(y[mask].mean())
        error += int(mask.sum()) / len(y) * abs(confidence - frequency)
        rows.append(
            {
                "bin": i,
                "n": int(mask.sum()),
                "mean_probability": confidence,
                "attack_frequency": frequency,
            }
        )
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "negative_log_likelihood": float(
            -np.mean(y * np.log(clipped) + (1 - y) * np.log1p(-clipped))
        ),
        "ece_equal_width": error,
        "bins": rows,
        "threshold_selected": False,
        "limitation": "Dataset prevalence and correlated requests affect this diagnostic; not an OOD calibration guarantee",
    }


def binary_metrics(labels, scores, threshold):
    labels, scores = np.asarray(labels), np.asarray(scores)
    if (
        not np.isin(labels, [0, 1]).all()
        or not np.isfinite(scores).all()
        or len(labels) != len(scores)
    ):
        raise PipelineError("Invalid external binary evaluation")
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    precision = float(precision_score(labels, predicted, zero_division=0))
    recall = float(recall_score(labels, predicted, zero_division=0))
    return {
        "rows": len(labels),
        "benign": int((labels == 0).sum()),
        "attack": int((labels == 1).sum()),
        "threshold": float(threshold),
        "pr_auc_average_precision": float(average_precision_score(labels, scores))
        if len(np.unique(labels)) == 2
        else None,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-12),
        "fpr": int(fp) / max(int(tn + fp), 1),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def missing_context_view(numbers, spec):
    """Construct absent-context indicators directly, without synthetic events/time."""
    return {
        name: float(numbers[name])
        if name in numbers
        else float(
            name.endswith("_missing")
            or name.endswith("_context_incomplete")
            or name == "role_UNKNOWN"
        )
        for name in spec["columns"]
    }


def shortcut_audit(dataset, output):
    """Train-fitted low-capacity probes; validation is explicitly development data."""
    dataset = Path(dataset)
    manifest = verify_dataset(dataset, "prepared")
    spec = load_json(dataset / "feature_spec.json")
    rows = [r for r in iter_rows(dataset / "features.parquet") if r["split"] in ("train", "val")]
    if len(rows) > 200_000:
        raise PipelineError("Short diagnostic capped at200k; use a registered streamed scale audit")
    train = [r for r in rows if r["split"] == "train"]
    val = [r for r in rows if r["split"] == "val"]
    x, vx = (np.asarray([r["x"] for r in rs], np.float32) for rs in (train, val))
    y, vy = (np.asarray([r["label"] for r in rs], np.int64) for rs in (train, val))
    protocol = validation_groups(dataset)
    ci, si = protocol["calibration_indices"], protocol["selection_indices"]
    if len(vy) != len(protocol["groups"]):
        raise PipelineError("Development probe row alignment mismatch")
    probes = {}

    def probe(name, indices, depth):
        estimator = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=64, random_state=17)
        estimator.fit(x[:, indices], y)
        score = estimator.predict_proba(vx[:, indices])[:, list(estimator.classes_).index(1)]
        threshold = threshold_at_fpr(vy[ci], score[ci], max_fpr=0.01)["threshold"]
        result = binary_metrics(vy[si], score[si], threshold)
        result.update(features=[spec["columns"][i] for i in indices], depth=depth)
        return result

    families = {
        "actor_only": lambda n: n.startswith("role_") or n == "authenticated",
        "agent_only": lambda n: n.startswith("ua_") or n.startswith("user_agent_"),
        "response_only": lambda n: n.startswith(("status_", "latency_", "response_bytes")),
        "behavior_only": lambda n: (
            n.startswith(("ip_", "user_")) and not n.startswith("user_agent_")
        ),
        "flow_only": lambda n: n.startswith("flow_"),
    }
    for name, predicate in families.items():
        indices = [i for i, n in enumerate(spec["columns"]) if predicate(n)]
        if indices:
            probes[name] = probe(name, indices, 4)
    stumps = [probe(n, [i], 1) for i, n in enumerate(spec["columns"]) if np.ptp(x[:, i]) > 0]
    stumps.sort(key=lambda v: v["pr_auc_average_precision"], reverse=True)
    overlap = {}
    for decimals in (None, 2):

        def identity(a):
            a = a if decimals is None else np.round(a, decimals)
            return hashlib.sha256(a.astype("<f4").tobytes()).digest()

        identities = {identity(a) for a in x}
        shared = np.array([identity(a) in identities for a in vx], dtype=bool)
        overlap["exact_vector" if decimals is None else "rounded_standardized_vector_2dp"] = {
            "validation_rows_matching_train": int(shared.sum()),
            "benign_matching": int(np.sum(shared & (vy == 0))),
            "attack_matching": int(np.sum(shared & (vy == 1))),
        }
    source_rows = [
        r
        for r in iter_rows(dataset / "requests.parquet")
        if r["split"] in ("train", "val") and r["label"] is not None
    ]
    identity_checks = {}
    for key in ("client_key", "user_key", "session_key", "campaign_key"):
        a = {r[key] for r in source_rows if r["split"] == "train" and r[key] is not None}
        b = {r[key] for r in source_rows if r["split"] == "val" and r[key] is not None}
        identity_checks[key] = len(a & b)
    times = {p: [r["timestamp"] for r in source_rows if r["split"] == p] for p in ("train", "val")}
    result = {
        "dataset_sha256": manifest["dataset_sha256"],
        "test_labels_used": False,
        "scope": "Already inspected lab validation is development data; these probes are not independent champion evidence",
        "train_rows": len(train),
        "val_rows": len(val),
        "identity_overlaps": identity_checks,
        "train_val_gap_seconds": min(times["val"]) - max(times["train"]),
        "label_sources": dict(Counter(r["label_source"] for r in source_rows)),
        "binary_family_conflicts": sum(
            r["label"] != int(r["attack_family"] != "benign") for r in source_rows
        ),
        "excluded_input_names": [
            n
            for n in spec["columns"]
            if n.startswith("context_suricata_")
            or n in ("label", "attack_family", "campaign_key", "timestamp", "event_key", "rule_sid")
        ],
        "view_collisions": overlap,
        "restricted_feature_probes": probes,
        "top_train_fitted_stumps": stumps[:12],
        "stump_count_examined_on_development_validation": len(stumps),
        "limits": [
            "Vector collisions are quantization/privacy collisions, not proof of repeated raw HTTP requests",
            "Disjoint HMAC identities/exact payload hashes do not prove independent semantic grammar",
            "Role/response/timing can legitimately predict attacks and also encode scenario construction; correlation alone does not identify cause",
            "No independent human label review or unseen deployment environment has been established",
        ],
    }
    atomic_json(output, result)
    return result


def external_challenge(benchmark, bundles, output, max_threads=8):
    """Frozen thresholds, no tuning, full published test including ambiguous views."""
    benchmark = Path(benchmark)
    rows = [r for r in iter_benchmark(benchmark, original=True) if r["split"] == "test"]
    if not rows or len(rows) > 200_000:
        raise PipelineError("External short challenge requires1–200k published test records")
    y = np.asarray([r["label"] for r in rows], np.int64)
    body = np.asarray([r["body_present"] for r in rows], bool)
    unique = np.asarray(list(dict.fromkeys(r["event_key"] for r in rows)))
    label_sets = {}
    for r in rows:
        label_sets.setdefault(r["event_key"], set()).add(r["label"])
    first = {r["event_key"]: i for i, r in reversed(list(enumerate(rows)))}
    unique_indices = np.array([first[k] for k in unique if len(label_sets[k]) == 1], dtype=np.int64)
    results = {}
    for name, path in bundles.items():
        path = Path(path)
        card = load_json(path / "model_manifest.json")
        for f in ("model.onnx", "feature_spec.json"):
            if file_sha256(path / f) != card["files"][f]:
                raise PipelineError("Frozen external candidate integrity failure")
        spec = load_json(path / "feature_spec.json")
        if spec.get("input_profile") != "safe_query_numeric_v2":
            raise PipelineError(
                "External stress test requires the matching EVE v2 query projection"
            )
        session = cpu_session(path / "model.onnx", max_threads)
        scores = []
        for start in range(0, len(rows), 512):
            batch = np.array(
                [
                    transform(spec, missing_context_view(json.loads(r["numbers_json"]), spec))
                    for r in rows[start : start + 512]
                ],
                np.float32,
            )
            scores.extend(session.run(None, {"input": batch})[0].tolist())
        scores = np.asarray(scores, np.float32)
        threshold = card["threshold"]
        results[name] = {
            "bundle_manifest_sha256": file_sha256(path / "model_manifest.json"),
            "full_original_test": binary_metrics(y, scores, threshold),
            "unique_nonconflicting_request_identity": binary_metrics(
                y[unique_indices], scores[unique_indices], threshold
            ),
            "body_present": binary_metrics(y[body], scores[body], threshold)
            if body.any()
            else None,
            "body_absent": binary_metrics(y[~body], scores[~body], threshold)
            if (~body).any()
            else None,
            "threshold_source": "Frozen lab calibration; external labels never fit thresholds or select configuration",
        }
    result = {
        "format_version": 1,
        "benchmark_manifest_sha256": file_sha256(benchmark / "manifest.json"),
        "test_requests": len(rows),
        "unique_request_identities": len(unique),
        "conflicting_binary_label_identities": sum(len(s) > 1 for s in label_sets.values()),
        "original_lab_final_test_opened": False,
        "models": results,
        "champion_selected": False,
        "scope": "Independent public HTTP origin with explicitly missing actor/response/flow/time; request-only OOD stress test, not equivalent to full-view lab metrics",
        "limits": [
            "Public anomalies include unseen families and body/header-only changes invisible to this feature profile",
            "Labels are publisher annotations, not independently reviewed exploit success",
            "No synthetic flow/actor/session/time is inserted; missing-context defaults are explicit",
            "No tuning or formal training uses this challenge; reusing these scores in future work makes it development data",
        ],
    }
    atomic_json(output, result)
    return result

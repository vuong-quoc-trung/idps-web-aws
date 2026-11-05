"""Frozen train-only flow-missingness ablation and 207-feature availability audit."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import verify_dataset
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import (
    FeatureExtractor,
    feature_columns,
    implementation_fingerprint,
    transform,
)
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope

AI_ROOT = Path(__file__).resolve().parents[1]
OUT = AI_ROOT / ".artifacts/glu207_flow_robustness_20261104"
FLOW_FIELDS = (
    "duration_seconds",
    "bytes_to_server",
    "bytes_to_client",
    "packets_to_server",
    "packets_to_client",
)
ARMS = {
    "duration": ("duration_seconds",),
    "bytes": ("bytes_to_server", "bytes_to_client"),
    "packets": ("packets_to_server", "packets_to_client"),
    "all_flow": FLOW_FIELDS,
}


def group_name(name):
    if name.startswith("flow_"):
        return "flow"
    if name.startswith(("ip_", "user_")) and not name.startswith("user_agent_"):
        return "temporal_behavior"
    if name.startswith(("status_", "latency_ms_", "response_bytes_")):
        return "response"
    if name.startswith("request_bytes_"):
        return "request_size"
    if name.startswith(("method_", "role_", "ua_", "user_agent_")) or name == "authenticated":
        return "method_role_agent"
    return "request_structure"


def stats(values):
    return {
        "min": float(np.min(values)),
        "p05": float(np.percentile(values, 5)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
    }


def json_builtin(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: json_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_builtin(item) for item in value]
    return value


def read_train(prepared, spec):
    requests = pq.ParquetFile(prepared / "requests.parquet")
    features = pq.ParquetFile(prepared / "features.parquet")
    extractor = FeatureExtractor(**spec["state_limits"])
    raw, x, labels, keys, families, timestamps = [], [], [], [], [], []
    parity = 0
    for group in range(82):
        req_rows = requests.read_row_group(group).to_pylist()
        feature_rows = features.read_row_group(group).to_pylist()
        if len(req_rows) != len(feature_rows):
            raise PipelineError("Request/feature row-group sizes disagree")
        for request, feature in zip(req_rows, feature_rows, strict=True):
            if request["split"] != feature["split"] or request["event_key"] != feature["event_key"]:
                raise PipelineError("Request/feature train identity mismatch")
            if request["split"] != "train":
                continue
            values = extractor.observe(request)
            expected = np.asarray(feature["x"], np.float32)
            if not np.array_equal(transform(spec, values), expected):
                raise PipelineError("Train feature replay mismatch")
            parity += 1
            raw.append([values[name] for name in spec["columns"]])
            x.append(expected)
            labels.append(int(feature["label"]))
            keys.append(feature["event_key"])
            families.append(feature["attack_family"])
            timestamps.append(float(request["timestamp"]))
    if parity != 41607:
        raise PipelineError("Unexpected train-only replay count")
    return (
        np.asarray(raw, np.float32),
        np.asarray(x, np.float32),
        np.asarray(labels, np.int64),
        keys,
        families,
        np.asarray(timestamps),
    )


def read_shadow(collected, spec):
    requests = pq.ParquetFile(collected / "requests.parquet").read().to_pylist()
    extractor = FeatureExtractor(**spec["state_limits"])
    raw, timestamps = [], []
    complete = {"STUDENT_AUDIT", "NGINX", "SURICATA"}
    for request in requests:
        values = extractor.observe(request)
        if set(request["sources"]) != complete or request["correlation"] != "request_id":
            continue
        raw.append([values[name] for name in spec["columns"]])
        timestamps.append(float(request["timestamp"]))
    if len(raw) != 54:
        raise PipelineError("Unexpected complete three-source shadow count")
    return np.asarray(raw, np.float32), np.asarray(timestamps)


def flow_timing(collected, shadow_times):
    observations = (
        pq.ParquetFile(collected / "observations.parquet")
        .read(
            columns=["source", "event_type", "timestamp", "available_at", "client_key", "flow_json"]
        )
        .to_pylist()
    )
    flows = [
        item
        for item in observations
        if item["source"] == "SURICATA" and item["event_type"] == "flow"
    ]
    if len(flows) != 54 or not all(
        json.loads(item["flow_json"]).get("duration_seconds") is not None for item in flows
    ):
        raise PipelineError("Expected 54 actual EVE flow counter observations")
    last = max(shadow_times)
    return {
        "request_span_seconds": float(max(shadow_times) - min(shadow_times)),
        "eve_flow_observations": len(flows),
        "eve_flow_event_before_last_request": sum(item["timestamp"] <= last for item in flows),
        "eve_flow_available_before_last_request": sum(
            item["available_at"] <= last for item in flows
        ),
        "earliest_flow_event_after_last_request_seconds": float(
            min(item["timestamp"] for item in flows) - last
        ),
        "earliest_flow_available_after_last_request_seconds": float(
            min(item["available_at"] for item in flows) - last
        ),
        "latest_flow_available_after_last_request_seconds": float(
            max(item["available_at"] for item in flows) - last
        ),
    }


def grouped_availability(spec, train, shadow):
    result = {}
    names = spec["columns"]
    for group in sorted({group_name(name) for name in names}):
        indices = [i for i, name in enumerate(names) if group_name(name) == group]
        train_zero = np.mean(train[:, indices] == 0, axis=0)
        shadow_zero = np.mean(shadow[:, indices] == 0, axis=0)
        missing = [i for i in indices if names[i].endswith(("_missing", "_context_incomplete"))]
        result[group] = {
            "columns": len(indices),
            "train_columns_nonzero": int(np.sum(np.any(train[:, indices] != 0, axis=0))),
            "shadow_columns_nonzero": int(np.sum(np.any(shadow[:, indices] != 0, axis=0))),
            "shadow_columns_varying": int(np.sum(np.ptp(shadow[:, indices], axis=0) > 0)),
            "train_median_zero_rate": float(np.median(train_zero)),
            "shadow_median_zero_rate": float(np.median(shadow_zero)),
            "columns_zero_rate_gap_ge_0_5": int(np.sum(np.abs(train_zero - shadow_zero) >= 0.5)),
            "explicit_missing_indicator_columns": len(missing),
            "mean_explicit_missing_rate_train": (
                float(np.mean(train[:, missing])) if missing else None
            ),
            "mean_explicit_missing_rate_shadow": (
                float(np.mean(shadow[:, missing])) if missing else None
            ),
            "zero_rate_note": "Raw zero may be a valid value; only explicit indicators define missingness",
        }
    return result


def sample_indices(labels, flow_present, keys, seed, per_class):
    selected = []
    for class_name, desired in (("benign", labels == 0), ("attack", labels != 0)):
        candidates = np.flatnonzero(desired & flow_present)
        if len(candidates) < per_class:
            raise PipelineError(f"Insufficient flow-observed {class_name} train rows")
        ordered = sorted(
            candidates,
            key=lambda i: hashlib.sha256(f"{seed}:{keys[i]}".encode()).digest(),
        )
        selected.extend(ordered[:per_class])
    return np.asarray(selected, np.int64)


def missing_value(spec, name, raw):
    index = spec["columns"].index(name)
    value = np.clip(raw, *spec["raw_clip"])
    return np.float32(np.clip((value - spec["mean"][index]) / spec["std"][index], *spec["clip"]))


def ablate(x, spec, fields):
    result = x.copy()
    for field in fields:
        for suffix, raw in (("_log1p", 0.0), ("_missing", 1.0)):
            name = "flow_" + field + suffix
            result[:, spec["columns"].index(name)] = missing_value(spec, name, raw)
    return result


def infer(session, x, batch=128):
    scores, probabilities = [], []
    for start in range(0, len(x), batch):
        score, probs = session.run(None, {"input": x[start : start + batch]})
        scores.append(score)
        probabilities.append(probs)
    return np.concatenate(scores), np.concatenate(probabilities)


def main():
    plan = load_json(OUT / "plan.json")
    if file_sha256(__file__) != plan["script_sha256"]:
        raise PipelineError("Frozen diagnostic code changed")
    prepared = AI_ROOT / plan["train_dataset"]
    collected = AI_ROOT / plan["shadow_dataset"]
    candidate = AI_ROOT / plan["candidate_root"]
    for path, expected in (
        (prepared / "dataset_manifest.json", plan["train_manifest_sha256"]),
        (prepared / "feature_spec.json", plan["feature_spec_sha256"]),
        (prepared / "features.parquet", plan["train_features_sha256"]),
        (prepared / "requests.parquet", plan["train_requests_sha256"]),
        (collected / "dataset_manifest.json", plan["shadow_manifest_sha256"]),
        (collected / "requests.parquet", plan["shadow_requests_sha256"]),
        (collected / "observations.parquet", plan["shadow_observations_sha256"]),
        (candidate / "research-final.onnx", plan["onnx_sha256"]),
    ):
        if file_sha256(path) != expected:
            raise PipelineError("Frozen input checksum changed")
    verify_dataset(collected, "collected")
    spec = load_json(prepared / "feature_spec.json")
    if (
        len(spec["columns"]) != 207
        or spec["implementation_sha256"] != implementation_fingerprint()
        or spec["columns"]
        != feature_columns(input_profile="safe_query_numeric_v2", behavior_dynamics=True)
    ):
        raise PipelineError("207 feature names/order/preprocessing changed")
    checkpoint = load_checkpoint(candidate / "run")
    if (
        file_sha256(checkpoint.path / "manifest.json") != plan["checkpoint_manifest_sha256"]
        or checkpoint.model.kind != "residual_glu"
        or checkpoint.model.input_dim != 207
        or checkpoint.model.steps != 652
    ):
        raise PipelineError("Frozen candidate checkpoint changed")
    raw_train, x_train, labels, keys, families, train_times = read_train(prepared, spec)
    raw_shadow, shadow_times = read_shadow(collected, spec)
    columns = spec["columns"]
    duration = columns.index("flow_duration_seconds_missing")
    present = raw_train[:, duration] == 0
    if int(np.sum(present)) != 36443 or np.any(raw_shadow[:, duration] != 1):
        raise PipelineError("Observed flow availability changed")
    selected = sample_indices(labels, present, keys, plan["seed"], plan["per_class"])
    selected_digest = hashlib.sha256("\n".join(keys[i] for i in selected).encode()).hexdigest()
    if selected_digest != plan["selected_event_keys_sha256"]:
        raise PipelineError("Frozen train-only sample changed")
    first_present = float(np.min(train_times[present]) - np.min(train_times))
    naturally_missing = np.flatnonzero(~present)[0]
    if not np.array_equal(
        x_train[
            naturally_missing,
            [
                columns.index("flow_" + field + suffix)
                for field in FLOW_FIELDS
                for suffix in ("_log1p", "_missing")
            ],
        ],
        ablate(x_train[naturally_missing : naturally_missing + 1], spec, FLOW_FIELDS)[
            0,
            [
                columns.index("flow_" + field + suffix)
                for field in FLOW_FIELDS
                for suffix in ("_log1p", "_missing")
            ],
        ],
    ):
        raise PipelineError("Counterfactual missing-flow encoding differs from natural missingness")
    with resource_envelope(4, 16) as (guard, resources):
        session = cpu_session(candidate / "research-final.onnx", max_threads=4)
        base_scores, base_probs = infer(session, x_train[selected])
        native_scores, native_probs = checkpoint.model.predict(x_train[selected[:16]])
        if not (
            np.allclose(base_scores[:16], native_scores, rtol=1e-5, atol=1e-6)
            and np.allclose(base_probs[:16], native_probs, rtol=1e-5, atol=1e-6)
        ):
            raise PipelineError("Checkpoint and ONNX parity failed")
        arms = {}
        for name, fields in ARMS.items():
            scores, probs = infer(session, ablate(x_train[selected], spec, fields))
            delta = scores - base_scores
            changed = np.argmax(probs, axis=1) != np.argmax(base_probs, axis=1)
            arms[name] = {
                "fields": list(fields),
                "score_delta": stats(delta),
                "absolute_score_delta": stats(np.abs(delta)),
                "mean_signed_score_delta": float(np.mean(delta)),
                "argmax_class_changes": int(np.sum(changed)),
                "abs_delta_gt_0_1": int(np.sum(np.abs(delta) > 0.1)),
                "abs_delta_gt_0_25": int(np.sum(np.abs(delta) > 0.25)),
            }
            if name == "all_flow":
                top = np.argsort(np.abs(delta))[-50:]
                arms[name]["largest_50_development_families"] = dict(
                    Counter(families[selected[i]] for i in top)
                )
                arms[name]["by_development_binary_label"] = {
                    group: {
                        "rows": int(np.sum(mask)),
                        "argmax_class_changes": int(np.sum(changed[mask])),
                        "median_abs_delta": float(np.median(np.abs(delta[mask]))),
                        "p95_abs_delta": float(np.percentile(np.abs(delta[mask]), 95)),
                    }
                    for group, mask in (
                        ("benign", labels[selected] == 0),
                        ("attack", labels[selected] != 0),
                    )
                }
            if guard.check() or guard.thermal_limit_reached:
                raise PipelineError("Resource or thermal guard stopped diagnostic")
        report = {
            "status": "TRAIN_ONLY_SYNTHETIC_MISSINGNESS_DIAGNOSTIC",
            "plan_sha256": file_sha256(OUT / "plan.json"),
            "train_rows": len(raw_train),
            "train_span_seconds": float(max(train_times) - min(train_times)),
            "train_prior_flow_rows": int(np.sum(present)),
            "train_first_prior_flow_seconds_after_start": first_present,
            "train_rows_before_first_prior_flow": int(
                np.sum(train_times < np.min(train_times[present]))
            ),
            "shadow_rows": len(raw_shadow),
            "shadow_prior_flow_rows": int(np.sum(raw_shadow[:, duration] == 0)),
            "shadow_flow_timing": flow_timing(collected, shadow_times),
            "windows_seconds": [10, 60, 300],
            "window_incomplete_rates": {
                name: {
                    "train": float(np.mean(raw_train[:, columns.index(name)])),
                    "shadow": float(np.mean(raw_shadow[:, columns.index(name)])),
                }
                for scope in ("ip", "user")
                for seconds in (10, 60, 300)
                for name in (f"{scope}_{seconds}s_context_incomplete",)
            },
            "feature_groups": grouped_availability(spec, raw_train, raw_shadow),
            "train_feature_replay_exact": len(raw_train),
            "shadow_207_values_finite": bool(np.isfinite(raw_shadow).all()),
            "sampled_train_only_rows": len(selected),
            "sampled_train_only_unique_views": len({x_train[i].tobytes() for i in selected}),
            "sampled_benign_development": int(np.sum(labels[selected] == 0)),
            "sampled_attack_development": int(np.sum(labels[selected] != 0)),
            "baseline_score_distribution": stats(base_scores),
            "counterfactual_arms": arms,
            "native_onnx_parity_first_16": "PASS",
            "threshold": None,
            "recall": None,
            "fpr": None,
            "formal_admitted_requests": 0,
            "request_id_overlap_train_shadow": None,
            "resource_guard": guard.metrics(),
            "resource_envelope": resources,
            "interpretation_limits": [
                "Ablation changes one observed group to its legitimate missing encoding, not a real new request",
                "Development runner labels are not independent attack ground truth",
                "Argmax changes are eight-class predictions, not alerts under a calibrated threshold",
                "No final holdout, development validation, or test row was used",
                "No model weights, threshold, or feature semantics were changed",
            ],
        }
        report = json_builtin(report)
        atomic_json(OUT / "report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "train_prior_flow_rows": report["train_prior_flow_rows"],
                "shadow_prior_flow_rows": report["shadow_prior_flow_rows"],
                "all_flow_argmax_changes": arms["all_flow"]["argmax_class_changes"],
                "all_flow_median_abs_score_delta": arms["all_flow"]["absolute_score_delta"][
                    "median"
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

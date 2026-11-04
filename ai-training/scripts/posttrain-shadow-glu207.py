"""Read-only, aggregate-only shadow diagnostic for the frozen GLU207 checkpoint."""

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
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
OUT = AI_ROOT / ".artifacts/posttrain_shadow_glu207_20261104"


def percentile(values):
    return {
        name: float(value)
        for name, value in zip(
            ("min", "p05", "p50", "p95", "max"),
            np.percentile(values, (0, 5, 50, 95, 100)),
            strict=True,
        )
    }


def main():
    plan = load_json(OUT / "plan.json")
    if file_sha256(__file__) != plan["script_sha256"]:
        raise PipelineError("Shadow diagnostic source changed after plan freeze")
    collected = AI_ROOT / plan["collected_dataset"]
    prepared = AI_ROOT / plan["training_dataset"]
    candidate = AI_ROOT / plan["candidate_root"]
    if (
        file_sha256(collected / "dataset_manifest.json") != plan["collected_manifest_sha256"]
        or file_sha256(collected / "requests.parquet") != plan["collected_requests_sha256"]
        or file_sha256(prepared / "features.parquet") != plan["train_features_sha256"]
        or file_sha256(prepared / "feature_spec.json") != plan["feature_spec_sha256"]
        or file_sha256(prepared / "dataset_manifest.json") != plan["train_manifest_sha256"]
        or file_sha256(candidate / "report.json") != plan["candidate_report_sha256"]
        or file_sha256(candidate / "research-final.onnx") != plan["onnx_sha256"]
    ):
        raise PipelineError("Frozen input checksum changed")
    manifest = verify_dataset(collected, "collected")
    train_manifest = load_json(prepared / "dataset_manifest.json")
    if manifest["redaction_key_fingerprint"] == train_manifest["redaction_key_fingerprint"]:
        raise PipelineError("Expected separate HMAC namespaces for this diagnostic")
    spec = load_json(prepared / "feature_spec.json")
    if (
        spec["feature_version"] != "ai-features-5"
        or spec["implementation_sha256"] != implementation_fingerprint()
        or spec["columns"]
        != feature_columns(input_profile="safe_query_numeric_v2", behavior_dynamics=True)
        or len(spec["columns"]) != 207
        or manifest["input_profile"] != "safe_query_numeric_v2"
    ):
        raise PipelineError("207-feature preprocessing contract mismatch")
    loaded = load_checkpoint(candidate / "run")
    model = loaded.model
    if (
        file_sha256(loaded.path / "manifest.json") != plan["checkpoint_manifest_sha256"]
        or loaded.state.get("freeze_sha256") != plan["candidate_freeze_sha256"]
        or model.kind != "residual_glu"
        or model.input_dim != 207
        or model.steps != 652
        or sum(p.size for p in model.parameters.values()) != 9_675_784
    ):
        raise PipelineError("Candidate checkpoint contract mismatch")
    rows = list(iter_rows(collected / "requests.parquet"))
    expected_sources = {"STUDENT_AUDIT", "NGINX", "SURICATA"}
    if len(rows) != 55 or any(r["label"] is not None for r in rows):
        raise PipelineError("Unexpected labeled or resized shadow cohort")
    extractor = FeatureExtractor(**spec["state_limits"])
    vectors, keys, raw_presence = [], [], Counter()
    values_by_column = {name: set() for name in spec["columns"]}
    for row in rows:
        values = extractor.observe(row)
        if set(row["sources"]) != expected_sources or row["correlation"] != "request_id":
            continue
        vector = transform(spec, values)
        if vector.shape != (207,) or not np.isfinite(vector).all():
            raise PipelineError("Non-finite shadow vector")
        vectors.append(vector)
        keys.append(row["event_key"])
        for name in spec["columns"]:
            values_by_column[name].add(float(values[name]))
        raw_presence["prior_flow"] += (
            json.loads(row["flow_json"]).get("duration_seconds") is not None
        )
        raw_presence["query_original"] += (
            json.loads(row["numeric_json"]).get("query_original_available") == 1
        )
        raw_presence["status_code"] += row["status_code"] is not None
        raw_presence["latency_ms"] += row["latency_ms"] is not None
        raw_presence["request_bytes"] += row["request_bytes"] is not None
        raw_presence["response_bytes"] += row["response_bytes"] is not None
    if len(vectors) != plan["eligible_requests"] or len(set(keys)) != len(keys):
        raise PipelineError("Incomplete or duplicate request-ID shadow cohort")
    x = np.stack(vectors)
    # Only the 82 train-containing row groups are opened. No test row group is read.
    pf = pq.ParquetFile(prepared / "features.parquet")
    train_vectors, train_keys, train_presence = [], set(), Counter()
    for group in range(82):
        for row in pf.read_row_group(group, columns=["split", "event_key", "x"]).to_pylist():
            if row["split"] != "train":
                continue
            train_vectors.append(np.asarray(row["x"], np.float32))
            train_keys.add(row["event_key"])
    if len(train_vectors) != 41607:
        raise PipelineError("Train reference count changed")
    train = np.stack(train_vectors)
    train_hashes = {hashlib.sha256(v.tobytes()).digest() for v in train}
    exact_overlaps = sum(hashlib.sha256(v.tobytes()).digest() in train_hashes for v in x)
    event_key_string_overlaps = len(train_keys.intersection(keys))
    train_norm = np.linalg.norm(train, axis=1)
    shadow_norm = np.linalg.norm(x, axis=1)
    similarities = (x @ train.T) / np.maximum(shadow_norm[:, None] * train_norm[None, :], 1e-12)
    max_cosine = similarities.max(axis=1)
    request_pf = pq.ParquetFile(prepared / "requests.parquet")
    for group in range(82):
        for row in request_pf.read_row_group(group, columns=["split", "flow_json"]).to_pylist():
            if row["split"] == "train":
                train_presence["prior_flow"] += (
                    json.loads(row["flow_json"]).get("duration_seconds") is not None
                )
                train_presence["rows"] += 1
    if train_presence["rows"] != 41607:
        raise PipelineError("Training request reference count changed")
    timings, scores, max_parity_error = [], [], 0.0
    with resource_envelope(4, 16) as (guard, resources):
        session = cpu_session(candidate / "research-final.onnx", max_threads=4)
        for vector in x:
            start = time.perf_counter_ns()
            onnx_score, onnx_probs = session.run(None, {"input": vector[None, :]})
            timings.append((time.perf_counter_ns() - start) / 1e6)
            native_score, native_probs = model.predict(vector[None, :])
            if not (
                np.isfinite(onnx_score).all()
                and np.isfinite(onnx_probs).all()
                and np.allclose(onnx_score, native_score, rtol=1e-5, atol=1e-6)
                and np.allclose(onnx_probs, native_probs, rtol=1e-5, atol=1e-6)
            ):
                raise PipelineError("Checkpoint/ONNX parity failed on shadow vectors")
            max_parity_error = max(
                max_parity_error, float(np.max(np.abs(onnx_probs - native_probs)))
            )
            scores.append(float(onnx_score[0]))
            if guard.check() or guard.thermal_limit_reached:
                raise PipelineError("Resource or thermal guard stopped shadow inference")
        report = {
            "status": "TECHNICAL_DIAGNOSTIC_ONLY",
            "plan_sha256": file_sha256(OUT / "plan.json"),
            "checkpoint_manifest_sha256": plan["checkpoint_manifest_sha256"],
            "feature_spec_sha256": plan["feature_spec_sha256"],
            "collected_dataset_sha256": manifest["dataset_sha256"],
            "new_http_requests_sent": 0,
            "collected_requests": len(rows),
            "inferred_three_source_requests": len(x),
            "unlabeled_requests": len(x),
            "independently_verified_benign": 0,
            "independently_verified_attack": 0,
            "train_rows_reference": len(train),
            "request_id_overlap_train": None,
            "event_key_string_overlap_train": event_key_string_overlaps,
            "cross_capture_request_identity_comparable": False,
            "redaction_key_fingerprints": {
                "train": train_manifest["redaction_key_fingerprint"],
                "shadow": manifest["redaction_key_fingerprint"],
            },
            "exact_float32_view_overlap_train": exact_overlaps,
            "nearest_train_cosine": percentile(max_cosine),
            "nearest_train_cosine_ge_0_995": int(np.sum(max_cosine >= 0.995)),
            "feature_columns": 207,
            "columns_varying": sum(len(v) > 1 for v in values_by_column.values()),
            "columns_nonzero_at_least_once": sum(
                any(value != 0 for value in v) for v in values_by_column.values()
            ),
            "raw_presence": dict(raw_presence),
            "train_prior_flow_available": dict(train_presence),
            "score_distribution_unlabeled": percentile(scores),
            "onnx_probability_max_abs_error": max_parity_error,
            "onnx_latency_ms_forward_only": percentile(timings),
            "resource_guard": guard.metrics(),
            "resource_envelope": resources,
            "fpr_budget_policy": 0.01,
            "threshold": None,
            "recall": None,
            "fpr": None,
            "pr_auc": None,
            "release_ready": False,
            "limitations": [
                "Same Student lab as training; no environment independence",
                "No reviewed request-level intent labels; score distribution is not detection quality",
                "Prior completed EVE flow absent on these 54 despite train availability on most rows",
                "Offline captured PCAP replay; this run is not live edge serving or Rust parity",
                "ONNX latency excludes feature extraction, correlation, IO, and model loading",
                "Cosine proximity is feature similarity, not proof of physical duplicate or label leakage",
                "Different HMAC redaction-key namespaces prevent cross-capture request-ID overlap verification",
            ],
        }
        atomic_json(OUT / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "inferred_three_source_requests",
                    "exact_float32_view_overlap_train",
                    "nearest_train_cosine_ge_0_995",
                    "score_distribution_unlabeled",
                    "onnx_latency_ms_forward_only",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Frozen GLU207 threshold viability on unique development training views only."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope

AI_ROOT = Path(__file__).resolve().parents[1]
OUT = AI_ROOT / ".artifacts/attack_threshold_viability_20261104"


def distribution(scores):
    return {
        key: float(value)
        for key, value in zip(
            ("min", "p05", "p25", "median", "p75", "p95", "max"),
            np.percentile(scores, (0, 5, 25, 50, 75, 95, 100)),
            strict=True,
        )
    }


def main():
    plan = load_json(OUT / "plan.json")
    if file_sha256(__file__) != plan["script_sha256"]:
        raise PipelineError("Frozen diagnostic code changed")
    prepared = AI_ROOT / plan["prepared_dataset"]
    candidate = AI_ROOT / plan["candidate_root"]
    threshold_path = AI_ROOT / plan["threshold_manifest"]
    for path, expected in (
        (prepared / "features.parquet", plan["features_sha256"]),
        (prepared / "requests.parquet", plan["requests_sha256"]),
        (prepared / "feature_spec.json", plan["feature_spec_sha256"]),
        (prepared / "dataset_manifest.json", plan["dataset_manifest_sha256"]),
        (candidate / "research-final.onnx", plan["onnx_sha256"]),
        (threshold_path, plan["threshold_manifest_sha256"]),
    ):
        if file_sha256(path) != expected:
            raise PipelineError("Frozen input checksum mismatch")
    frozen = load_json(threshold_path)
    spec = load_json(prepared / "feature_spec.json")
    if (
        frozen["threshold"] != plan["threshold"]
        or frozen["status"] != "PROVISIONAL_BENIGN_ONLY"
        or frozen["onnx_sha256"] != plan["onnx_sha256"]
        or frozen["feature_spec_sha256"] != plan["feature_spec_sha256"]
        or len(spec["columns"]) != 207
        or tuple(CLASSES) != tuple(plan["classes"])
    ):
        raise PipelineError("Threshold or 207-class contract mismatch")
    checkpoint = load_checkpoint(candidate / "run")
    if (
        file_sha256(checkpoint.path / "manifest.json") != plan["checkpoint_manifest_sha256"]
        or checkpoint.model.steps != 652
        or checkpoint.model.kind != "residual_glu"
        or checkpoint.model.input_dim != 207
        or sum(p.size for p in checkpoint.model.parameters.values()) != 9_675_784
    ):
        raise PipelineError("Frozen checkpoint mismatch")
    feature_file = pq.ParquetFile(prepared / "features.parquet")
    request_file = pq.ParquetFile(prepared / "requests.parquet")
    seen = {}
    feature_rows = []
    raw_rows = 0
    repeated = 0
    labels_by_source = defaultdict(Counter)
    labels_by_provenance = defaultdict(Counter)
    label_sources = Counter()
    for group in range(82):
        features = feature_file.read_row_group(
            group, columns=["split", "event_key", "label", "attack_family", "x"]
        ).to_pylist()
        requests = request_file.read_row_group(
            group,
            columns=[
                "split",
                "event_key",
                "label",
                "attack_family",
                "source",
                "label_source",
                "provenance",
                "flow_json",
                "campaign_key",
            ],
        ).to_pylist()
        if len(features) != len(requests):
            raise PipelineError("Feature/request row-group boundary mismatch")
        for feature, request in zip(features, requests, strict=True):
            if feature["split"] != request["split"] or feature["event_key"] != request["event_key"]:
                raise PipelineError("Feature/request identity mismatch")
            if feature["split"] != "train":
                continue  # mixed final row group includes development validation bytes
            if (
                feature["label"] != request["label"]
                or feature["attack_family"] != request["attack_family"]
            ):
                raise PipelineError("Development label metadata mismatch")
            raw_rows += 1
            label = int(feature["label"])
            if label not in (0, 1) or feature["attack_family"] not in CLASSES:
                raise PipelineError("Binary label/family mapping mismatch")
            if (label == 0) != (feature["attack_family"] == "benign"):
                raise PipelineError("Benign/attack family mapping mismatch")
            vector = np.asarray(feature["x"], np.float32)
            if vector.shape != (207,) or not np.isfinite(vector).all():
                raise PipelineError("Invalid train vector")
            key = hashlib.sha256(vector.tobytes()).digest()
            if key in seen:
                if seen[key] != label:
                    raise PipelineError("Conflicting labels on one float32 train view")
                repeated += 1
                continue
            seen[key] = label
            flow = json.loads(request["flow_json"] or "{}")
            flow_present = flow.get("duration_seconds") is not None
            feature_rows.append((vector, label, feature["attack_family"], flow_present))
            labels_by_source[request["source"]][feature["attack_family"]] += 1
            labels_by_provenance[request["provenance"]][feature["attack_family"]] += 1
            label_sources[request["label_source"]] += 1
    if raw_rows != 41607 or len(feature_rows) != 41585 or repeated != 22:
        raise PipelineError("Train partition or dedup count changed")
    vectors = np.stack([row[0] for row in feature_rows])
    labels = np.asarray([row[1] for row in feature_rows], np.int64)
    flow_present = np.asarray([row[3] for row in feature_rows], bool)
    threshold = np.float32(plan["threshold"])
    scores = []
    with resource_envelope(4, 16) as (guard, resources):
        session = cpu_session(candidate / "research-final.onnx", max_threads=4)
        for start in range(0, len(vectors), 128):
            score, probabilities = session.run(None, {"input": vectors[start : start + 128]})
            if score.shape != (min(128, len(vectors) - start),) or probabilities.shape[1] != len(
                CLASSES
            ):
                raise PipelineError("ONNX output shape mismatch")
            if not np.allclose(score, 1.0 - probabilities[:, 0], rtol=1e-5, atol=1e-6):
                raise PipelineError("Positive score direction mismatch")
            scores.append(score)
            if guard.check() or guard.thermal_limit_reached:
                raise PipelineError("Resource guard stopped diagnostic")
        scores = np.concatenate(scores)
        flagged = scores >= threshold
        margin = scores - threshold
        benign = labels == 0
        attack = ~benign
        by_family = {}
        families = np.asarray([row[2] for row in feature_rows])
        for family in CLASSES:
            mask = families == family
            group_scores = scores[mask]
            by_family[family] = {
                "unique_train_views": int(mask.sum()),
                "flagged": int(flagged[mask].sum()),
                "flag_rate_train_only": float(np.mean(flagged[mask])),
                "scores": distribution(group_scores),
                "prior_flow_available": int(np.sum(flow_present[mask])),
                "below_threshold_prior_flow_available": int(
                    np.sum((~flagged) & mask & flow_present)
                ),
                "below_threshold_prior_flow_missing": int(
                    np.sum((~flagged) & mask & (~flow_present))
                ),
            }
        missed = attack & (~flagged)
        risk = {
            "attack_below_threshold": int(missed.sum()),
            "attack_below_threshold_with_flow": int(np.sum(missed & flow_present)),
            "attack_below_threshold_missing_flow": int(np.sum(missed & (~flow_present))),
            "attack_within_0_01_below_threshold": int(
                np.sum(attack & (margin < 0) & (margin >= -0.01))
            ),
            "attack_within_0_05_below_threshold": int(
                np.sum(attack & (margin < 0) & (margin >= -0.05))
            ),
            "benign_within_0_01_above_threshold": int(
                np.sum(benign & (margin >= 0) & (margin <= 0.01))
            ),
            "benign_within_0_05_below_threshold": int(
                np.sum(benign & (margin < 0) & (margin >= -0.05))
            ),
            "missed_attack_margin_quantiles": distribution(margin[missed])
            if np.any(missed)
            else None,
        }
        report = {
            "status": "TRAINING_VIEW_THRESHOLD_VIABILITY_DIAGNOSTIC_ONLY",
            "plan_sha256": file_sha256(OUT / "plan.json"),
            "threshold_manifest_sha256": plan["threshold_manifest_sha256"],
            "model_checkpoint_manifest_sha256": plan["checkpoint_manifest_sha256"],
            "threshold": float(threshold),
            "score_semantics": "1 - P(benign class 0); larger score means more attack-like",
            "label_semantics": "scenario_manifest development binary label 0 benign/1 attack; attack_family separately names seven families; not independent Ground Truth",
            "raw_train_rows": raw_rows,
            "unique_float32_train_views": len(feature_rows),
            "same_label_repeated_views": repeated,
            "conflicting_label_views": 0,
            "benign_unique_train_views": int(benign.sum()),
            "attack_unique_train_views": int(attack.sum()),
            "benign_flagged_train_views": int(np.sum(benign & flagged)),
            "attack_flagged_train_views": int(np.sum(attack & flagged)),
            "train_positive_flag_rate": float(np.mean(flagged[attack])),
            "train_benign_flag_rate": float(np.mean(flagged[benign])),
            "benign_score_distribution": distribution(scores[benign]),
            "attack_score_distribution": distribution(scores[attack]),
            "by_family": by_family,
            "false_negative_risk_train_only": risk,
            "labels_by_source": {k: dict(v) for k, v in labels_by_source.items()},
            "labels_by_provenance": {k: dict(v) for k, v in labels_by_provenance.items()},
            "label_sources": dict(label_sources),
            "request_id_overlap_across_hmac_namespaces": None,
            "independent_recall": None,
            "fpr_on_new_cohort": None,
            "formal_admitted": 0,
            "model_or_threshold_changed": False,
            "resource_guard": guard.metrics(),
            "resource_envelope": resources,
            "limits": [
                "All scored views were used to fit this checkpoint; flag rate is not independent recall",
                "Development scenario labels are not independent attack intent evidence",
                "Last train row group physically contains 377 development validation rows; discarded before scoring/statistics",
                "Source/campaign association in one lab cannot establish domain generalization",
            ],
        }
        atomic_json(OUT / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "benign_unique_train_views",
                    "attack_unique_train_views",
                    "attack_flagged_train_views",
                    "train_positive_flag_rate",
                    "benign_flagged_train_views",
                )
            }
        )
    )


if __name__ == "__main__":
    main()

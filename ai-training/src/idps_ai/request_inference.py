"""Separate request-view inference. No Web/DB/firewall calls or family guessing."""

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.data.readers import eve_request_id
from idps_ai.data.request_corpus import PAYLOAD_FAMILIES
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import transform
from idps_ai.features.request_view import PROFILE, fingerprint, project_request, validate_view
from idps_ai.training.evaluation import latency_ms
from idps_ai.training.generalization import binary_metrics


def has_flow_observation(flow):
    """Count usable causal flow values, excluding metadata-only/null dictionaries."""
    return any(
        isinstance(flow.get(key), (int, float))
        and not isinstance(flow[key], bool)
        and math.isfinite(flow[key])
        and flow[key] >= 0
        for key in (
            "duration_seconds",
            "bytes_to_server",
            "bytes_to_client",
            "packets_to_server",
            "packets_to_client",
        )
    )


class RequestInferencePipeline:
    def __init__(self, bundle, max_threads=1):
        self.bundle = Path(bundle)
        self.manifest = load_json(self.bundle / "model_manifest.json")
        if self.manifest.get("profile") != PROFILE:
            raise PipelineError(
                "A request-structure-v1 bundle is required; fused v5 is a separate contract"
            )
        for f in ("model.onnx", "feature_spec.json"):
            if file_sha256(self.bundle / f) != self.manifest["files"][f]:
                raise PipelineError("Request bundle integrity failure")
        self.spec = load_json(self.bundle / "feature_spec.json")
        if self.spec["implementation_sha256"] != fingerprint():
            raise PipelineError("Request preprocessing contract changed")
        self.session = cpu_session(self.bundle / "model.onnx", max_threads)

    def predict_views(self, views):
        if not 1 <= len(views) <= 4096:
            raise PipelineError("Request inference batch must contain1–4096observations")
        x = np.asarray([transform(self.spec, validate_view(v)) for v in views], np.float32)
        if not len(x):
            raise PipelineError("No request observations")
        score, output = self.session.run(None, {"input": x})
        if not np.isfinite(score).all() or not np.isfinite(output).all():
            raise PipelineError("Nonfinite request inference output")
        return score

    def observe(self, view):
        score = float(self.predict_views([view])[0])
        above = score >= self.manifest["threshold"]
        return {
            "score": score,
            "above_threshold": above,
            "decision": (
                "anomaly_candidate"
                if self.manifest["model_kind"] == "denoising_autoencoder"
                else "attack_candidate"
            )
            if above
            else "below_threshold",
            "family_candidate": None,
            "profile": PROFILE,
            "enforcement_actions": 0,
        }

    def observe_uri(self, target, method="GET"):
        return self.observe(project_request(target, method))


def fresh_lab_evaluation(dataset, eve, observer, student_audit, nginx, bundles, output, cpus=4):
    from idps_ai.data.request_corpus import verify_requests

    training_manifest = verify_requests(dataset)
    labels = {}
    with Path(observer).open() as stream:
        for line in stream:
            r = json.loads(line)
            labels[r["request_id"]] = r
    rows = []
    with Path(eve).open() as stream:
        for line in stream:
            r = json.loads(line)
            if r.get("event_type") != "http":
                continue
            rid = eve_request_id(r.get("http") or {})
            if rid in labels:
                rows.append((rid, r["ai_request_view"], labels[rid]))
    if not rows or len(rows) != len(labels):
        raise PipelineError("Fresh held-out observer/EVE coverage mismatch")
    sources = {}
    for name, path in [("student", student_audit), ("nginx", nginx)]:
        with Path(path).open() as stream:
            sources[name] = {json.loads(line).get("request_id") for line in stream}
    correlated = sum(rid in sources["student"] and rid in sources["nginx"] for rid, view, r in rows)
    train_keys = {
        r["feature_key"]
        for r in iter_rows(Path(dataset) / "requests.parquet", columns=["split", "feature_key"])
        if r["split"] == "train"
    }
    y = np.array([r["label"] for rid, v, r in rows])
    eligible = np.array(
        [
            r["review_status"] == "approved" and r["attack_family"] in PAYLOAD_FAMILIES | {"benign"}
            for rid, v, r in rows
        ]
    )
    novel = np.array([digest(v["numbers"]) not in train_keys for rid, v, r in rows])
    pending = np.array([r["review_status"] != "approved" for rid, v, r in rows])
    results = {}
    for name, path in bundles.items():
        pipeline = RequestInferencePipeline(path, cpus)
        if pipeline.manifest["dataset_sha256"] != training_manifest["dataset_sha256"]:
            raise PipelineError("Fresh cohort comparison uses a different training dataset")
        scores = np.concatenate(
            [
                pipeline.predict_views([v for rid, v, r in rows[i : i + 512]])
                for i in range(0, len(rows), 512)
            ]
        )
        threshold = pipeline.manifest["threshold"]
        families = {}
        for family in sorted({r["attack_family"] for rid, v, r in rows}):
            mask = np.array([r["attack_family"] == family for rid, v, r in rows])
            families[family] = {
                "requests": int(mask.sum()),
                "flagged": int(np.sum(scores[mask] >= threshold)),
                "known_limitation": family not in PAYLOAD_FAMILIES | {"benign"},
            }
        results[name] = {
            "bundle_manifest_sha256": file_sha256(Path(path) / "model_manifest.json"),
            "approved_request_task": binary_metrics(y[eligible], scores[eligible], threshold),
            "novel_view_request_task": binary_metrics(
                y[eligible & novel], scores[eligible & novel], threshold
            ),
            "full_intent_all_families_diagnostic": binary_metrics(y, scores, threshold),
            "pending_expected_http_contract_diagnostic": binary_metrics(
                y[pending], scores[pending], threshold
            )
            if pending.any()
            else None,
            "binary_detection_by_intent_family": families,
            "threshold_tuned_on_fresh_cohort": False,
            "latency_ms": {
                "scope": "warm batch1 envelope validation/scaling/ONNX; packet capture and URI projection excluded",
                **latency_ms(pipeline.predict_views, [rows[0][1]], repeats=100),
            },
        }
    result = {
        "format_version": 1,
        "cohort_requests": len(rows),
        "three_source_correlated_requests": correlated,
        "approved_request_task_rows": int(eligible.sum()),
        "pending_http_contract_rows": int(pending.sum()),
        "novel_views": int(novel.sum()),
        "raw_view_collisions_with_training": int((~novel).sum()),
        "models": results,
        "intent_families": dict(Counter(r["attack_family"] for rid, v, r in rows)),
        "original_final_test_quality_opened": False,
        "champion_selected": False,
        "enforcement_actions": 0,
        "limits": [
            "New temporal cohort with new authored grammars and three concurrent clients, same owned environment",
            "Intent/HTTP-contract labels are not independent human review or proof of exploit success",
            "HEAD/OPTIONS403pending cases remain in raw/full diagnostics; not relabeled to make results look better",
            "Request-only task cannot observe UA/sequence/role/flow attacks; all-family metric is diagnostic",
            "Novel-only subset supplements full eligible cohort; no hard cases are silently removed",
            "Do not tune on this exposed cohort and later claim it as fresh held-out evidence",
        ],
    }
    atomic_json(output, result)
    return result


def fused_baseline_evaluation(collected, observer, key_file, bundles, output):
    """Frozen original207-feature candidates on the same new full3source cohort."""
    from idps_ai.data.dataset import verify_dataset
    from idps_ai.data.privacy import pseudonym
    from idps_ai.inference import InferencePipeline

    manifest = verify_dataset(collected, "collected")
    key = Path(key_file).read_bytes()
    with Path(observer).open() as stream:
        labels = {pseudonym(key, "request", v["request_id"]): v for v in map(json.loads, stream)}
    rows = [
        r for r in iter_rows(Path(collected) / "requests.parquet") if r["request_key"] in labels
    ]
    if not rows or len(rows) != len(labels):
        raise PipelineError("Full3source cohort/observer identity mismatch")
    intents = [labels[r["request_key"]] for r in rows]
    y = np.array([r["label"] for r in intents])
    approved = np.array([r["review_status"] == "approved" for r in intents])
    supported = (
        np.array([r["attack_family"] in PAYLOAD_FAMILIES | {"benign"} for r in intents]) & approved
    )
    results = {}
    for name, path in bundles.items():
        pipeline = InferencePipeline(path, max_threads=4)
        first = pipeline.observe(rows[0], include_features=True)
        first_vector = np.array([first["feature_vector"]], np.float32)
        scores = np.array(
            [first["score"]] + [pipeline.observe(r)["score"] for r in rows[1:]], np.float32
        )
        threshold = pipeline.manifest["threshold"]
        families = {}
        for family in sorted({r["attack_family"] for r in intents}):
            mask = np.array([r["attack_family"] == family for r in intents])
            families[family] = {
                "requests": int(mask.sum()),
                "flagged": int(np.sum(scores[mask] >= threshold)),
            }
        results[name] = {
            "bundle_manifest_sha256": file_sha256(Path(path) / "model_manifest.json"),
            "approved_all_family_task": binary_metrics(y[approved], scores[approved], threshold),
            "common_request_payload_task": binary_metrics(
                y[supported], scores[supported], threshold
            ),
            "all_intent_diagnostic": binary_metrics(y, scores, threshold),
            "binary_detection_by_intent_family": families,
            "threshold_tuned_on_fresh_cohort": False,
            "latency_ms": {
                "scope": "warm batch1 ONNX model only, feature extraction excluded",
                **latency_ms(
                    lambda x: pipeline.session.run(None, {"input": x}), first_vector, repeats=100
                ),
            },
        }
    result = {
        "requests": len(rows),
        "collected_sha256": manifest["dataset_sha256"],
        "three_source_correlated_requests": sum(
            {"STUDENT_AUDIT", "NGINX", "SURICATA"} <= set(r["sources"]) for r in rows
        ),
        "flow_present_requests": sum(
            has_flow_observation(json.loads(r["flow_json"])) for r in rows
        ),
        "approved_rows": int(approved.sum()),
        "pending_rows": int((~approved).sum()),
        "models": results,
        "canonical_profile": "safe_query_numeric_v2; fused chronological207-featurev5 unchanged",
        "champion_selected": False,
        "original_final_test_quality_opened": False,
        "limits": [
            "New time and grammars, same isolated fixture and runner-intent labels",
            "No threshold/config selection uses this cohort; public/new request branch has a different observation/task scope",
            "Completed-flow context stays causal; live receipt-time acceptance is not established",
        ],
    }
    atomic_json(output, result)
    return result

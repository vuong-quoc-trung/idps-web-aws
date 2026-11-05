#!/usr/bin/env python3
"""Frozen, offline Juice Shop smoke evaluation of an existing WAF request model.

The WAF target is publisher NORMAL/ANOMALOUS. Juice labels are separate lab
evidence; this script never interprets a WAF anomaly score as ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.common import (
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content import rich_request
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.resources import resource_envelope

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / ".artifacts"
JUICE = ART / "juice_gt_factory_20261104"
WAF = ART / "autonomous_content_intelligence_20261104"
SOURCE_FILES = {
    "juice_plan": JUICE / "plan.json",
    "juice_run": JUICE / "run/report.json",
    "juice_curation": JUICE / "curated/report.json",
    "juice_curator_v1": JUICE / "curator-source-v1.py",
    "juice_factory_code": ROOT / "scripts/juice-gt-factory.py",
    "waf_curation": WAF / "waf-rich-v1/report.json",
    "waf_tensor": WAF / "waf-rich-v1/rich-content.npz",
    "waf_study_plan": WAF / "study-plan-v1.json",
    "waf_study_report": WAF / "study-v1/report.json",
    "encoder": ROOT / "src/idps_ai/features/rich_content.py",
    "numeric_encoder": ROOT / "src/idps_ai/features/request_preprocessing.py",
}
CHECKPOINT = WAF / "study-v1/content_mlp"


def _verified_json(path):
    value = load_json(path)
    field = "report_sha256" if "report_sha256" in value else "plan_sha256"
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise PipelineError(f"Artifact self-hash mismatch: {path}")
    return value


def _factory():
    source = SOURCE_FILES["juice_factory_code"]
    spec = importlib.util.spec_from_file_location("frozen_juice_factory", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs():
    juice_plan = _verified_json(SOURCE_FILES["juice_plan"])
    juice_run = _verified_json(SOURCE_FILES["juice_run"])
    juice_curation = _verified_json(SOURCE_FILES["juice_curation"])
    waf_curation = _verified_json(SOURCE_FILES["waf_curation"])
    waf_study_plan = _verified_json(SOURCE_FILES["waf_study_plan"])
    waf_study_report = _verified_json(SOURCE_FILES["waf_study_report"])
    if (
        juice_run["plan_file_sha256"] != file_sha256(SOURCE_FILES["juice_plan"])
        or juice_plan["script_sha256"] != file_sha256(SOURCE_FILES["juice_factory_code"])
        or juice_run["script_sha256"] != juice_plan["script_sha256"]
        or juice_curation["plan_file_sha256"] != file_sha256(SOURCE_FILES["juice_plan"])
        or juice_curation["run_report_file_sha256"] != file_sha256(SOURCE_FILES["juice_run"])
        or juice_curation["curator_script_sha256"] != file_sha256(SOURCE_FILES["juice_curator_v1"])
        or "from idps_ai.features.rich_content import rich_request"
        not in SOURCE_FILES["juice_curator_v1"].read_text()
        or waf_curation["data_file_sha256"] != file_sha256(SOURCE_FILES["waf_tensor"])
        or waf_curation["rich_content_code_sha256"] != file_sha256(SOURCE_FILES["encoder"])
        or waf_curation["numeric_spec_sha256"] != digest(bounded_spec())
        or waf_study_plan["dataset_sha256"] != file_sha256(SOURCE_FILES["waf_tensor"])
        or waf_study_report["plan_sha256"] != waf_study_plan["plan_sha256"]
        or waf_study_report["arms"]["content_mlp"]["input_features"] != 588
    ):
        raise PipelineError("Juice/WAF provenance or feature contract mismatch")
    loaded = load_checkpoint(CHECKPOINT)
    arm = waf_study_report["arms"]["content_mlp"]
    if (
        loaded.used_previous
        or file_sha256(loaded.path / "manifest.json") != arm["checkpoint_manifest_sha256"]
        or loaded.state["plan_sha256"] != waf_study_plan["plan_sha256"]
        or loaded.state["source_role"] != "train"
        or loaded.state["validation_or_test_rows_used_for_fitting"] != 0
        or loaded.model.input_dim != 588
        or loaded.model.steps != 300
        or loaded.model.objective
        != {"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0}
    ):
        raise PipelineError("Frozen WAF checkpoint contract mismatch")
    threshold = float(arm["threshold"])
    if not np.isfinite(threshold) or arm["threshold_source"] != (
        "calibration publisher-normal 99th percentile, strict greater than"
    ):
        raise PipelineError("WAF operating rule was not frozen on calibration")
    return juice_plan, juice_run, juice_curation, waf_curation, loaded, threshold


def _cohort(juice_plan, juice_run):
    observations = {row["request_id"]: row for row in juice_run["observations"]}
    receipts = {row["request_id"]: row for row in juice_run["proxy_receipts"]}
    if len(observations) != 33 or len(receipts) != 33 or len(juice_plan["cases"]) != 33:
        raise PipelineError("Juice request IDs are missing or duplicated")
    factory = _factory()
    spec = bounded_spec()
    records, texts, numeric, availability = [], [], [], Counter()
    for case in juice_plan["cases"]:
        rid = case["request_id"]
        obs, receipt = observations.get(rid), receipts.get(rid)
        if not obs or not receipt or obs["case_id"] != case["case_id"]:
            raise PipelineError("Juice case identity mismatch")
        body = factory._body(case["body_profile"]) if case["body_profile"] else b""
        if any(
            (
                hashlib.sha256(body).hexdigest() != case["body_sha256"],
                receipt["method"] != case["method"],
                receipt["path_sha256"] != hashlib.sha256(case["path"].encode()).hexdigest(),
                receipt["body_sha256"] != case["body_sha256"],
                receipt["response_sha256"] != obs["response_sha256"],
                receipt["status"] != obs["status"],
            )
        ):
            raise PipelineError("Juice proxy/response evidence mismatch")
        tier = obs["ground_truth_tier"]
        if tier not in ("BENIGN_WORKFLOW_VERIFIED", "ATTACK_ATTEMPT_VERIFIED", "UNKNOWN"):
            raise PipelineError("Unsupported Juice evidence tier")
        if tier == "BENIGN_WORKFLOW_VERIFIED" and (
            case["intended_class"] != "benign" or not obs["application_semantic_ok"]
        ):
            raise PipelineError("Benign semantic Oracle contradiction")
        if tier == "ATTACK_ATTEMPT_VERIFIED" and case["intended_class"] != "attack":
            raise PipelineError("Attack receipt/intent contradiction")
        if obs["exploit_success_verified"] and (
            tier != "ATTACK_ATTEMPT_VERIFIED"
            or case["oracle"] != "login_admin_challenge_transition"
            or juice_run["before_challenge"]["solved"]
            or not juice_run["after_challenge"]["solved"]
            or not obs["admin_identity_returned"]
        ):
            raise PipelineError("Exploit-success Oracle contradiction")
        values = encode_request(spec, project_request(case["path"], case["method"])["numbers"])
        symbolic, observed = rich_request(
            case["method"], case["path"], None, body.decode() if body else None
        )
        numeric.append(values)
        texts.append(symbolic)
        availability.update(observed)
        records.append(
            {
                "case_id": case["case_id"],
                "request_id": rid,
                "family": case["scenario_family"],
                "tier": tier,
                "exploit_success_verified": bool(obs["exploit_success_verified"]),
            }
        )
    content = (
        HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )
        .transform(texts)
        .toarray()
        .astype(np.float32)
    )
    vectors = np.concatenate((np.asarray(numeric, np.float32), content), axis=1)
    views = [hashlib.sha256(row.tobytes()).hexdigest() for row in vectors]
    if not np.isfinite(vectors).all():
        raise PipelineError("Nonfinite request views")
    return records, vectors, views, dict(availability)


def prepare(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise PipelineError("Smoke evaluation plan already exists")
    juice_plan, juice_run, juice_curation, _, loaded, threshold = _inputs()
    records, _, views, availability = _cohort(juice_plan, juice_run)
    classes = defaultdict(set)
    for record, view in zip(records, views, strict=True):
        if record["tier"] != "UNKNOWN":
            classes[view].add(record["tier"])
    mixed = {view for view, labels in classes.items() if len(labels) > 1}
    if (
        len(classes) != juice_curation["unique_numeric76_content512_views_before_quarantine"]
        or len(mixed) != juice_curation["mixed_label_feature_views"]
        or sum(r["tier"] == "UNKNOWN" for r in records) != 1
        or sum(r["tier"] == "ATTACK_ATTEMPT_VERIFIED" for r in records) != 4
        or sum(r["exploit_success_verified"] for r in records) != 1
    ):
        raise PipelineError("Juice label/view inventory differs from frozen curation")
    with np.load(SOURCE_FILES["waf_tensor"], allow_pickle=False) as data:
        waf_train_views = set(data["view"][data["role"] == 0].astype(str))
    plan = {
        "format_version": 1,
        "scope": "single-application historical lab attack smoke; not independent recall",
        "model_task": "WAF publisher NORMAL/ANOMALOUS; positive score means anomalous candidate",
        "juice_labels": "28 benign workflow, 4 collector-controlled attack attempts, 1 unknown; exploit-success subset",
        "files_sha256": {key: file_sha256(path) for key, path in SOURCE_FILES.items()},
        "evaluator_sha256": file_sha256(__file__),
        "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
        "threshold": threshold,
        "operating_rule": "score > frozen WAF publisher-normal calibration p99",
        "metrics": "request and unique-view; UNKNOWN excluded; mixed-label views flagged separately",
        "juice_unique_views": len(set(views)),
        "juice_mixed_label_views": len(mixed),
        "juice_views_overlapping_waf_train": sum(view in waf_train_views for view in views),
        "header_values_observed": False,
        "content_availability": availability,
        "no_threshold_or_model_selection_on_juice": True,
        "no_network_or_new_requests": True,
    }
    plan["plan_sha256"] = digest(plan)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, plan)
    output.chmod(0o600)
    return plan


def run(plan_path, output):
    plan_path, output = Path(plan_path), Path(output)
    if output.exists() or output.is_symlink():
        raise PipelineError("Smoke evaluation report already exists")
    plan = _verified_json(plan_path)
    if (
        plan["evaluator_sha256"] != file_sha256(__file__)
        or plan["files_sha256"] != {key: file_sha256(path) for key, path in SOURCE_FILES.items()}
        or plan["operating_rule"] != "score > frozen WAF publisher-normal calibration p99"
    ):
        raise PipelineError("Frozen smoke plan or inputs changed")
    juice_plan, juice_run, _, _, loaded, threshold = _inputs()
    if (
        plan["checkpoint_manifest_sha256"] != file_sha256(loaded.path / "manifest.json")
        or plan["threshold"] != threshold
    ):
        raise PipelineError("Checkpoint or threshold changed after plan freeze")
    records, vectors, views, availability = _cohort(juice_plan, juice_run)
    with np.load(SOURCE_FILES["waf_tensor"], allow_pickle=False) as data:
        waf_train_views = set(data["view"][data["role"] == 0].astype(str))
    if (
        plan["juice_unique_views"] != len(set(views))
        or plan["content_availability"] != availability
        or plan["juice_views_overlapping_waf_train"]
        != sum(view in waf_train_views for view in views)
    ):
        raise PipelineError("Feature overlap or availability changed after plan freeze")
    start = time.perf_counter()
    scores = loaded.model.predict(vectors)[0]
    elapsed_ms = 1000 * (time.perf_counter() - start)
    if scores.shape != (33,) or not np.isfinite(scores).all():
        raise PipelineError("Frozen model output is invalid")
    by_view = defaultdict(list)
    for i, view in enumerate(views):
        by_view[view].append(i)
    rows = []
    for i, record in enumerate(records):
        rows.append(
            record
            | {
                "view_sha256": views[i],
                "overlaps_waf_train_view": views[i] in waf_train_views,
                "same_view_request_count": len(by_view[views[i]]),
                "mixed_label_view": len(
                    {
                        records[j]["tier"]
                        for j in by_view[views[i]]
                        if records[j]["tier"] != "UNKNOWN"
                    }
                )
                > 1,
                "score": float(scores[i]),
                "flagged": bool(scores[i] > threshold),
            }
        )
    unique_rows = [rows[indices[0]] for indices in by_view.values()]

    def _group_summary(items, label):
        selected = [r for r in items if r["tier"] == label]
        return {
            "count": len(selected),
            "flagged": sum(r["flagged"] for r in selected),
            "score_min": min((r["score"] for r in selected), default=None),
            "score_median": float(np.median([r["score"] for r in selected])) if selected else None,
            "score_max": max((r["score"] for r in selected), default=None),
        }

    report = {
        "format_version": 1,
        "scope": plan["scope"],
        "plan_file_sha256": file_sha256(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "checkpoint_manifest_sha256": plan["checkpoint_manifest_sha256"],
        "threshold": threshold,
        "threshold_source": "WAF publisher-normal calibration, not Juice Shop",
        "model_task": plan["model_task"],
        "request_counts": {
            "benign": _group_summary(rows, "BENIGN_WORKFLOW_VERIFIED"),
            "attack_attempt": _group_summary(rows, "ATTACK_ATTEMPT_VERIFIED"),
            "unknown_excluded": _group_summary(rows, "UNKNOWN"),
        },
        "unique_view_counts": {
            "total": len(by_view),
            "benign_only": sum(
                any(r["tier"] == "BENIGN_WORKFLOW_VERIFIED" for r in (rows[i] for i in indices))
                and not any(
                    r["tier"] == "ATTACK_ATTEMPT_VERIFIED" for r in (rows[i] for i in indices)
                )
                for indices in by_view.values()
            ),
            "attack_only": sum(
                any(r["tier"] == "ATTACK_ATTEMPT_VERIFIED" for r in (rows[i] for i in indices))
                and not any(
                    r["tier"] == "BENIGN_WORKFLOW_VERIFIED" for r in (rows[i] for i in indices)
                )
                for indices in by_view.values()
            ),
            "mixed_label": sum(r["mixed_label_view"] for r in unique_rows),
            "flagged": sum(r["flagged"] for r in unique_rows),
        },
        "views_overlapping_waf_train": sum(view in waf_train_views for view in by_view),
        "content_availability": availability,
        "inference_latency_ms": {
            "scope": "model.predict batch33 only; feature construction excluded",
            "batch_total": elapsed_ms,
            "per_request_amortized": elapsed_ms / 33,
        },
        "rows": rows,
        "limits": [
            "One application/session, collector-controlled attack intent and tiny cohort; no generalization estimate",
            "WAF model predicts publisher ANOMALOUS, not independently verified malicious intent",
            "Juice headers were not persisted; header names/values missing at projection",
            "View collisions are reported, including mixed benign/attack; no feature values were invented",
            "No model, threshold or encoder was tuned on Juice Shop and no formal admission follows",
        ],
        "formal_admitted": 0,
    }
    report["report_sha256"] = digest(report)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    with resource_envelope(4, 8):
        result = prepare(args.plan) if args.mode == "prepare" else run(args.plan, args.output)
    print({"scope": result["scope"], "plan_sha256": result["plan_sha256"]})

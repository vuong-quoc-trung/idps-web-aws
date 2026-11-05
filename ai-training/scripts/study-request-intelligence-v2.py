#!/usr/bin/env python3
"""One WAF publisher-label v2 fit, frozen calibration, and historical regression."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import resource
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.metrics import average_precision_score

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model
from idps_ai.training.resources import resource_envelope

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / ".artifacts"
JUICE = ART / "juice_gt_factory_20261104"
SOURCE_CODE = (
    "src/idps_ai/features/rich_content.py",
    "src/idps_ai/features/rich_content_v2.py",
    "src/idps_ai/features/safe_content.py",
    "src/idps_ai/features/request_view.py",
    "src/idps_ai/features/request_preprocessing.py",
    "src/idps_ai/features/request_encoding.py",
    "src/idps_ai/training/models.py",
    "src/idps_ai/training/deep.py",
    "src/idps_ai/training/partial.py",
    "src/idps_ai/training/checkpoint.py",
    "scripts/curate-waf-rich-v2.py",
    "scripts/juice-gt-factory.py",
)
JUICE_FILES = {
    "plan": JUICE / "plan.json",
    "run": JUICE / "run/report.json",
    "curation": JUICE / "curated-v2/report.json",
    "tensor": JUICE / "curated-v2/lab-request-views.npz",
}
V1_REPORT = ART / "juice_request_smoke_20261104/final-report.json"


def _self_hash(path):
    value = load_json(path)
    field = "report_sha256" if "report_sha256" in value else "plan_sha256"
    if value.get(field) != digest({k: v for k, v in value.items() if k != field}):
        raise PipelineError(f"Self-hash mismatch: {path}")
    return value


def _code_hashes():
    return {name: file_sha256(ROOT / name) for name in SOURCE_CODE}


def _model(seed):
    return Model(
        588,
        64,
        "deep_mlp",
        seed=seed,
        objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
    )


def _corpus(dataset, report_path):
    report = _self_hash(report_path)
    if (
        report.get("encoder_version") != "rich_content_v2"
        or report["data_file_sha256"] != file_sha256(dataset)
        or report["rich_content_code_sha256"]
        != file_sha256(ROOT / "src/idps_ai/features/rich_content_v2.py")
        or report["numeric_spec_sha256"] != digest(bounded_spec())
        or report["input_sha256"]["train"]
        != file_sha256(ART / "autonomous_research_20261104/waf_v2/train.parquet")
        or report["symbolic_template_cross_role_overlap"] != 0
        or report["prior_safe_symbolic_template_overlap"] != 0
    ):
        raise PipelineError("WAF v2 curation provenance/contract mismatch")
    with np.load(dataset, allow_pickle=False) as data:
        numeric = data["numeric"].copy()
        content = data["content"].copy()
        labels = data["label"].copy()
        role = data["role"].copy()
        group = data["group"].copy()
        views = data["view"].copy()
    count = len(labels)
    if (
        numeric.shape != (count, 76)
        or content.shape != (count, 512)
        or count != report["selected_unique_numeric_content_views"]
        or not np.isfinite(numeric).all()
        or not np.isfinite(content).all()
        or not np.isin(labels, [0, 1]).all()
        or not np.isin(role, [0, 1, 2]).all()
        or len(set(views)) != count
    ):
        raise PipelineError("WAF v2 feature collision or tensor contract failure")
    for a, b in ((0, 1), (0, 2), (1, 2)):
        if set(group[role == a]) & set(group[role == b]):
            raise PipelineError("WAF v2 template group crosses roles")
    for partition in (0, 1, 2):
        if min(np.bincount(labels[role == partition], minlength=2)) < 100:
            raise PipelineError("WAF v2 role lacks publisher-label coverage")
    return np.concatenate((numeric, content), axis=1), labels, role, views, report


def _juice_views():
    plan = _self_hash(JUICE_FILES["plan"])
    run = _self_hash(JUICE_FILES["run"])
    curated = _self_hash(JUICE_FILES["curation"])
    if (
        run["plan_file_sha256"] != file_sha256(JUICE_FILES["plan"])
        or plan["script_sha256"] != file_sha256(ROOT / "scripts/juice-gt-factory.py")
        or curated["run_report_file_sha256"] != file_sha256(JUICE_FILES["run"])
        or curated["tensor_sha256"] != file_sha256(JUICE_FILES["tensor"])
        or curated["encoder_version"] != "rich_v2"
        or curated["encoder_code_sha256"]
        != file_sha256(ROOT / "src/idps_ai/features/rich_content_v2.py")
    ):
        raise PipelineError("Juice evidence or v2 encoder binding mismatch")
    factory_path = ROOT / "scripts/juice-gt-factory.py"
    spec = importlib.util.spec_from_file_location("frozen_juice_factory", factory_path)
    factory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(factory)
    observations = {x["request_id"]: x for x in run["observations"]}
    receipts = {x["request_id"]: x for x in run["proxy_receipts"]}
    if len(observations) != 33 or len(receipts) != 33 or len(plan["cases"]) != 33:
        raise PipelineError("Juice request identity coverage mismatch")
    records, numeric, symbols = [], [], []
    for case in plan["cases"]:
        obs = observations.get(case["request_id"])
        receipt = receipts.get(case["request_id"])
        body = factory._body(case["body_profile"]) if case["body_profile"] else b""
        if (
            obs is None
            or receipt is None
            or obs["case_id"] != case["case_id"]
            or receipt["method"] != case["method"]
            or receipt["path_sha256"] != hashlib.sha256(case["path"].encode()).hexdigest()
            or receipt["body_sha256"] != case["body_sha256"]
            or hashlib.sha256(body).hexdigest() != case["body_sha256"]
            or receipt["response_sha256"] != obs["response_sha256"]
            or receipt["status"] != obs["status"]
        ):
            raise PipelineError("Juice case/proxy/application evidence mismatch")
        tier = obs["ground_truth_tier"]
        if tier not in ("BENIGN_WORKFLOW_VERIFIED", "ATTACK_ATTEMPT_VERIFIED", "UNKNOWN"):
            raise PipelineError("Juice ground-truth tier changed")
        if tier == "BENIGN_WORKFLOW_VERIFIED" and not obs["application_semantic_ok"]:
            raise PipelineError("Juice benign semantic Oracle mismatch")
        if obs["exploit_success_verified"] and (
            tier != "ATTACK_ATTEMPT_VERIFIED"
            or not obs["admin_identity_returned"]
            or run["before_challenge"]["solved"]
            or not run["after_challenge"]["solved"]
        ):
            raise PipelineError("Juice exploit-success Oracle mismatch")
        numeric.append(
            encode_request(bounded_spec(), project_request(case["path"], case["method"])["numbers"])
        )
        symbols.append(
            rich_request_v2(case["method"], case["path"], None, body.decode() if body else None)[0]
        )
        records.append(
            {
                "case_id": case["case_id"],
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
        .transform(symbols)
        .toarray()
        .astype(np.float32)
    )
    values = np.concatenate((np.asarray(numeric, np.float32), content), axis=1)
    view = [hashlib.sha256(x.tobytes()).hexdigest() for x in values]
    grouped = defaultdict(set)
    for item, key in zip(records, view, strict=True):
        if item["tier"] != "UNKNOWN":
            grouped[key].add(item["tier"])
    with np.load(JUICE_FILES["tensor"], allow_pickle=False) as data:
        curated_views = set(data["view"].astype(str))
    if (
        len(grouped) != 21
        or any(len(classes) != 1 for classes in grouped.values())
        or set(grouped) != curated_views
        or sum(x["tier"] == "BENIGN_WORKFLOW_VERIFIED" for x in records) != 28
        or sum(x["tier"] == "ATTACK_ATTEMPT_VERIFIED" for x in records) != 4
        or sum(x["tier"] == "UNKNOWN" for x in records) != 1
        or sum(x["exploit_success_verified"] for x in records) != 1
    ):
        raise PipelineError("Juice v2 collision/label contract differs from curated evidence")
    return records, values, view


def prepare(dataset, curation_report, plan_path, run_dir):
    plan_path = Path(plan_path)
    run_dir = Path(run_dir)
    if plan_path.exists() or run_dir.exists():
        raise PipelineError("V2 frozen plan or output already exists")
    x, label, role, views, curated = _corpus(Path(dataset), Path(curation_report))
    juice_records, _, juice_views = _juice_views()
    train_views = set(views[role == 0].astype(str))
    model = _model(31)
    coverage = {
        name: {
            "normal": int(np.sum((role == idx) & (label == 0))),
            "anomalous": int(np.sum((role == idx) & (label == 1))),
        }
        for idx, name in enumerate(("train", "calibration", "development_evaluation"))
    }
    plan = {
        "format_version": 1,
        "scope": "one WAF train-split publisher-label v2 research fit; Juice historical regression only",
        "dataset": str(Path(dataset).resolve()),
        "dataset_sha256": file_sha256(dataset),
        "curation_report": str(Path(curation_report).resolve()),
        "curation_report_sha256": file_sha256(curation_report),
        "encoder_version": "rich_content_v2",
        "feature_contract": "bounded-request-v1 numeric76 + HashingVectorizer char 3-5 512 nonnegative L2 float32",
        "feature_count": int(x.shape[1]),
        "unique_views": len(views),
        "publisher_label_coverage": coverage,
        "model": "deep_mlp hidden64 partial_binary_v1 smoothing0.005 family_weight0",
        "parameters": sum(v.size for v in model.parameters.values()),
        "optimizer": "adamw-v1; existing Model.train_batch contract",
        "learning_rate": 0.001,
        "batch_size": 256,
        "updates": 3072,
        "checkpoint_at": 1536,
        "seed": 31,
        "calibration": "role1 publisher-NORMAL score p99 higher; alert strictly score > threshold",
        "development_evaluation": "role2 once after threshold freeze; publisher labels only",
        "baseline": "frozen rich-v1 Juice scores only; no Juice-based model/threshold selection",
        "run_dir": str(run_dir.resolve()),
        "code_sha256": _code_hashes(),
        "script_sha256": file_sha256(__file__),
        "juice_files_sha256": {name: file_sha256(path) for name, path in JUICE_FILES.items()},
        "v1_report_sha256": file_sha256(V1_REPORT),
        "juice_labeled_unique_v2_views": len(
            set(juice_views[i] for i, r in enumerate(juice_records) if r["tier"] != "UNKNOWN")
        ),
        "juice_views_overlapping_waf_train": sum(v in train_views for v in juice_views),
        "max_cpus": 4,
        "max_memory_gib": 16,
        "no_sealed_holdout": True,
        "formal_admitted": 0,
        "curation_near_duplicate_probe": curated["near_duplicate_cross_role_probe"],
    }
    if plan["parameters"] != 50_696 or plan["juice_labeled_unique_v2_views"] != 21:
        raise PipelineError("V2 architecture or Juice encoder contract changed")
    plan["plan_sha256"] = digest(plan)
    plan_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(plan_path, plan)
    plan_path.chmod(0o600)
    return plan


def _frozen(plan_path):
    plan = _self_hash(plan_path)
    if (
        plan["script_sha256"] != file_sha256(__file__)
        or plan["code_sha256"] != _code_hashes()
        or plan["dataset_sha256"] != file_sha256(plan["dataset"])
        or plan["curation_report_sha256"] != file_sha256(plan["curation_report"])
        or plan["juice_files_sha256"]
        != {name: file_sha256(path) for name, path in JUICE_FILES.items()}
        or plan["v1_report_sha256"] != file_sha256(V1_REPORT)
        or plan["updates"] != 3072
        or plan["checkpoint_at"] != 1536
        or plan["batch_size"] != 256
        or plan["feature_count"] != 588
        or plan["parameters"] != 50_696
    ):
        raise PipelineError("Frozen v2 plan or input changed")
    x, label, role, views, _ = _corpus(Path(plan["dataset"]), Path(plan["curation_report"]))
    if len(views) != plan["unique_views"]:
        raise PipelineError("V2 plan view count changed")
    return plan, x, label, role, views


def _score(model, x):
    return np.concatenate([model.predict(x[i : i + 4096])[0] for i in range(0, len(x), 4096)])


def fit(plan_path):
    plan, x, label, role, _ = _frozen(plan_path)
    root = Path(plan["run_dir"])
    if root.exists():
        raise PipelineError("V2 training output already exists")
    root.mkdir(parents=True, mode=0o700)
    model = _model(plan["seed"])
    train = np.flatnonzero(role == 0)
    rng = np.random.default_rng(plan["seed"])
    order = rng.permutation(train)
    cursor = 0
    losses = []
    start = time.monotonic()
    checkpoint_readback_exact = False
    for update in range(1, plan["updates"] + 1):
        if cursor + plan["batch_size"] > len(order):
            order = rng.permutation(train)
            cursor = 0
        batch = order[cursor : cursor + plan["batch_size"]]
        cursor += plan["batch_size"]
        loss = model.train_batch(
            x[batch],
            np.full(len(batch), -1, np.int64),
            plan["learning_rate"],
            binary_targets=label[batch],
        )
        if not np.isfinite(loss) or update != model.steps:
            raise PipelineError("V2 nonfinite loss or optimizer step mismatch")
        losses.append(float(loss))
        if update == plan["checkpoint_at"]:
            saved = save_checkpoint(
                root / "model",
                model,
                {
                    "plan_sha256": plan["plan_sha256"],
                    "source_role": "train",
                    "sampler_cursor": cursor,
                    "rng_state": rng.bit_generator.state,
                    "calibration_or_evaluation_rows_used_for_fitting": 0,
                },
                order.astype(np.int64),
            )
            loaded = load_checkpoint(root / "model")
            checkpoint_readback_exact = (
                loaded.path == saved
                and loaded.model.steps == update
                and np.array_equal(loaded.permutation, order)
                and all(
                    np.array_equal(model.arrays()[key], loaded.model.arrays()[key])
                    for key in model.arrays()
                )
            )
            if not checkpoint_readback_exact:
                raise PipelineError("V2 midpoint checkpoint roundtrip mismatch")
            model = loaded.model
            order = loaded.permutation
            cursor = loaded.state["sampler_cursor"]
            rng.bit_generator.state = loaded.state["rng_state"]
    final_path = save_checkpoint(
        root / "model",
        model,
        {
            "plan_sha256": plan["plan_sha256"],
            "source_role": "train",
            "sampler_cursor": cursor,
            "rng_state": rng.bit_generator.state,
            "calibration_or_evaluation_rows_used_for_fitting": 0,
        },
        order.astype(np.int64),
    )
    loaded = load_checkpoint(root / "model")
    if (
        loaded.path != final_path
        or loaded.model.steps != plan["updates"]
        or not all(
            np.array_equal(model.arrays()[key], loaded.model.arrays()[key])
            for key in model.arrays()
        )
        or not all(np.isfinite(array).all() for array in model.arrays().values())
    ):
        raise PipelineError("V2 final checkpoint/optimizer state mismatch")
    report = {
        "format_version": 1,
        "scope": plan["scope"],
        "plan_sha256": plan["plan_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "unique_views": len(label),
        "train_rows": len(train),
        "updates": model.steps,
        "effective_epochs": model.steps * plan["batch_size"] / len(train),
        "parameters": plan["parameters"],
        "first_100_loss_mean": float(np.mean(losses[:100])),
        "last_100_loss_mean": float(np.mean(losses[-100:])),
        "loss_min": float(np.min(losses)),
        "loss_max": float(np.max(losses)),
        "fit_seconds": time.monotonic() - start,
        "midpoint_checkpoint_exact_roundtrip": checkpoint_readback_exact,
        "resumed_from_midpoint": True,
        "final_checkpoint_manifest_sha256": file_sha256(final_path / "manifest.json"),
        "final_checkpoint_path": str(final_path),
        "calibration_or_evaluation_rows_used_for_fitting": 0,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "formal_admitted": 0,
    }
    report["report_sha256"] = digest(report)
    atomic_json(root / "fit-report.json", report)
    (root / "fit-report.json").chmod(0o600)
    return report


def _fitted(plan_path):
    plan, x, label, role, views = _frozen(plan_path)
    root = Path(plan["run_dir"])
    fit_report = _self_hash(root / "fit-report.json")
    loaded = load_checkpoint(root / "model")
    if (
        fit_report["plan_sha256"] != plan["plan_sha256"]
        or fit_report["final_checkpoint_manifest_sha256"]
        != file_sha256(loaded.path / "manifest.json")
        or loaded.state["plan_sha256"] != plan["plan_sha256"]
        or loaded.state["calibration_or_evaluation_rows_used_for_fitting"] != 0
        or loaded.model.steps != plan["updates"]
        or loaded.model.input_dim != 588
        or sum(v.size for v in loaded.model.parameters.values()) != plan["parameters"]
    ):
        raise PipelineError("V2 fitted checkpoint or plan integrity mismatch")
    return plan, x, label, role, views, fit_report, loaded


def calibrate(plan_path):
    plan, x, label, role, _, fit_report, loaded = _fitted(plan_path)
    root = Path(plan["run_dir"])
    destination = root / "threshold-manifest.json"
    if destination.exists():
        raise PipelineError("V2 threshold manifest already exists")
    normal = x[(role == 1) & (label == 0)]
    if len(normal) < 1000:
        raise PipelineError("V2 publisher-NORMAL calibration lacks coverage")
    scores = _score(loaded.model, normal)
    threshold = float(np.quantile(scores, 0.99, method="higher"))
    flagged = int(np.sum(scores > threshold))
    manifest = {
        "format_version": 1,
        "scope": "research publisher-NORMAL calibration only; not real benign FPR",
        "plan_sha256": plan["plan_sha256"],
        "fit_report_file_sha256": file_sha256(root / "fit-report.json"),
        "final_checkpoint_manifest_sha256": fit_report["final_checkpoint_manifest_sha256"],
        "dataset_sha256": plan["dataset_sha256"],
        "encoder_version": plan["encoder_version"],
        "selection": plan["calibration"],
        "normal_calibration_views": len(normal),
        "threshold": threshold,
        "calibration_normal_flagged": flagged,
        "calibration_normal_empirical_fraction": flagged / len(normal),
        "uncertainty": "Threshold selected on these publisher labels; source/template dependence and sampled cross-role near duplicates prevent an independent real-world FPR confidence interval.",
        "no_juice_or_development_scores_used": True,
        "formal_admitted": 0,
    }
    if not np.isfinite(threshold):
        raise PipelineError("V2 calibration produced a nonfinite threshold")
    manifest["manifest_sha256"] = digest(manifest)
    atomic_json(destination, manifest)
    destination.chmod(0o600)
    return manifest


def _publisher_metrics(labels, scores, threshold):
    flagged = scores > threshold
    anomalous = labels == 1
    normal = labels == 0
    tp = int(np.sum(flagged & anomalous))
    fp = int(np.sum(flagged & normal))
    return {
        "publisher_normal_views": int(np.sum(normal)),
        "publisher_anomalous_views": int(np.sum(anomalous)),
        "publisher_anomalous_flagged": tp,
        "publisher_normal_flagged": fp,
        "publisher_anomalous_fraction_flagged": tp / max(int(np.sum(anomalous)), 1),
        "publisher_normal_fraction_flagged": fp / max(int(np.sum(normal)), 1),
        "publisher_pr_auc": float(average_precision_score(labels, scores)),
        "scope": "same-source development publisher labels; not verified attack Recall/FPR",
    }


def evaluate(plan_path):
    plan, x, label, role, train_views, _, loaded = _fitted(plan_path)
    root = Path(plan["run_dir"])
    output = root / "evaluation-report.json"
    if output.exists():
        raise PipelineError("V2 historical regression already exists")
    manifest_path = root / "threshold-manifest.json"
    manifest = load_json(manifest_path)
    if (
        manifest.get("manifest_sha256")
        != digest({k: v for k, v in manifest.items() if k != "manifest_sha256"})
        or manifest["plan_sha256"] != plan["plan_sha256"]
        or manifest["final_checkpoint_manifest_sha256"]
        != file_sha256(loaded.path / "manifest.json")
        or manifest["selection"] != plan["calibration"]
        or not manifest["no_juice_or_development_scores_used"]
    ):
        raise PipelineError("V2 threshold was not frozen before evaluation")
    threshold = float(manifest["threshold"])
    if not np.isfinite(threshold):
        raise PipelineError("Invalid V2 threshold")
    # The role-2 result is development only: one WAF publisher and sampled
    # near-template overlap across roles, not a new independent blind cohort.
    dev = role == 2
    dev_scores = _score(loaded.model, x[dev])
    dev_result = _publisher_metrics(label[dev], dev_scores, threshold)

    records, juice_values, juice_views = _juice_views()
    train_view_set = set(train_views[role == 0].astype(str))
    if (
        sum(view in train_view_set for view in juice_views)
        != plan["juice_views_overlapping_waf_train"]
    ):
        raise PipelineError("Juice/WAF exact view overlap changed after plan freeze")
    started = time.perf_counter()
    juice_scores = loaded.model.predict(juice_values)[0]
    model_ms = 1000 * (time.perf_counter() - started)
    if juice_scores.shape != (33,) or not np.isfinite(juice_scores).all():
        raise PipelineError("Invalid v2 Juice scores")
    v1 = _self_hash(V1_REPORT)
    v1_by_case = {row["case_id"]: row for row in v1["rows"]}
    if len(v1_by_case) != 33:
        raise PipelineError("Frozen v1 comparator is incomplete")
    rows = []
    for item, score, view in zip(records, juice_scores, juice_views, strict=True):
        old = v1_by_case[item["case_id"]]
        if (
            old["tier"] != item["tier"]
            or old["exploit_success_verified"] != item["exploit_success_verified"]
        ):
            raise PipelineError("V1/V2 Juice evidence label mismatch")
        rows.append(
            item
            | {
                "view_sha256": view,
                "overlaps_waf_v2_train_view": view in train_view_set,
                "v1_score": old["score"],
                "v1_flagged": old["flagged"],
                "v2_score": float(score),
                "v2_flagged": bool(score > threshold),
            }
        )
    unique = defaultdict(list)
    for item in rows:
        unique[item["view_sha256"]].append(item)
    mixed = sum(
        len({r["tier"] for r in group if r["tier"] != "UNKNOWN"}) > 1 for group in unique.values()
    )
    if mixed != 0:
        raise PipelineError("V2 Juice mixed-label collision unexpectedly reappeared")

    def _class_summary(items, tier):
        chosen = [r for r in items if r["tier"] == tier]
        return {
            "count": len(chosen),
            "v1_flagged": sum(r["v1_flagged"] for r in chosen),
            "v2_flagged": sum(r["v2_flagged"] for r in chosen),
            "v2_score_min": min((r["v2_score"] for r in chosen), default=None),
            "v2_score_median": float(np.median([r["v2_score"] for r in chosen]))
            if chosen
            else None,
            "v2_score_max": max((r["v2_score"] for r in chosen), default=None),
        }

    report = {
        "format_version": 1,
        "scope": "WAF same-source publisher development plus historical Juice Shop regression; no independent generalization",
        "plan_sha256": plan["plan_sha256"],
        "threshold_manifest_file_sha256": file_sha256(manifest_path),
        "final_checkpoint_manifest_sha256": manifest["final_checkpoint_manifest_sha256"],
        "v2_threshold": threshold,
        "v1_threshold": v1["threshold"],
        "waf_development_publisher_metrics": dev_result,
        "juice_request_counts": {
            "benign": _class_summary(rows, "BENIGN_WORKFLOW_VERIFIED"),
            "attack_attempt": _class_summary(rows, "ATTACK_ATTEMPT_VERIFIED"),
            "unknown_excluded": _class_summary(rows, "UNKNOWN"),
        },
        "juice_unique_v2_views_including_unknown": len(unique),
        "juice_mixed_label_v2_views": mixed,
        "juice_exact_views_overlapping_waf_train": sum(v in train_view_set for v in unique),
        "juice_model_only_batch33_ms": model_ms,
        "rows": rows,
        "interpretation": "v1 and v2 use the same historical Juice evidence, but different WAF train cohorts and separate publisher calibration. Their score scales are not directly comparable. Regression is exposed, tiny, single-app, collector-controlled; no independent Recall/FPR, champion, or formal admission.",
        "formal_admitted": 0,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    report["report_sha256"] = digest(report)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "fit", "calibrate", "evaluate"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--dataset")
    parser.add_argument("--curation-report")
    parser.add_argument("--run-dir")
    args = parser.parse_args()
    with resource_envelope(4, 16):
        if args.mode == "prepare":
            if not (args.dataset and args.curation_report and args.run_dir):
                parser.error("prepare requires --dataset, --curation-report and --run-dir")
            result = prepare(args.dataset, args.curation_report, args.plan, args.run_dir)
        elif args.mode == "fit":
            result = fit(args.plan)
        elif args.mode == "calibrate":
            result = calibrate(args.plan)
        else:
            result = evaluate(args.plan)
    print({"mode": args.mode, "scope": result["scope"], "plan_sha256": result["plan_sha256"]})

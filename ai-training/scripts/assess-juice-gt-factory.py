#!/usr/bin/env python3
"""Focused quality gate for a single Juice Shop evidence cohort; no scoring."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.training.resources import resource_envelope


def assess(plan_path, run_path, curation_path, tensor_path, output):
    plan_path, run_path, curation_path, tensor_path, output = map(
        Path, (plan_path, run_path, curation_path, tensor_path, output)
    )
    if output.exists():
        raise PipelineError("Factory quality report exists")
    plan, run, curated = map(load_json, (plan_path, run_path, curation_path))
    for report, key in ((plan, "plan_sha256"), (run, "report_sha256"), (curated, "report_sha256")):
        if report.get(key) != digest({k: v for k, v in report.items() if k != key}):
            raise PipelineError("Factory quality input self-hash mismatch")
    if (
        curated["plan_file_sha256"] != file_sha256(plan_path)
        or curated["run_report_file_sha256"] != file_sha256(run_path)
        or curated["tensor_sha256"] != file_sha256(tensor_path)
        or curated.get("encoder_version") != "rich_v2"
        or run["formal_admitted"] != 0
    ):
        raise PipelineError("Factory quality input lineage mismatch")
    with np.load(tensor_path, allow_pickle=False) as data:
        content, labels, views = data["content"], data["label"], data["view"]
    if (
        content.shape != (len(labels), 512)
        or len(set(views)) != len(views)
        or len(labels) != curated["research_candidate_views_after_quarantine"]
        or not np.isin(labels, [0, 1]).all()
        or not np.isfinite(content).all()
    ):
        raise PipelineError("Invalid Juice research tensor")
    similarities = cosine_similarity(content)
    np.fill_diagonal(similarities, -1)
    pairs = np.argwhere(np.triu(similarities, k=1) >= 0.995)
    routes = Counter()
    observation_by_case = {item["case_id"]: item for item in run["observations"]}
    for case in plan["cases"]:
        observed = observation_by_case[case["case_id"]]
        if observed["ground_truth_tier"] == "UNKNOWN":
            continue
        routes[(case["method"], case["path"].split("?", 1)[0], observed["ground_truth_tier"])] += 1
    benign = int(np.sum(labels == 0))
    report = {
        "format_version": 1,
        "scope": "Juice Shop single-application development cohort; no model score",
        "plan_file_sha256": file_sha256(plan_path),
        "run_report_file_sha256": file_sha256(run_path),
        "curation_file_sha256": file_sha256(curation_path),
        "tensor_sha256": file_sha256(tensor_path),
        "assessor_sha256": file_sha256(__file__),
        "campaign_requests": run["requests_sent"],
        "unique_complete_request_representations": run["unique_http_representations"],
        "unique_feature_views": len(labels),
        "benign_views": benign,
        "attack_attempt_views": int(np.sum(labels == 1)),
        "mixed_label_views": curated["mixed_label_feature_views"],
        "same_label_duplicate_view_rows": curated["quality_counts"][
            "same_label_view_duplicate_rows"
        ],
        "content_cosine_ge_0_995_pairs": len(pairs),
        "cross_label_content_cosine_ge_0_995_pairs": int(
            sum(labels[i] != labels[j] for i, j in pairs)
        ),
        "route_label_counts": {
            f"{method} {path} {label}": count for (method, path, label), count in routes.items()
        },
        "declared_campaign_ids": len({case["campaign_id"] for case in plan["cases"]}),
        "independent_applications": 1,
        "independent_environments": 0,
        "fpr_one_sided_95pct_upper_if_zero_fp": 1 - 0.05 ** (1 / benign),
        "feature_availability": "request-only 76+512; proxy did not persist header values; 207 fused features unavailable",
        "campaign_shortcut": "campaign IDs encode scenario intent and cannot be model features or independent evaluation groups here",
        "research_fit_ready": False,
        "research_eval_ready": False,
        "formal_ready": False,
        "formal_admitted": 0,
        "reason": "Only one app/run and four unique attack views, no valid train/calibration/evaluation split, and benign sample too small to support FPR 1%",
    }
    report["report_sha256"] = digest(report)
    atomic_json(output, report)
    output.chmod(0o600)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "run-report", "curation-report", "tensor", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    with resource_envelope(4, 8):
        result = assess(args.plan, args.run_report, args.curation_report, args.tensor, args.output)
    print(
        {
            "views": result["unique_feature_views"],
            "fit": result["research_fit_ready"],
            "eval": result["research_eval_ready"],
        }
    )

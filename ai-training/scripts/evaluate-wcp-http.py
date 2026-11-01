#!/usr/bin/env python3
"""Once-only frozen-model benign-domain stress test, never a recall/champion gate."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.data.http_curation import require_development_source
from idps_ai.features.request_preprocessing import encode_request
from idps_ai.features.request_view import fingerprint
from idps_ai.request_inference import RequestInferencePipeline
from idps_ai.training.evaluation import latency_ms
from idps_ai.training.generalization import grouped_binary_metrics
from idps_ai.training.resources import resource_envelope


def run(dataset, registry, output, cpus=4):
    dataset, output = Path(dataset), Path(output)
    require_development_source(dataset)
    source, plan = load_json(dataset / "manifest.json"), load_json(registry)
    if (
        source.get("source") != "openappsec_WCP_legitimate"
        or source.get("projection_sha256") != fingerprint()
        or output.exists()
    ):
        raise PipelineError("Explicit compatible source and new evaluation output required")
    if (
        plan.get("evaluate_role") != "validation"
        or not plan.get("reserved_websites_unopened")
        or not plan.get("no_HPO_or_new_training")
    ):
        raise PipelineError("Frozen external-validation protocol required")
    for f, sha in source["files"].items():
        if file_sha256(dataset / f) != sha:
            raise PipelineError("Public corpus shard integrity mismatch")
    rows = [
        r
        for r in iter_rows(dataset / "observations.parquet")
        if r["split"] == "validation" and r["projected"]
    ]
    if not rows or any(
        r["label"] != 0 or r["label_source"] != "publisher_legitimate_capture" for r in rows
    ):
        raise PipelineError("No eligible publisher-labeled benign validation projections")
    numbers = [json.loads(r["numeric_json"]) for r in rows]
    groups = [r["source_member_key"] for r in rows]
    novel = np.array([r["earliest_model_view_role"] == "validation" for r in rows])
    # Predefined syntax-only subset of publisher-benign observations, not new labels.
    hostile_syntax = np.array(
        [
            any(
                n[k] > 0
                for k in (
                    "sqli_keywords",
                    "xss_tokens",
                    "traversal_tokens",
                    "shell_and_count",
                    "shell_substitution_count",
                    "backtick_count",
                )
            )
            for n in numbers
        ]
    )
    output.mkdir(mode=0o700, parents=True)
    result = {
        "scope": "Benign-only external development stress test; publisher annotations, not independent human review or recall acceptance",
        "source_manifest_sha256": file_sha256(dataset / "manifest.json"),
        "registry_sha256": file_sha256(registry),
        "rows": len(rows),
        "website_case_groups": len(set(groups)),
        "reserved_members_opened": False,
        "new_training_or_threshold_fitting": False,
        "champion_selected": False,
        "models": {},
    }
    with resource_envelope(cpus, 16) as (guard, resources):
        for name, entry in plan["models"].items():
            bundle = Path(entry["bundle"])
            if (
                file_sha256(bundle / "model_manifest.json") != entry["manifest_sha256"]
                or file_sha256(bundle / "model.onnx") != entry["onnx_sha256"]
            ):
                raise PipelineError("Frozen evaluation model changed")
            pipe = RequestInferencePipeline(bundle, cpus)
            if pipe.manifest["threshold"] != entry["threshold"]:
                raise PipelineError("Frozen calibration threshold changed")
            x = np.asarray([encode_request(pipe.spec, n) for n in numbers], np.float32)
            values = []
            start = time.monotonic()
            for i in range(0, len(rows), 512):
                if guard.check() or guard.thermal_limit_reached or time.monotonic() - start > 300:
                    raise PipelineError("External evaluation resource/duration guard stopped")
                values.extend(
                    pipe.session.run(None, {"input": x[i : i + 512]})[0].reshape(-1).tolist()
                )
            scores = np.asarray(values)
            primary = grouped_binary_metrics(
                np.zeros(len(rows), int), scores, groups, entry["threshold"]
            )
            sensitivity = (
                grouped_binary_metrics(
                    np.zeros(int(novel.sum()), int),
                    scores[novel],
                    np.array(groups)[novel],
                    entry["threshold"],
                )
                if novel.any()
                else None
            )
            syntax_subset = (
                grouped_binary_metrics(
                    np.zeros(int(hostile_syntax.sum()), int),
                    scores[hostile_syntax],
                    np.array(groups)[hostile_syntax],
                    entry["threshold"],
                )
                if hostile_syntax.any()
                else None
            )
            for metrics in [primary, sensitivity, syntax_subset]:
                if metrics:
                    for key in ("precision", "recall", "f1", "pr_auc_average_precision"):
                        metrics["metrics"][key] = None
                    if metrics["cluster_bootstrap_95pct"]:
                        metrics["cluster_bootstrap_95pct"]["recall"] = None
                        metrics["cluster_bootstrap_95pct"]["precision"] = None
            result["models"][name] = {
                "primary_all_sampled_validation": primary,
                "novel_view_sensitivity_not_primary": sensitivity,
                "score_quantiles": dict(
                    zip(
                        ["min", "median", "p90", "p99", "max"],
                        np.quantile(scores, [0, 0.5, 0.9, 0.99, 1]).tolist(),
                    )
                ),
                "model_only_latency_ms": latency_ms(
                    lambda sample: pipe.session.run(None, {"input": sample}), x[:1], repeats=50
                ),
                "threshold_changed": False,
                "inference_rows": len(rows),
                "publisher_benign_syntax_subset": syntax_subset,
            }
            np.savez(output / (name + "-scores.npz"), scores=scores)
    result.update(status="PASS_FROZEN_BENIGN_STRESS_ONLY", resources=resources)
    atomic_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "registry", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--cpus", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.registry, args.output, args.cpus), sort_keys=True))

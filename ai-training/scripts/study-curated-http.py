#!/usr/bin/env python3
"""One preregistered, bounded multi-source development comparison; never open test."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.curated_split import audit_curated_partitions
from idps_ai.data.dataset import iter_rows
from idps_ai.data.request_corpus import verify_requests
from idps_ai.request_inference import RequestInferencePipeline
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.evaluation import latency_ms
from idps_ai.training.generalization import binary_metrics, calibration_audit
from idps_ai.training.request_training import benign_threshold, selected_training
from idps_ai.training.resources import resource_envelope
from idps_ai.training.runner import implementation_identity


def run(dataset, output, cpus=4, candidates=None):
    dataset, output = Path(dataset), Path(output)
    manifest = verify_requests(dataset)
    audit = audit_curated_partitions(dataset)
    if (
        not manifest.get("admission", {}).get("research_training_permitted")
        or audit["status"] != "PASS"
        or not audit["source_role_class_coverage"]
    ):
        raise PipelineError(
            "Curated study requires actual source-wise temporal and unique-view support"
        )
    if output.exists() or cpus not in (1, 2, 4, 8):
        raise PipelineError("Study requires a new output and at most8CPU")
    candidates = candidates or [
        ("mlp256", "deep_mlp", 256),
        ("glu256", "residual_glu", 256),
        ("glu1024", "residual_glu", 1024),
    ]
    if (
        not 1 <= len(candidates) <= 3
        or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]+", name)
            or kind not in ("deep_mlp", "residual_glu")
            or not 8 <= width <= 1024
            for name, kind, width in candidates
        )
        or len({name for name, _, _ in candidates}) != len(candidates)
    ):
        raise PipelineError("Invalid bounded candidate plan")
    output.mkdir(mode=0o700, parents=True)
    sources = sorted(manifest["admission"]["positive_training_sources"])
    plans = []
    for name, kind, width in candidates:
        plans.append(
            {
                "name": name,
                "config": dict(
                    kind=kind,
                    width=width,
                    seed=17,
                    learning_rate=0.0003,
                    total_steps=300,
                    warmup_steps=15,
                    training_pool="curated_multisource",
                    training_sources=sources,
                    sampling="domain_family_balanced",
                    family_weight=0.0,
                    smoothing=0.005,
                ),
            }
        )
    plan = {
        "dataset_sha256": manifest["dataset_sha256"],
        "source_sha256": implementation_identity(),
        "plans": plans,
        "steps_per_model": 300,
        "batch_size": 128,
        "threshold": "max per-source benign calibration quantile at1%FPR, never validation or test",
        "selection": "Report all candidates; validation only, no HPO, champion or final-test selection",
        "baseline": "LogisticRegression fixed C1,max_iter200,class/source/family training weights",
        "fresh_test_quality_opened": False,
        "limits": "SRBH day blocks, one recorded private source IP; publisher/runner annotations, no independent human review. Not a production generalization certificate.",
    }
    atomic_json(output / "preregistered-plan.json", plan)
    started = time.monotonic()

    def worker(argv, name):
        with (
            (output / (name + ".stdout.log")).open("w") as out,
            (output / (name + ".stderr.log")).open("w") as err,
        ):
            code = subprocess.run(
                [sys.executable, "-m", "idps_ai", *argv],
                stdout=out,
                stderr=err,
                timeout=300,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            ).returncode
        if code:
            raise PipelineError("Curated study worker failed; inspect private logs")
        return load_json(output / (name + ".stdout.log"))

    validation = [r for r in iter_rows(dataset / "features.parquet") if r["split"] == "val"]
    vx = np.asarray([r["x"] for r in validation], np.float32)
    vy = np.array([r["label"] for r in validation])

    def evaluate(scores, threshold):
        by_source = {}
        for source in sources:
            mask = np.array([r["source_id"] == source for r in validation])
            by_source[source] = {
                "metrics": binary_metrics(vy[mask], scores[mask], threshold),
                "score_calibration": calibration_audit(vy[mask], scores[mask]),
                "by_family": {
                    family: {
                        "requests": int(
                            sum(
                                r["source_id"] == source and r["attack_family"] == family
                                for r in validation
                            )
                        ),
                        "recall": float(
                            np.mean(
                                scores[
                                    np.array(
                                        [
                                            r["source_id"] == source
                                            and r["attack_family"] == family
                                            for r in validation
                                        ]
                                    )
                                ]
                                >= threshold
                            )
                        ),
                    }
                    for family in sorted(
                        {
                            r["attack_family"]
                            for r in validation
                            if r["source_id"] == source and r["label"] == 1
                        }
                    )
                },
            }
        return {
            "metrics": binary_metrics(vy, scores, threshold),
            "by_source": by_source,
            "empirical_each_source_FPR_at_most_1pct": all(
                v["metrics"]["fpr"] <= 0.01 for v in by_source.values()
            ),
            "threshold_changed_from_calibration": False,
        }

    results = {}
    for entry in plans:
        name, config = entry["name"], entry["config"]
        conf = output / (name + ".yaml")
        conf.write_text(yaml.safe_dump(config))
        args = [
            "request-train",
            "--dataset",
            str(dataset),
            "--config",
            str(conf),
            "--cpus",
            str(cpus),
            "--diagnostic-updates",
            "300",
        ]
        resumed, reference = output / (name + "-resumed"), output / (name + "-continuous")
        worker([*args, "--run-dir", str(resumed), "--max-steps", "100"], name + "-first")
        trained = worker([*args, "--run-dir", str(resumed), "--resume"], name + "-resume")
        control = worker([*args, "--run-dir", str(reference)], name + "-reference")
        a, b = load_checkpoint(resumed), load_checkpoint(reference)
        exact = (
            all(np.array_equal(v, b.model.arrays()[k]) for k, v in a.model.arrays().items())
            and np.array_equal(a.permutation, b.permutation)
            and all(
                a.state[k] == b.state[k]
                for k in ["rng", "cursor", "epoch", "history", "global_step"]
            )
        )
        if not exact or a.model.steps != 300:
            raise PipelineError("Curated exact resume/update budget failed")
        bundle = output / (name + "-bundle")
        card = worker(
            [
                "request-export",
                "--dataset",
                str(dataset),
                "--checkpoint",
                str(resumed),
                "--output",
                str(bundle),
                "--cpus",
                str(cpus),
            ],
            name + "-export",
        )
        with resource_envelope(cpus, 16):
            pipe = RequestInferencePipeline(bundle, cpus)
            scores = np.concatenate(
                [
                    pipe.session.run(None, {"input": vx[i : i + 512]})[0]
                    for i in range(0, len(vx), 512)
                ]
            ).reshape(-1)
            latency = latency_ms(
                lambda sample: pipe.session.run(None, {"input": sample}), vx[:1], repeats=50
            )
        results[name] = {
            "parameters": sum(v.size for v in a.model.parameters.values()),
            "bundle": str(bundle),
            "bundle_manifest_sha256": file_sha256(bundle / "model_manifest.json"),
            "threshold": card["threshold"],
            "validation": evaluate(scores, card["threshold"]),
            "exact_resume": exact,
            "parity": card["parity"],
            "model_only_latency_ms": latency,
            "training": trained,
            "reference_optimizer_seconds": control["optimizer_seconds"],
        }
        atomic_json(
            output / "progress.json", {"models": results, "fresh_test_quality_opened": False}
        )

    # A small fixed baseline uses exactly the same eligible unique input-view pool.
    from sklearn.linear_model import LogisticRegression

    with resource_envelope(cpus, 16):
        x, y, f, domains = selected_training(dataset, "deep_mlp", plans[0]["config"], True)
        weights = np.zeros(len(y), np.float64)
        for label in (0, 1):
            ds = np.unique(domains[y == label])
            for domain in ds:
                mask = (y == label) & (domains == domain)
                fs = np.unique(f[mask]) if label else [0]
                for family in fs:
                    m = mask & ((f == family) if label else True)
                    weights[m] = len(y) * 0.5 / (len(ds) * len(fs) * int(m.sum()))
        model = LogisticRegression(C=1.0, max_iter=200, random_state=17).fit(
            x, y, sample_weight=weights
        )
        cal = [
            r
            for r in iter_rows(dataset / "features.parquet")
            if r["split"] == "calibration" and r["label"] == 0
        ]
        cs = model.predict_proba(np.asarray([r["x"] for r in cal], np.float32))[:, 1]
        fitted = {
            s: benign_threshold([score for r, score in zip(cal, cs) if r["source_id"] == s])
            for s in sources
        }
        threshold = max(v["threshold"] for v in fitted.values())
        scores = model.predict_proba(vx)[:, 1]
        results["logistic"] = {
            "training_views": len(x),
            "parameters": model.coef_.size + model.intercept_.size,
            "threshold": threshold,
            "calibration": fitted,
            "validation": evaluate(scores, threshold),
            "model_only_latency_ms": latency_ms(model.predict_proba, vx[:1], repeats=50),
            "iterations": model.n_iter_.tolist(),
            "ONNX": "NOT_RUN classical control; not deployable bundle",
        }
        np.savez(
            output / "logistic-coefficients.npz",
            coefficient=model.coef_,
            intercept=model.intercept_,
            classes=model.classes_,
        )
    result = {
        "status": "PASS_TECHNICAL_DEVELOPMENT_ONLY",
        "plan_sha256": file_sha256(output / "preregistered-plan.json"),
        "wall_seconds": time.monotonic() - started,
        "dataset_sha256": manifest["dataset_sha256"],
        "models": results,
        "champion_selected": False,
        "formal_training": False,
        "fresh_test_quality_opened": False,
        "quality_limit": plan["limits"],
        "selection_performed": False,
    }
    atomic_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cpus", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(args.dataset, args.output, args.cpus), sort_keys=True))

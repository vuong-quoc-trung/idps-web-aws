#!/usr/bin/env python3
"""Bounded, preregistered validation-only request ablations. Never select a champion."""

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
from idps_ai.data.request_corpus import verify_requests
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.request_training import selected_training
from idps_ai.training.runner import implementation_identity


def run(raw_dataset, encoded_dataset, output, cpus=4, plan_file=None):
    output = Path(output).resolve()
    if output.exists():
        raise PipelineError("Ablation output must be new; never overwrite experiment evidence")
    encoded_key = (
        "bounded76"
        if verify_requests(encoded_dataset).get("encoding") == "bounded-request-v1"
        else "security45"
    )
    datasets = {
        "affine70": str(Path(raw_dataset).resolve()),
        encoded_key: str(Path(encoded_dataset).resolve()),
    }
    manifests = {name: verify_requests(path) for name, path in datasets.items()}
    if manifests["affine70"]["rows"] != manifests[encoded_key]["rows"]:
        raise PipelineError("Controlled encodings need the same physical observations and roles")
    pools = [
        selected_training(path, "deep_mlp", {"training_pool": "multisource_benign"}, True)
        for path in datasets.values()
    ]
    if any(not np.array_equal(a, b) for a, b in zip(pools[0][1:], pools[1][1:])):
        raise PipelineError("Encoding ablation altered labels/source order or sampling pool")
    output.mkdir(parents=True, mode=0o700)
    plans = []
    for encoding in datasets:
        for kind, width in [("deep_mlp", 256), ("residual_glu", 1024)]:
            for seed in [17, 29] if encoding == "security45" else [17]:
                plans.append(
                    dict(
                        name=f"{encoding}-{kind}-seed{seed}",
                        encoding=encoding,
                        config=dict(
                            kind=kind,
                            width=width,
                            seed=seed,
                            learning_rate=0.0003,
                            total_steps=300,
                            warmup_steps=15,
                            training_pool="multisource_benign",
                            sampling="source_family_balanced",
                            family_weight=0.2,
                        ),
                    )
                )
    plans.append(
        dict(
            name="security45-residual_glu256-seed17",
            encoding="security45",
            config=dict(
                kind="residual_glu",
                width=256,
                seed=17,
                learning_rate=0.0003,
                total_steps=300,
                warmup_steps=15,
                training_pool="multisource_benign",
                sampling="source_family_balanced",
                family_weight=0.2,
            ),
        )
    )
    if plan_file:
        plans = load_json(plan_file)
        if (
            not isinstance(plans, list)
            or not 1 <= len(plans) <= 8
            or any(
                not re.fullmatch(r"[a-zA-Z0-9_-]+", v.get("name", ""))
                or v.get("encoding") not in datasets
                or v.get("config", {}).get("kind") not in ("deep_mlp", "residual_glu")
                for v in plans
            )
            or len({v["name"] for v in plans}) != len(plans)
        ):
            raise PipelineError("Invalid bounded ablation plan")
    plan = {
        "source_sha256": implementation_identity(),
        "external_plan_sha256": file_sha256(plan_file) if plan_file else None,
        "datasets": {n: m["dataset_sha256"] for n, m in manifests.items()},
        "steps": 300,
        "batch_size": 128,
        "plans": plans,
        "selection": "validation only; source-wise FPR<=1% empirical, maximize lab macrofamily recall then AP; if none eligible keep none",
        "thresholds": "source-wise benign-only calibration target1%; no test tuning",
        "test_partitions_opened": False,
        "champion_selection": False,
        "sampling_counts_are_not_new_HTTP_requests": True,
    }
    atomic_json(output / "preregistered-plan.json", plan)
    started = time.monotonic()
    result = {"plan": plan, "models": {}, "formal_training": False, "champion_selected": False}

    def worker(arguments, name):
        with (
            (output / (name + ".stdout.log")).open("w") as out,
            (output / (name + ".stderr.log")).open("w") as err,
        ):
            c = subprocess.run(
                [sys.executable, "-m", "idps_ai", *arguments],
                stdout=out,
                stderr=err,
                timeout=600,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        if c.returncode:
            raise PipelineError("Ablation worker failed; inspect private logs")
        return load_json(output / (name + ".stdout.log"))

    for entry in plans:
        name, config = entry["name"], entry["config"]
        dataset = datasets[entry["encoding"]]
        conf = output / (name + ".yaml")
        conf.write_text(yaml.safe_dump(config))
        shared = [
            "request-train",
            "--dataset",
            dataset,
            "--config",
            str(conf),
            "--cpus",
            str(cpus),
            "--diagnostic-updates",
            "300",
        ]
        resumed, reference = output / (name + "-resumed"), output / (name + "-continuous")
        first = worker(
            [*shared, "--run-dir", str(resumed), "--epochs", "2", "--max-steps", "100"],
            name + "-first",
        )
        second = worker(
            [*shared, "--run-dir", str(resumed), "--epochs", "2", "--resume"], name + "-second"
        )
        control = worker(
            [*shared, "--run-dir", str(reference), "--epochs", "2"], name + "-reference"
        )
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
            raise PipelineError("Ablation exactresume/update budget failed")
        bundle = output / (name + "-bundle")
        card = worker(
            [
                "request-export",
                "--dataset",
                dataset,
                "--checkpoint",
                str(resumed),
                "--output",
                str(bundle),
                "--cpus",
                str(cpus),
            ],
            name + "-export",
        )
        result["models"][name] = {
            "encoding": entry["encoding"],
            "config": config,
            "parameters": sum(v.size for v in a.model.parameters.values()),
            "source_counts": a.state["training_source_counts"],
            "training_input_views": a.state["training_views"],
            "steps": a.model.steps,
            "resume_exact": exact,
            "optimizer_seconds": second["optimizer_seconds"],
            "first_session_steps": first["steps"],
            "reference_optimizer_seconds": control["optimizer_seconds"],
            "resources": second["resources"],
            "bundle": str(bundle),
            "manifest_sha256": file_sha256(bundle / "model_manifest.json"),
            "parity": card["parity"],
            "validation": card["validation"],
            "validation_by_source": card["validation_by_source"],
            "threshold": card["threshold"],
        }
        atomic_json(output / "report.json", result)
        print(
            json.dumps(
                {"completed": name, "validation": card["validation"], "resume_exact": exact}
            ),
            flush=True,
        )
    result.update(
        status="PASS_TECHNICAL_ONLY",
        wall_seconds=time.monotonic() - started,
        test_quality_opened=False,
    )
    atomic_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dataset", required=True)
    parser.add_argument("--encoded-dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cpus", type=int, choices=(1, 2, 4, 8), default=4)
    parser.add_argument(
        "--plan", help="Optional preregistered JSON plan, at most8bounded configurations"
    )
    args = parser.parse_args()
    run(args.raw_dataset, args.encoded_dataset, args.output, args.cpus, args.plan)

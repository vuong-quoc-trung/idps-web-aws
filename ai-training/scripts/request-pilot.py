#!/usr/bin/env python3
"""Fixed2epoch request-profile acceptance; no HPO or test-set selection."""

import argparse
import json
import math
import os
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


def run(dataset, output, cpus=4, learning_curve=False):
    dataset = Path(dataset).resolve()
    output = Path(output).resolve()
    manifest = verify_requests(dataset)
    if output.exists():
        raise PipelineError("Pilot output must be new; completed evidence is immutable")
    output.mkdir(mode=0o700, parents=True)
    start = time.monotonic()
    report = {
        "format_version": 1,
        "dataset_sha256": manifest["dataset_sha256"],
        "epochs": None if learning_curve else 2,
        "short_learning_curve": learning_curve,
        "diagnostic_update_cap": 300 if learning_curve else None,
        "seed": 17,
        "batch_size": 128,
        "models": {},
        "quality_test_opened": False,
        "champion_selected": False,
        "formal_training": False,
    }
    plan = {}
    for kind, width in [("deep_mlp", 256), ("residual_glu", 1024), ("denoising_autoencoder", 256)]:
        count = len(selected_training(dataset, kind)[0])
        plan[kind] = {
            "kind": kind,
            "width": width,
            "learning_rate": 0.0003,
            "total_steps": 2 * math.ceil(count / 128),
            "unique_training_views": count,
        }
        if learning_curve:
            plan[kind].update(
                total_steps=300,
                warmup_steps=15,
                binary_weighting="balanced" if kind != "denoising_autoencoder" else "none",
            )
    atomic_json(output / "preregistered-plan.json", plan)

    def worker(arguments, name):
        with (
            (output / (name + ".stdout.log")).open("w") as stdout,
            (output / (name + ".stderr.log")).open("w") as stderr,
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "idps_ai", *arguments],
                stdout=stdout,
                stderr=stderr,
                timeout=600,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        if completed.returncode:
            raise PipelineError("Request pilot worker failed; inspect private logs")
        return load_json(output / (name + ".stdout.log"))

    for kind, config in plan.items():
        conf = output / (kind + ".yaml")
        conf.write_text(yaml.safe_dump(config))
        shared = [
            "request-train",
            "--dataset",
            str(dataset),
            "--config",
            str(conf),
            "--cpus",
            str(cpus),
        ]
        if learning_curve:
            shared += ["--diagnostic-updates", "300"]
        run_dir, reference = output / (kind + "-resumed"), output / (kind + "-continuous")
        first = worker(
            [
                *shared,
                "--run-dir",
                str(run_dir),
                "--epochs",
                "1",
                *(["--max-steps", "100"] if learning_curve else []),
            ],
            kind + "-first",
        )
        second = worker(
            [*shared, "--run-dir", str(run_dir), "--epochs", "2", "--resume"], kind + "-second"
        )
        control = worker(
            [*shared, "--run-dir", str(reference), "--epochs", "2"], kind + "-reference"
        )
        a, b = load_checkpoint(run_dir), load_checkpoint(reference)
        if (not learning_curve and a.state["epoch"] != 2) or a.model.steps != config["total_steps"]:
            raise PipelineError("Request pilot failed to reach its fixed short budget")
        exact = all(np.array_equal(v, b.model.arrays()[n]) for n, v in a.model.arrays().items())
        exact = (
            exact
            and np.array_equal(a.permutation, b.permutation)
            and all(
                a.state[k] == b.state[k]
                for k in ["history", "rng", "cursor", "epoch", "global_step"]
            )
        )
        if not exact:
            raise PipelineError("Fresh-process request resume differs from uninterrupted reference")
        bundle = output / (kind + "-bundle")
        card = worker(
            [
                "request-export",
                "--dataset",
                str(dataset),
                "--checkpoint",
                str(run_dir),
                "--output",
                str(bundle),
                "--cpus",
                str(cpus),
            ],
            kind + "-export",
        )
        report["models"][kind] = {
            "parameters": sum(v.size for v in a.model.parameters.values()),
            "steps": a.model.steps,
            "unique_training_views": config["unique_training_views"],
            "resume_exact": exact,
            "optimizer_seconds": second["optimizer_seconds"],
            "reference_optimizer_seconds": control["optimizer_seconds"],
            "bundle": str(bundle),
            "bundle_manifest_sha256": file_sha256(bundle / "model_manifest.json"),
            "parity": card["parity"],
            "validation": card["validation"],
            "validation_by_source": card["validation_by_source"],
            "threshold": card["threshold"],
            "first_session": first,
            "second_session": second,
        }
        atomic_json(output / "report.json", report)
    report.update(status="PASS_TECHNICAL_ONLY", wall_seconds=time.monotonic() - start)
    atomic_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cpus", type=int, choices=(1, 2, 4, 8), default=4)
    parser.add_argument(
        "--learning-curve",
        action="store_true",
        help="100→300update diagnostic, balanced binary loss,180second session cap",
    )
    args = parser.parse_args()
    print(
        json.dumps(run(args.dataset, args.output, args.cpus, args.learning_curve), sort_keys=True)
    )

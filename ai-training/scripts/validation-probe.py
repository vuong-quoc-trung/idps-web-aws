#!/usr/bin/env python3
"""Two preregistered short GLU probes. Never opens final-test quality labels.

Run inside the existing8CPU/16GiB cgroup. Reuses prior baseline evidence rather
than refitting it. Output plan/configs/logs/checkpoints make interruption visible.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.capacity import validate_training_report
from idps_ai.training.checkpoint import load_checkpoint


def run(dataset, readiness, plan_path, output):
    validate_training_report(readiness, dataset)
    plan = load_json(plan_path)
    if (
        not plan.get("frozen_before_external_scores")
        or plan.get("official_training")
        or len(plan.get("variants", {})) != 2
    ):
        raise PipelineError("Only the two preregistered technical variants are permitted")
    output = Path(output)
    if (output / "report.json").exists() and load_json(output / "report.json").get(
        "status"
    ) == "COMPLETE_DEVELOPMENT_ONLY":
        raise PipelineError(
            "Completed experiment evidence is immutable; choose a new output for a new experiment"
        )
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    report = {
        "purpose": "Development validation probes, not formal training or champion selection",
        "plan_sha256": file_sha256(plan_path),
        "readiness_sha256": file_sha256(readiness),
        "models": {},
        "test_quality_opened": False,
        "champion_selected": False,
    }
    start = time.monotonic()

    def worker(arguments, name):
        with (
            (output / (name + ".stdout.log")).open("w") as out,
            (output / (name + ".stderr.log")).open("w") as err,
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "idps_ai", *arguments],
                stdout=out,
                stderr=err,
                timeout=600,
                env=os.environ | {"PYTHONPATH": str(AI_ROOT / "src")},
            )
        if completed.returncode:
            raise PipelineError("Development worker failed; inspect its private logs")
        return load_json(output / (name + ".stdout.log"))

    for index, (name, variant) in enumerate(plan["variants"].items()):
        config = yaml.safe_load((AI_ROOT / "configs/scale_pilot_config.yaml").read_text())
        config["model"]["regularization"] = {
            k: variant[k] for k in ("dropout", "label_smoothing", "weight_decay")
        }
        config["training"]["learning_rate"] = variant["learning_rate"]
        config_path = output / (name + ".yaml")
        text = yaml.safe_dump(config)
        if config_path.exists() and config_path.read_text() != text:
            raise PipelineError("Existing experiment configuration differs; use a new output")
        config_path.write_text(text)
        shared = [
            "train",
            "--dataset",
            str(dataset),
            "--config",
            str(config_path),
            "--readiness-report",
            str(readiness),
            "--cpus",
            "8",
            "--memory-limit-gib",
            "16",
            "--max-duration-minutes",
            "8",
        ]
        run_dir = output / (name + "-resumed")
        if not (run_dir / "latest.json").exists():
            worker([*shared, "--run-dir", str(run_dir), "--epochs", "1"], name + "-first")
        if load_checkpoint(run_dir).state["epoch"] < 2:
            worker(
                [
                    *shared,
                    "--run-dir",
                    str(run_dir),
                    "--resume-from",
                    str(run_dir),
                    "--epochs",
                    "2",
                ],
                name + "-second",
            )
        loaded = load_checkpoint(run_dir)
        if loaded.state["epoch"] != 2 or loaded.model.steps != plan["steps_per_candidate"]:
            raise PipelineError("Short probe did not reach its preregistered epoch/step budget")
        equivalent = None
        if index == 0:
            reference = output / (name + "-continuous")
            if not (reference / "latest.json").exists():
                worker([*shared, "--run-dir", str(reference), "--epochs", "2"], name + "-reference")
            elif load_checkpoint(reference).state["epoch"] < 2:
                worker(
                    [
                        *shared,
                        "--run-dir",
                        str(reference),
                        "--resume-from",
                        str(reference),
                        "--epochs",
                        "2",
                    ],
                    name + "-reference-resume",
                )
            continuous = load_checkpoint(reference)
            equivalent = all(
                np.array_equal(a, continuous.model.arrays()[k])
                for k, a in loaded.model.arrays().items()
            )
            equivalent = equivalent and np.array_equal(loaded.permutation, continuous.permutation)
            equivalent = equivalent and all(
                loaded.state[k] == continuous.state[k]
                for k in ("history", "numpy_rng", "python_rng", "epoch", "global_step")
            )
            if not equivalent:
                raise PipelineError("Fresh-process resumed probe differs from continuous reference")
        bundle = output / (name + "-bundle")
        if not (bundle / "model_manifest.json").exists():
            worker(
                [
                    "export",
                    "--dataset",
                    str(dataset),
                    "--checkpoint",
                    str(run_dir),
                    "--output",
                    str(bundle),
                    "--validation-only",
                    "--independent-validation",
                    "--cpus",
                    "8",
                ],
                name + "-export",
            )
        report["models"][name] = {
            "config_sha256": file_sha256(config_path),
            "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
            "parameters": sum(p.size for p in loaded.model.parameters.values()),
            "steps": loaded.model.steps,
            "history": loaded.state["history"],
            "training_seconds": loaded.state["optimizer_seconds"],
            "resume_exact_against_continuous": equivalent,
            "bundle": str(bundle),
            "bundle_manifest_sha256": file_sha256(bundle / "model_manifest.json"),
            "evaluation": load_json(bundle / "evaluation.json"),
            "parity": load_json(bundle / "model_manifest.json")["parity"],
        }
        atomic_json(output / "report.json", report)
    report["wall_seconds_this_invocation"] = time.monotonic() - start
    report["status"] = "COMPLETE_DEVELOPMENT_ONLY"
    atomic_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "readiness", "plan", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                Path(args.dataset).resolve(),
                Path(args.readiness).resolve(),
                Path(args.plan).resolve(),
                Path(args.output).resolve(),
            ),
            sort_keys=True,
        )
    )

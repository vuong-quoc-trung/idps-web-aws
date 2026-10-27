"""Actual subprocess S0: collect→prepare→2 epochs→new-process resume→ONNX."""

import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, load_json
from idps_ai.data.dataset import collect
from idps_ai.data.readers import Input
from idps_ai.data.split import prepare
from idps_ai.data.synthetic import synthetic_s0
from idps_ai.training.checkpoint import load_checkpoint


def run_s0(output, campaigns=15, requests_per_campaign=64, max_threads=2, memory_limit_gib=12):
    output = Path(output).resolve()
    if output.exists():
        raise PipelineError("S0 destination already exists; create a new run version")
    output.mkdir(parents=True, mode=0o700)
    started = time.time()
    preprocessing_start = time.perf_counter()
    from idps_ai.training.resources import resource_envelope

    with resource_envelope(max_threads, memory_limit_gib) as (_, preprocessing_resources):
        fixture = synthetic_s0(
            output / "raw", campaigns=campaigns, requests_per_campaign=requests_per_campaign
        )
        key = (output / "raw/redaction.key").read_bytes()
        inputs = [
            Input("student", output / "raw/student-audit.log"),
            Input("nginx", output / "raw/access.log"),
            Input("suricata", output / "raw/eve.json"),
        ]
        collected = collect(inputs, output / "collected", key, output / "raw/labels.jsonl")
        dataset = prepare(output / "collected", output / "prepared")
    preprocessing_wall_seconds = time.perf_counter() - preprocessing_start
    base = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    report = {
        "purpose": "S0 pipeline/resume verification on synthetic fixtures",
        "synthetic": True,
        "branch": "feat/ai-model-training",
        "started_at_unix": started,
        "fixture": fixture,
        "dataset_sha256": dataset["dataset_sha256"],
        "split": dataset["split"],
        "source_observations": collected["rows"],
        "feature_count": dataset["feature_count"],
        "rows": dataset["rows"],
        "models": {},
        "real_data_training_hours": 0.0,
        "production_quality_claim": False,
        "preprocessing_resources": preprocessing_resources,
        "preprocessing_wall_seconds_not_training": preprocessing_wall_seconds,
    }
    environment = os.environ | {"PYTHONPATH": str(AI_ROOT / "src")}

    def worker(args, logname):
        command = [sys.executable, "-m", "idps_ai", *args]
        result = subprocess.run(command, env=environment, capture_output=True, text=True)
        (output / (logname + ".stdout.log")).write_text(result.stdout)
        (output / (logname + ".stderr.log")).write_text(result.stderr)
        if result.returncode:
            raise PipelineError("S0 worker failed; inspect its private stderr log")
        return __import__("json").loads(result.stdout)

    for kind in ("mlp", "autoencoder"):
        config = {
            **base,
            "model": {**base["model"], "kind": kind},
            "training": {**base["training"], "scheduler_decay_steps": 5},
        }
        config_path = output / (kind + ".yaml")
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))
        run = output / (kind + "-resumed")
        continuous = output / (kind + "-continuous")
        common = [
            "train",
            "--dataset",
            str(output / "prepared"),
            "--config",
            str(config_path),
            "--max-threads",
            str(max_threads),
            "--memory-limit-gib",
            str(memory_limit_gib),
        ]
        first = worker([*common, "--run-dir", str(run), "--epochs", "2"], kind + "-session1")
        second = worker(
            [*common, "--run-dir", str(run), "--epochs", "4", "--resume-from", str(run)],
            kind + "-session2",
        )
        full = worker(
            [*common, "--run-dir", str(continuous), "--epochs", "4"], kind + "-continuous"
        )
        a, b = load_checkpoint(run), load_checkpoint(continuous)
        equivalent = (
            a.state["global_step"] == b.state["global_step"]
            and a.state["scheduler"] == b.state["scheduler"]
            and a.state["numpy_rng"] == b.state["numpy_rng"]
            and a.state["python_rng"] == b.state["python_rng"]
            and np.array_equal(a.permutation, b.permutation)
            and all(
                np.array_equal(value, b.model.arrays()[name])
                for name, value in a.model.arrays().items()
            )
        )
        if not equivalent or first["process_id"] == second["process_id"]:
            raise PipelineError("Continuous vs resumed model/optimizer/RNG/sampler states differ")
        bundle = worker(
            [
                "export",
                "--dataset",
                str(output / "prepared"),
                "--checkpoint",
                str(run),
                "--output",
                str(output / (kind + "-bundle")),
                "--max-threads",
                str(max_threads),
                "--memory-limit-gib",
                str(memory_limit_gib),
            ],
            kind + "-export",
        )
        if any(
            s["resources"]["peak_tree_rss_bytes"] >= s["resources"]["memory_limit_bytes"]
            for s in (first, second, full)
        ):
            raise PipelineError("S0 exceeded the configured memory ceiling")
        report["models"][kind] = {
            "resume_equivalent": equivalent,
            "first_process_id": first["process_id"],
            "resumed_process_id": second["process_id"],
            "global_step": second["global_step"],
            "epoch": second["epoch"],
            "training_rows": a.state["shard"]["row_count"],
            "benign_only_training": kind == "autoencoder",
            "next_learning_rate": a.state["scheduler"]["next_learning_rate"],
            "scheduler_decay_steps": config["training"]["scheduler_decay_steps"],
            "config_sha256": second["config_sha256"],
            "checkpoint_manifest_sha256": second["checkpoint_manifest_sha256"],
            "onnx_sha256": bundle["files"]["model.onnx"],
            "onnx_parity": bundle["parity"],
            "threshold": bundle["threshold"],
            "sessions": [first, second],
            "continuous_reference_session": full,
            "evaluation": load_json(output / (kind + "-bundle/evaluation.json")),
        }
    report["ended_at_unix"] = time.time()
    report["wall_seconds"] = report["ended_at_unix"] - started
    report["optimizer_seconds_synthetic"] = sum(
        s["session_optimizer_seconds"]
        for item in report["models"].values()
        for s in item["sessions"]
    )
    report["comparison_optimizer_seconds"] = sum(
        item["continuous_reference_session"]["session_optimizer_seconds"]
        for item in report["models"].values()
    )
    report["outside_training_session_wall_seconds"] = report["wall_seconds"] - sum(
        s["session_wall_seconds"]
        for item in report["models"].values()
        for s in [*item["sessions"], item["continuous_reference_session"]]
    )
    report["artifact_root"] = str(output)
    atomic_json(output / "s0_report.json", report)
    return report

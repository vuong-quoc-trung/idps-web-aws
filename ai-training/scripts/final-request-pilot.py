#!/usr/bin/env python3
"""One short, append-only request-channel feasibility pilot; prospective stays closed."""

import argparse
import importlib.metadata
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import psutil
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.training.checkpoint import (
    RunLock,
    load_checkpoint,
    save_checkpoint,
    validate_generation,
)
from idps_ai.training.models import Model

ROOT = Path(__file__).resolve().parents[2]


def load(p):
    return json.loads(p.read_text())


def counts(scores, labels, t):
    flags = np.asarray(scores) > t
    positive = np.asarray(labels) > 0
    return {
        name: int(mask.sum())
        for name, mask in {
            "TP": flags & positive,
            "FN": ~flags & positive,
            "FP": flags & ~positive,
            "TN": ~flags & ~positive,
        }.items()
    }


def materials(root):
    r = load(root / "dataset-release.json")
    assert r["dataset_fingerprint"] == digest(
        {k: v for k, v in r.items() if k != "dataset_fingerprint"}
    )
    for name, sha in r["files_sha256"].items():
        assert file_sha256(root / name) == sha
    with np.load(root / "train.npz", allow_pickle=False) as d:
        train = {k: d[k].copy() for k in d.files}
    with np.load(root / "calibration.npz", allow_pickle=False) as d:
        cal = {k: d[k].copy() for k in d.files}
    return r, train, cal


def prepare(dataset, run):
    run.mkdir(parents=True, mode=0o700, exist_ok=False)
    r, train, cal = materials(dataset)
    cfg = load(ROOT / "ai-training/configs/research/request-channel-unblock-pilot.json")
    assert cfg["parameters"] == 50696 and cfg["initialization"] == "NEW_INITIALIZATION"
    assert file_sha256(ROOT / cfg["feature_source"]) == cfg["feature_source_sha256"]
    model = Model(588, 64, "deep_mlp", cfg["seed"])
    planned = math.ceil(len(train["x"]) / cfg["batch_size"])
    assert planned <= cfg["max_updates"] and cfg["max_epochs"] == 1
    plan = {
        "schema_version": "final-request-pilot-plan-1",
        "run_id": run.name,
        "scope": "ENGINEERING_AND_SMALL_SAMPLE_FEASIBILITY_ONLY",
        "dataset": str(dataset),
        "dataset_fingerprint": r["dataset_fingerprint"],
        "dataset_release_sha256": file_sha256(dataset / "dataset-release.json"),
        "fit_rows": len(train["x"]),
        "fit_groups": r["fit"]["groups"],
        "input_dim": 588,
        "parameters": 50696,
        "model": model.metadata(),
        "initialization": "NEW_INITIALIZATION",
        "seed": cfg["seed"],
        "batch_size": cfg["batch_size"],
        "learning_rate": cfg["learning_rate"],
        "scheduler": "constant",
        "epochs": 1,
        "planned_optimizer_steps": planned,
        "checkpoint_every_steps": 1,
        "candidate_encoder_source_sha256": cfg["feature_source_sha256"],
        "pilot_source_sha256": file_sha256(__file__),
        "model_source_sha256": {
            str(p.relative_to(ROOT)): file_sha256(p)
            for p in (ROOT / "ai-training/src/idps_ai/training").glob("*.py")
        },
        "dependencies": {
            n: importlib.metadata.version(n) for n in ["numpy", "scikit-learn", "threadpoolctl"]
        },
        "evaluation": "TRAIN/CAL diagnostics only; prospective samples/labels/tensors remain closed; no promotion",
        "threshold_rule": "strict > max unique benign CALIBRATION view score; post-selected calibration flags not population FPR",
        "stop": "one epoch/budget; nonfinite; data/source/hash mismatch; existing independent thermal/heartbeat watchdog loss; no automatic restart",
        "enforcement": "DISABLED",
    }
    plan["plan_sha256"] = digest(plan)
    atomic_json(run / "plan.json", plan)
    # Control is computed before any optimizer step, on permitted TRAIN/CAL only.
    frozen = ResearchMVP("request-v2", cpus=1)
    with threadpool_limits(limits=1):
        train_scores = frozen.v2_model.predict(train["baseline"])[0]
        cal_scores = frozen.v2_model.predict(cal["baseline"])[0]
    t = float(cal_scores[cal["y"] == 0].max())
    control = {
        "status": "EXPOSED_TRAIN_CAL_DIAGNOSTIC_ONLY",
        "dataset_fingerprint": r["dataset_fingerprint"],
        "prospective_scores_computed": 0,
        "frozen_threshold": frozen.v2_threshold,
        "calibration_only_threshold": t,
        "comparator": ">",
        "frozen": {
            "TRAIN": counts(train_scores, train["y"], frozen.v2_threshold),
            "CALIBRATION": counts(cal_scores, cal["y"], frozen.v2_threshold),
        },
        "calibration_only": {
            "TRAIN": counts(train_scores, train["y"], t),
            "CALIBRATION": counts(cal_scores, cal["y"], t),
        },
        "threshold_used_for_deployment": False,
        "quality_claim": "NOT_ESTABLISHED; no independent eval or population FPR estimate",
    }
    atomic_json(run / "baseline-control.json", control)
    print(
        json.dumps(
            {
                "run": run.name,
                "fit_rows": len(train["x"]),
                "steps": planned,
                "scope": plan["scope"],
                "control": control,
            },
            indent=2,
        )
    )


def train(run, resource):
    plan = load(run / "plan.json")
    assert plan["plan_sha256"] == digest({k: v for k, v in plan.items() if k != "plan_sha256"})
    assert plan["pilot_source_sha256"] == file_sha256(__file__)
    assert all(file_sha256(ROOT / p) == sha for p, sha in plan["model_source_sha256"].items())
    assert (
        file_sha256(ROOT / "ai-training/src/idps_ai/features/research_request_channels.py")
        == plan["candidate_encoder_source_sha256"]
    )
    dataset = Path(plan["dataset"])
    r, fit, cal = materials(dataset)
    assert r["dataset_fingerprint"] == plan["dataset_fingerprint"]
    rng = np.random.default_rng(plan["seed"])
    order = rng.permutation(len(fit["x"])).astype(np.int64)
    net = Model(588, 64, "deep_mlp", plan["seed"])
    start = time.time()
    cursor = 0
    metrics = []
    checkpoint = None

    def status(state, error=None):
        monitor = (
            load(resource / "resource-status.json")
            if (resource / "resource-status.json").exists()
            else {}
        )
        atomic_json(
            run / "status.json",
            {
                "state": state,
                "run_id": plan["run_id"],
                "model": "request-channel-robustness-v3",
                "dataset_fingerprint": plan["dataset_fingerprint"],
                "current_step": net.steps,
                "planned_steps": plan["planned_optimizer_steps"],
                "training_loss": metrics[-1]["loss"] if metrics else None,
                "checkpoint": str(checkpoint) if checkpoint else None,
                "checkpoint_latest": str(run / "latest.json"),
                "logs": str(run / "metrics.jsonl"),
                "service": monitor.get("unit"),
                "PID": os.getpid(),
                "started_at": start,
                "last_heartbeat": time.time(),
                "finished_at": time.time() if state != "RUNNING" else None,
                "RSS_bytes": psutil.Process().memory_info().rss,
                "MemAvailable_bytes": psutil.virtual_memory().available,
                "resource_status": str(resource / "resource-status.json"),
                "error": error,
                "actual_resume_claim": "NOT_TESTED_ON_REAL_RUN; synthetic exact-next-update previously verified",
            },
        )

    with RunLock(run), threadpool_limits(limits=1):
        assert not (run / "latest.json").exists(), (
            "Existing pilot may not be overwritten or automatically restarted"
        )
        status("RUNNING")
        try:
            initial_loss = float(net.classification_errors(fit["x"], fit["y"]).mean())
            with (run / "metrics.jsonl").open("x") as log:
                while cursor < len(order):
                    idx = order[cursor : cursor + plan["batch_size"]]
                    loss = float(
                        net.train_batch(fit["x"][idx], fit["y"][idx], plan["learning_rate"])
                    )
                    cursor += len(idx)
                    assert np.isfinite(loss) and net.steps <= plan["planned_optimizer_steps"]
                    entry = {
                        "step": net.steps,
                        "cursor": cursor,
                        "loss": loss,
                        "timestamp": time.time(),
                    }
                    metrics.append(entry)
                    log.write(json.dumps(entry) + "\n")
                    log.flush()
                    os.fsync(log.fileno())
                    state = {
                        "plan_sha256": plan["plan_sha256"],
                        "dataset_fingerprint": plan["dataset_fingerprint"],
                        "training_configuration": plan,
                        "sampler_cursor": cursor,
                        "epoch": 1 if cursor == len(order) else 0,
                        "RNG": rng.bit_generator.state,
                        "scheduler": {
                            "kind": "constant",
                            "step": net.steps,
                            "learning_rate": plan["learning_rate"],
                        },
                        "metrics": metrics,
                        "started_at": start,
                        "last_heartbeat": time.time(),
                    }
                    checkpoint = save_checkpoint(run, net, state, order)
                    validate_generation(checkpoint)
                    status("RUNNING")
            loaded = load_checkpoint(run)
            assert loaded.model.steps == plan["planned_optimizer_steps"] and loaded.state[
                "sampler_cursor"
            ] == len(order)
            assert loaded.state["dataset_fingerprint"] == plan["dataset_fingerprint"]
            assert all(np.array_equal(v, loaded.model.arrays()[k]) for k, v in net.arrays().items())
            scores = net.predict(cal["x"])[0]
            threshold = float(scores[cal["y"] == 0].max())
            final = {
                "state": "COMPLETED",
                "run_id": plan["run_id"],
                "scope": plan["scope"],
                "fit_rows": len(order),
                "optimizer_steps": net.steps,
                "epochs": 1,
                "initial_train_mean_cross_entropy": initial_loss,
                "final_train_mean_cross_entropy": float(
                    net.classification_errors(fit["x"], fit["y"]).mean()
                ),
                "candidate_calibration_threshold": threshold,
                "threshold_comparator": ">",
                "TRAIN": counts(net.predict(fit["x"])[0], fit["y"], threshold),
                "CALIBRATION": counts(scores, cal["y"], threshold),
                "checkpoint_manifest_sha256": file_sha256(checkpoint / "manifest.json"),
                "checkpoint_roundtrip_arrays_equal": True,
                "real_data_exact_resume": "NOT_TESTED; checkpoint reload only is not next-update equivalence",
                "dataset_fingerprint": plan["dataset_fingerprint"],
                "prospective_scores_computed": 0,
                "quality_improvement_claim": False,
                "promoted": False,
                "finished_at": time.time(),
            }
            atomic_json(run / "result.json", final)
            status("COMPLETED")
            print(json.dumps(final, indent=2))
        except BaseException as exc:
            status("FAILED", type(exc).__name__)
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "train"])
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--dataset", type=Path)
    p.add_argument("--resource", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.command == "prepare":
        prepare(a.dataset.resolve(), a.run.resolve())
    else:
        train(a.run.resolve(), a.resource.resolve())

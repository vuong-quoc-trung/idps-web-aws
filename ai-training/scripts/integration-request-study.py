#!/usr/bin/env python3
"""One bounded numeric-channel-mask candidate using curated WAF train views.

Frozen encoders/model files are never changed. Sampler/RNG/Adam state is saved
through existing immutable checkpoint utilities. No development/calibration
arrays are opened by the train command.
"""

import argparse
import json
import os
import platform
import signal
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.models import Model

DATASET = AI_ROOT / ".artifacts/request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz"
DATASET_SHA = "279dca7d03b38bb2092bf775762bfe68904eea131e0d1145a564de0f98441049"


def identity():
    return {
        "study_script_sha256": file_sha256(__file__),
        "training_modules": {
            str(p.relative_to(AI_ROOT)): file_sha256(p)
            for p in sorted((AI_ROOT / "src/idps_ai/training").glob("*.py"))
        },
        "python": platform.python_version(),
        "dependencies": {
            name: version(name) for name in ["numpy", "scikit-learn", "threadpoolctl"]
        },
    }


def model():
    return Model(
        588,
        64,
        "deep_mlp",
        seed=31,
        objective={"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.0},
    )


def prepare(root):
    root = Path(root).resolve()
    if root.exists():
        raise PipelineError("New study output required")
    root.mkdir(mode=0o700, parents=True)
    if file_sha256(DATASET) != DATASET_SHA:
        raise PipelineError("Curated WAF tensor changed")
    with np.load(DATASET, allow_pickle=False) as data:
        role = data["role"]
        mask = role == 0
        labels = data["label"][mask]
        views = data["view"][mask]
        numeric = data["numeric"][mask]
        content = data["content"][mask]
    x = np.concatenate((numeric, content), axis=1).astype(np.float32)
    if x.shape != (120435, 588) or len(set(views.tolist())) != len(views):
        raise PipelineError("Unexpected unique train corpus")
    for name, value in [("train.npy", x), ("labels.npy", labels), ("views.npy", views)]:
        with (root / name).open("xb") as stream:
            np.save(stream, value, allow_pickle=False)
    plan = {
        "format_version": 1,
        "candidate": "request-v2-numeric-mask-p025",
        "hypothesis": "Train-time numeric channel masking makes content useful when privacy projection removes numeric evidence; no inference encoder change",
        "dataset_original_sha256": DATASET_SHA,
        "fit_role": "role0_only",
        "train_unique_views": len(views),
        "train_class_counts": {
            "publisher_NORMAL": int(np.sum(labels == 0)),
            "publisher_ANOMALOUS": int(np.sum(labels == 1)),
        },
        "material_sha256": {
            n: file_sha256(root / n) for n in ["train.npy", "labels.npy", "views.npy"]
        },
        "seed": 31,
        "batch_size": 256,
        "updates": 3072,
        "learning_rate": 0.001,
        "numeric_mask_probability": 0.25,
        "augmentation": "zero first76 features for Bernoulli-selected rows; stateless PCG64 SeedSequence(seed, committed_step,5341); no inverted scaling; training only",
        "architecture": "deep_mlp588x64x64x64x64x8 partial_binary_v1",
        "parameters": 50696,
        "identity": identity(),
        "checkpoint_every_updates": 256,
        "calibration": "role1 publisher NORMAL p99 higher; score strictly greater than threshold",
        "evaluation": "role2 development and exposed DVWA/Juice regression; optional existing ModSec retrospective tensor; never independent",
        "selection": "promote for demo only if WAF development normal flags<=baseline+0.002 absolute and anomaly flagged fraction>=baseline-0.01; require DVWA improvement>=4 additional attempts with no additional benign flags; otherwise package frozen reference. No threshold search or hyperparameter retries.",
        "formal_admitted": 0,
        "frozen_untouched": True,
    }
    plan["plan_sha256"] = digest(plan)
    atomic_json(root / "plan.json", plan)
    print(json.dumps({"prepared_train_unique": len(views), "plan_sha256": plan["plan_sha256"]}))


def read_plan(root):
    root = Path(root).resolve()
    plan = load_json(root / "plan.json")
    if (
        plan["plan_sha256"] != digest({k: v for k, v in plan.items() if k != "plan_sha256"})
        or plan["identity"] != identity()
    ):
        raise PipelineError("Plan or source/environment mismatch; do not force-resume")
    for name, sha in plan["material_sha256"].items():
        if file_sha256(root / name) != sha:
            raise PipelineError("Train material mismatch")
    return root, plan


def masked_batch(x, seed, step, p):
    result = np.asarray(x, np.float32).copy()
    mask = np.random.default_rng(np.random.SeedSequence([seed, step, 5341])).random(len(result)) < p
    result[mask, :76] = 0
    return result, int(mask.sum())


def train(root, run, through):
    root, plan = read_plan(root)
    run = Path(run).resolve()
    if not 1 <= through <= plan["updates"]:
        raise PipelineError("Invalid update target")
    x = np.load(root / "train.npy", mmap_mode="r", allow_pickle=False)
    labels = np.load(root / "labels.npy", mmap_mode="r", allow_pickle=False)
    rng = np.random.default_rng(plan["seed"])
    stop = [False]
    handlers = {
        s: signal.signal(s, lambda *_: stop.__setitem__(0, True))
        for s in [signal.SIGTERM, signal.SIGINT]
    }
    started = time.monotonic()
    with RunLock(run), threadpool_limits(limits=1):
        if (run / "latest.json").exists():
            loaded = load_checkpoint(run)
            if loaded.used_previous or loaded.state["plan_sha256"] != plan["plan_sha256"]:
                raise PipelineError("Unexpected checkpoint/fallback")
            net = loaded.model
            order = loaded.permutation
            state = loaded.state
            rng.bit_generator.state = state["sampler_rng_state"]
            cursor = state["sampler_cursor"]
            losses = state["losses"]
            masked = state["masked_row_exposures"]
            original_step = net.steps
        else:
            net = model()
            order = rng.permutation(len(x))
            cursor = 0
            losses = []
            masked = 0
            original_step = 0
        if through <= net.steps:
            raise PipelineError("Run already at requested target")
        while net.steps < through:
            if cursor + plan["batch_size"] > len(order):
                order = rng.permutation(len(x))
                cursor = 0
            batch = order[cursor : cursor + plan["batch_size"]]
            cursor += plan["batch_size"]
            values, n = masked_batch(
                x[batch], plan["seed"], net.steps, plan["numeric_mask_probability"]
            )
            loss = net.train_batch(
                values,
                np.full(len(batch), -1, np.int64),
                plan["learning_rate"],
                binary_targets=labels[batch],
            )
            if not np.isfinite(loss):
                raise PipelineError("Nonfinite training loss")
            losses.append(float(loss))
            masked += n
            if net.steps % plan["checkpoint_every_updates"] == 0 or net.steps == through or stop[0]:
                path = save_checkpoint(
                    run,
                    net,
                    {
                        "plan_sha256": plan["plan_sha256"],
                        "sampler_cursor": cursor,
                        "sampler_rng_state": rng.bit_generator.state,
                        "losses": losses,
                        "masked_row_exposures": masked,
                        "fit_role": "train_only",
                        "calibration_development_DVWA_rows_used_for_fitting": 0,
                    },
                    order,
                )
                atomic_json(
                    run / "progress.json",
                    {
                        "step": net.steps,
                        "checkpoint": str(path),
                        "mean_last100_loss": float(np.mean(losses[-100:])),
                    },
                )
            if stop[0]:
                break
        last = load_checkpoint(run)
        if not all(np.array_equal(v, last.model.arrays()[k]) for k, v in net.arrays().items()):
            raise PipelineError("Checkpoint readback mismatch")
        summary = {
            "step": net.steps,
            "from_step": original_step,
            "through_target": through,
            "plan_sha256": plan["plan_sha256"],
            "final_checkpoint_manifest_sha256": file_sha256(last.path / "manifest.json"),
            "checkpoint": str(last.path),
            "first100_loss_mean": float(np.mean(losses[:100])),
            "last100_loss_mean": float(np.mean(losses[-100:])),
            "loss_min": min(losses),
            "loss_max": max(losses),
            "sample_exposures": net.steps * plan["batch_size"],
            "masked_row_exposures": masked,
            "effective_epochs": net.steps * plan["batch_size"] / len(x),
            "wall_seconds_this_process": time.monotonic() - started,
            "signal_checkpointed": stop[0],
            "threads": {
                p.name: sorted(os.sched_getaffinity(int(p.name)))
                for p in Path("/proc/self/task").glob("*")
            },
            "train_unique_views": len(x),
            "parameters": sum(v.size for v in net.parameters.values()),
            "calibration_development_DVWA_rows_used_for_fitting": 0,
            "training_identity": plan["identity"],
        }
        atomic_json(run / f"session-{original_step:05}-{net.steps:05}.json", summary)
        print(json.dumps(summary))
    for sig, h in handlers.items():
        signal.signal(sig, h)


def compare(a, b, output):
    aa, bb = load_checkpoint(a), load_checkpoint(b)
    equal = {k: np.array_equal(v, bb.model.arrays()[k]) for k, v in aa.model.arrays().items()}
    result = {
        "status": "RESUME_EXACT"
        if all(equal.values())
        and np.array_equal(aa.permutation, bb.permutation)
        and aa.state == bb.state
        else "FAIL",
        "steps": [aa.model.steps, bb.model.steps],
        "arrays_equal": equal,
        "sampler_equal": np.array_equal(aa.permutation, bb.permutation),
        "state_rng_history_equal": aa.state == bb.state,
        "scope": "fresh OS process invocations; exact arrays including parameters/Adam m/v, RNG/permutation/cursor and loss history",
    }
    atomic_json(output, result)
    if result["status"] != "RESUME_EXACT":
        raise PipelineError("Fresh-process resume mismatch")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=["prepare", "train", "compare"], required=True)
    parser.add_argument("--root")
    parser.add_argument("--run")
    parser.add_argument("--through", type=int)
    parser.add_argument("--reference")
    parser.add_argument("--output")
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "prepare":
        prepare(args.root)
    elif args.action == "train":
        train(args.root, args.run, args.through)
    else:
        compare(args.run, args.reference, args.output)

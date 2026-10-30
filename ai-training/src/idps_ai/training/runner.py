"""Deterministic mini-batch training and exact same-run resume across processes."""

from __future__ import annotations

import os
import platform
import random
import signal
import time
import uuid
from importlib.metadata import version
from pathlib import Path

import numpy as np

from idps_ai.common import (
    AI_ROOT,
    CLASSES,
    PipelineError,
    atomic_json,
    digest,
    file_sha256,
    load_json,
)
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.deep import AUTOENCODERS, DEEP_KINDS
from idps_ai.training.evaluation import threshold_at_fpr
from idps_ai.training.models import Model
from idps_ai.training.resources import cgroup_readback, resource_envelope
from idps_ai.training.schedule import learning_rate


def environment_identity():
    return {
        "python": platform.python_version(),
        "dependencies": {
            name: version(name)
            for name in ("numpy", "pyarrow", "scikit-learn", "onnx", "onnxruntime")
        },
        "requirements_sha256": file_sha256(AI_ROOT / "requirements.txt")
        if (AI_ROOT / "requirements.txt").exists()
        else None,
    }


def implementation_identity():
    source = AI_ROOT / "src/idps_ai"
    return digest(
        {str(file.relative_to(source)): file_sha256(file) for file in sorted(source.rglob("*.py"))}
    )


def load_arrays(dataset, directory, kind, feature_count, memory_limit):
    counts = {part: 0 for part in ("train", "val", "test")}
    for row in iter_rows(Path(dataset) / "features.parquet", columns=["split", "label"]):
        if row["split"] == "calibration":
            counts.setdefault("calibration", 0)
        if row["split"] not in counts:
            raise PipelineError("Unknown prepared feature partition")
        if kind in AUTOENCODERS and row["split"] == "train" and row["label"] != 0:
            continue
        counts[row["split"]] += 1
    if any(count == 0 for count in counts.values()):
        raise PipelineError("Empty model partition after reviewed/benign filtering")
    if max(counts.values()) * feature_count * 4 > memory_limit * 0.5:
        raise PipelineError("Dataset cache exceeds training memory budget; reduce snapshot size")
    cache = Path(directory) / "cache"
    cache.mkdir(exist_ok=True, mode=0o700)
    arrays = {}
    for part, count in counts.items():
        x = np.lib.format.open_memmap(
            cache / (part + "-x.npy"), mode="w+", dtype=np.float32, shape=(count, feature_count)
        )
        y = np.lib.format.open_memmap(
            cache / (part + "-y.npy"), mode="w+", dtype=np.int64, shape=(count,)
        )
        arrays[part] = (x, y)
    offsets = dict.fromkeys(counts, 0)
    for row in iter_rows(Path(dataset) / "features.parquet"):
        if kind in AUTOENCODERS and row["split"] == "train" and row["label"] != 0:
            continue
        part = row["split"]
        x, y = arrays[part]
        index = offsets[part]
        values = np.asarray(row["x"], dtype=np.float32)
        if values.shape != (feature_count,) or not np.isfinite(values).all():
            raise PipelineError("Invalid feature tensor in prepared dataset")
        x[index], y[index] = values, CLASSES.index(row["attack_family"])
        offsets[part] += 1
    for x, y in arrays.values():
        x.flush()
        y.flush()
    return arrays


def predict_batches(model, x, batch_size=512):
    scores, outputs = [], []
    for start in range(0, len(x), batch_size):
        score, output = model.predict(x[start : start + batch_size])
        scores.append(score)
        if model.kind not in AUTOENCODERS:
            outputs.append(output)
    return np.concatenate(scores), np.concatenate(outputs) if outputs else None


def tuple_tree(value):
    return tuple(tuple_tree(v) for v in value) if isinstance(value, list) else value


def train(
    dataset,
    run_dir,
    config,
    epochs=20,
    resume_from=None,
    max_duration_minutes=150,
    max_threads=8,
    memory_limit_gib=16,
    checkpoint_every_seconds=300,
    max_steps=None,
):
    if (
        epochs < 1
        or max_duration_minutes < 0
        or checkpoint_every_seconds <= 0
        or max_steps is not None
        and max_steps < 1
    ):
        raise PipelineError("Invalid training duration/epochs/checkpoint options")
    run_dir, dataset = Path(run_dir).resolve(), Path(dataset).resolve()
    if run_dir == dataset or dataset.is_relative_to(run_dir) or run_dir.is_relative_to(dataset):
        raise PipelineError("Run cache must be outside the immutable dataset")
    data_manifest = verify_dataset(dataset, "prepared")
    spec = load_json(dataset / "feature_spec.json")
    learning = {
        "model": config["model"],
        "training": config["training"],
        "classes": list(CLASSES),
        "feature_spec_sha256": file_sha256(dataset / "feature_spec.json"),
    }
    config_sha = digest(learning)
    env, code_sha = environment_identity(), implementation_identity()
    model_config, training = config["model"], config["training"]
    kind = model_config["kind"]
    weighting = training.get("class_weighting", "none")
    if weighting not in ("none", "balanced_sqrt") or (kind in AUTOENCODERS and weighting != "none"):
        raise PipelineError("Unsupported class weighting for this model")
    batch_size = int(training["batch_size"])
    if not 1 <= batch_size <= 4096 or not 0 < training["learning_rate"] <= 1:
        raise PipelineError("Invalid learning configuration")
    learning_rate(training, 0)
    if not training.get("validation_during_training", True) and training.get(
        "early_stopping_patience", 0
    ):
        raise PipelineError("No-validation fitting requires fixed epochs without early stopping")
    if kind == "residual_glu":
        if training.get("regime") == "technical_pilot":
            if epochs > 2 or max_duration_minutes > 8 or max_steps is not None and max_steps > 1024:
                raise PipelineError(
                    "Technical main-model pilots are capped at2epochs/8minutes/1024 explicit steps per session"
                )
        elif training.get("regime") == "formal_scale":
            from idps_ai.data.corpus import require_scale_dataset

            require_scale_dataset(dataset)
        else:
            raise PipelineError(
                "Main model requires an explicit technical_pilot or formal_scale regime"
            )
    if kind in AUTOENCODERS and spec.get("fit_labels") != "benign_only":
        raise PipelineError("Autoencoder requires a benign-only train-fitted scaler")
    start = time.monotonic()
    session_id = uuid.uuid4().hex
    started_at = time.time()
    reason = None
    previous_handlers = {}

    def stop(signum, _frame):
        nonlocal reason
        reason = signal.Signals(signum).name

    with RunLock(run_dir), resource_envelope(max_threads, memory_limit_gib) as (memory, resources):
        if (run_dir / "latest.json").exists() and resume_from is None:
            raise PipelineError(
                "Run already has a checkpoint; resume it or choose a new run directory"
            )
        arrays = load_arrays(
            dataset, run_dir, kind, len(spec["columns"]), int(memory_limit_gib * 1024**3)
        )
        x, y = arrays["train"]
        class_weights = None
        if weighting == "balanced_sqrt":
            counts = np.bincount(y, minlength=len(CLASSES))
            if (counts == 0).any():
                raise PipelineError("Balanced classifier requires every training class")
            class_weights = np.sqrt(len(y) / (len(CLASSES) * counts))
            class_weights = (class_weights / class_weights.mean()).astype(np.float32)
        rng = np.random.default_rng(training["seed"])
        random.seed(training["seed"])
        if resume_from is not None:
            loaded = load_checkpoint(resume_from)
            model, state, permutation = loaded.model, loaded.state, loaded.permutation
            if (model.class_weights is None) != (class_weights is None) or (
                class_weights is not None and not np.array_equal(model.class_weights, class_weights)
            ):
                raise PipelineError("Resume class weighting differs from train-only counts")
            if (model.input_dim, model.hidden_dim, model.kind) != (
                len(spec["columns"]),
                model_config["hidden_dim"],
                kind,
            ):
                raise PipelineError(
                    "Checkpoint architecture differs from the learning configuration"
                )
            for field, expected in (
                ("dataset_sha256", data_manifest["dataset_sha256"]),
                ("config_sha256", config_sha),
                ("environment", env),
                ("implementation_sha256", code_sha),
            ):
                if state.get(field) != expected:
                    raise PipelineError(
                        "Resume rejected: dataset/config/environment/implementation checksum mismatch"
                    )
            if state.get("stop_reason") == "early_stopping":
                raise PipelineError(
                    "Early-stopped run is terminal; create a new reviewed child run"
                )
            if (
                len(permutation) != len(x)
                or not np.array_equal(np.sort(permutation), np.arange(len(x)))
                or not 0 <= state["cursor"] < len(x)
            ):
                raise PipelineError("Resume sampler does not match the dataset")
            if model.steps != state["global_step"]:
                raise PipelineError("Optimizer/global-step mismatch")
            expected_scheduler = {
                "global_step": model.steps,
                "next_learning_rate": learning_rate(training, model.steps),
            }
            if state.get("scheduler") != expected_scheduler:
                raise PipelineError(
                    "Checkpoint scheduler state does not match the learning configuration"
                )
            rng.bit_generator.state = state["numpy_rng"]
            random.setstate(tuple_tree(state["python_rng"]))
            state["used_previous_checkpoint"] = loaded.used_previous
        else:
            model = Model(
                len(spec["columns"]),
                model_config["hidden_dim"],
                kind,
                training["seed"],
                class_weights=class_weights,
                regularization=model_config.get("regularization"),
            )
            permutation = rng.permutation(len(x)).astype(np.int64)
            state = {
                "run_id": uuid.uuid4().hex,
                "dataset_sha256": data_manifest["dataset_sha256"],
                "config_sha256": config_sha,
                "environment": env,
                "implementation_sha256": code_sha,
                "learning_config": learning,
                "epoch": 0,
                "cursor": 0,
                "global_step": 0,
                "best_metric": None,
                "patience": 0,
                "history": [],
                "optimizer_seconds": 0.0,
                "wall_seconds": 0.0,
                "epoch_loss_sum": 0.0,
                "epoch_loss_samples": 0,
                "class_weighting": weighting,
                "training_loss_semantics": "sample-count weighted mean of per-batch objectives",
                "validation_loss_semantics": "fixed train-derived weighted CE, or benign-only AE MSE; all-class unweighted loss reported separately",
            }
        state["shard"] = {
            "file": "features.parquet",
            "sha256": data_manifest["files"]["features.parquet"]["sha256"],
            "partition": "train",
            "row_count": len(x),
        }
        if state["epoch"] > epochs:
            raise PipelineError("Target epochs are below checkpoint progress")
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, stop)
        session_optimizer = 0.0
        initial_step = model.steps
        last_checkpoint = time.monotonic()
        session_base_wall = state["wall_seconds"]
        base_optimizer = state["optimizer_seconds"]

        def checkpoint(best=False):
            state.update(
                numpy_rng=rng.bit_generator.state,
                python_rng=random.getstate(),
                global_step=model.steps,
                session_id=session_id,
                optimizer_seconds=base_optimizer + session_optimizer,
                wall_seconds=session_base_wall + time.monotonic() - start,
                scheduler={
                    "global_step": model.steps,
                    "next_learning_rate": learning_rate(training, model.steps),
                },
                stop_reason=reason,
                resources=resources,
            )
            return save_checkpoint(run_dir, model, state, permutation, is_best=best)

        try:
            if resume_from is None:
                checkpoint()
            while state["epoch"] < epochs:
                if memory.check():
                    reason = reason or "memory_limit"
                if memory.thermal_limit_reached:
                    reason = reason or "thermal_limit"
                if time.monotonic() - start >= max_duration_minutes * 60:
                    reason = reason or "duration_limit"
                if max_steps is not None and model.steps - initial_step >= max_steps:
                    reason = reason or "max_steps"
                if reason:
                    break
                stop_at = min(state["cursor"] + batch_size, len(x))
                indices = permutation[state["cursor"] : stop_at]
                lr = learning_rate(training, model.steps)
                before = time.perf_counter()
                loss = model.train_batch(x[indices], y[indices], lr)
                session_optimizer += time.perf_counter() - before
                state["cursor"] = stop_at
                state["global_step"] = model.steps
                state["last_loss"] = loss
                state["epoch_loss_sum"] += loss * len(indices)
                state["epoch_loss_samples"] += len(indices)
                if stop_at == len(x):
                    state["epoch"] += 1
                    state["cursor"] = 0
                    permutation = rng.permutation(len(x)).astype(np.int64)
                    if training.get("validation_during_training", True):
                        val_score, val_probabilities = predict_batches(model, arrays["val"][0])
                        val_y = arrays["val"][1]
                        if kind in AUTOENCODERS:
                            val_errors = val_score
                            val_loss = float(val_score[val_y == 0].mean())
                        else:
                            val_errors = -np.log(
                                np.maximum(val_probabilities[np.arange(len(val_y)), val_y], 1e-12)
                            )
                            if kind in DEEP_KINDS:
                                val_errors = np.concatenate(
                                    [
                                        model.classification_errors(
                                            arrays["val"][0][i : i + 512], val_y[i : i + 512]
                                        )
                                        for i in range(0, len(val_y), 512)
                                    ]
                                )
                            if model.class_weights is None:
                                val_loss = float(val_errors.mean())
                            else:
                                weights = model.class_weights[val_y]
                                val_loss = float((val_errors * weights).sum() / weights.sum())
                        val_binary = (arrays["val"][1] != 0).astype(np.int64)
                        # A true calibration partition remains sealed until export.
                        calibration = (
                            None
                            if "calibration" in arrays
                            else threshold_at_fpr(val_binary, val_score)
                        )
                        from sklearn.metrics import average_precision_score

                        metric = float(average_precision_score(val_binary, val_score))
                        improved = state["best_metric"] is None or metric > state["best_metric"]
                        state["best_metric"] = metric if improved else state["best_metric"]
                        state["patience"] = 0 if improved else state["patience"] + 1
                    else:
                        metric = val_loss = val_errors = calibration = None
                        improved = True
                        state["best_metric"] = None
                        state["patience"] = 0
                    state["history"].append(
                        {
                            "epoch": state["epoch"],
                            "global_step": model.steps,
                            "validation_pr_auc": metric,
                            "validation_average_precision": metric,
                            "training_loss": state["epoch_loss_sum"]
                            / max(state["epoch_loss_samples"], 1),
                            "validation_loss": val_loss,
                            "last_learning_rate": lr,
                            "validation_unweighted_all_class_loss": float(val_errors.mean())
                            if val_errors is not None
                            else None,
                            "calibration": calibration,
                        }
                    )
                    state["epoch_loss_sum"] = 0.0
                    state["epoch_loss_samples"] = 0
                    if (
                        training.get("early_stopping_patience", 0)
                        and state["patience"] >= training["early_stopping_patience"]
                    ):
                        reason = "early_stopping"
                    checkpoint(best=improved)
                    last_checkpoint = time.monotonic()
                elif time.monotonic() - last_checkpoint >= checkpoint_every_seconds:
                    checkpoint()
                    last_checkpoint = time.monotonic()
            reason = reason or "epochs_complete"
            memory.check()
            resources.update(memory.metrics())
            latest = checkpoint()
            resources["cgroup_v2_final"] = cgroup_readback()
            report = {
                "session_id": session_id,
                "process_id": os.getpid(),
                "run_id": state["run_id"],
                "started_at_unix": started_at,
                "ended_at_unix": time.time(),
                "session_wall_seconds": time.monotonic() - start,
                "session_optimizer_seconds": session_optimizer,
                "cumulative_wall_seconds": state["wall_seconds"],
                "cumulative_optimizer_seconds": state["optimizer_seconds"],
                "epoch": state["epoch"],
                "cursor": state["cursor"],
                "global_step": model.steps,
                "stop_reason": reason,
                "dataset_sha256": state["dataset_sha256"],
                "config_sha256": config_sha,
                "best_metric": state["best_metric"],
                "checkpoint": str(latest.relative_to(run_dir)),
                "checkpoint_manifest_sha256": file_sha256(latest / "manifest.json"),
                "resources": resources,
                "used_previous_checkpoint": state.get("used_previous_checkpoint", False),
            }
            atomic_json(run_dir / "sessions" / (session_id + ".json"), report)
            atomic_json(run_dir / "session_report.json", report)
            return report
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

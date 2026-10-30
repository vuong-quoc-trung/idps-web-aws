"""Bounded request-only research fitting, checkpoint/resume and ONNX acceptance.

No formal scale admission. Supervised candidates fit the same lab examples;
public shards with benign-only annotations are used by the denoising model,
not as a source-ID shortcut for supervised labels. All use the shared scaler.
"""

import math
import os
import signal
import tempfile
import time
from pathlib import Path

import numpy as np
import onnx
import pyarrow.parquet as pq

from idps_ai.common import CLASSES, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.data.request_corpus import verify_requests
from idps_ai.data.snapshot import new_destination
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.deep import AUTOENCODERS
from idps_ai.training.generalization import binary_metrics
from idps_ai.training.models import Model
from idps_ai.training.resources import resource_envelope
from idps_ai.training.runner import environment_identity, implementation_identity
from idps_ai.training.schedule import learning_rate


def selected_training(dataset, kind):
    rows, seen = [], set()
    for row in iter_rows(Path(dataset) / "features.parquet"):
        if row["split"] != "train" or row["label"] is None:
            continue
        if kind in AUTOENCODERS:
            if row["label"] != 0:
                continue
            key = row["feature_key"]
        else:
            if row["source_id"] != "student-lab":
                continue
            key = (row["feature_key"], row["label"], row["attack_family"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if not rows:
        raise PipelineError("No eligible unique request training views")
    return (
        np.array([r["x"] for r in rows], np.float32),
        np.array([r["label"] for r in rows], np.int64),
        np.array(
            [
                CLASSES.index(r["attack_family"]) if r["attack_family"] in CLASSES else -1
                for r in rows
            ],
            np.int64,
        ),
    )


def train_request(
    dataset, output, config, epochs=2, resume=False, max_steps=None, cpus=4, diagnostic_updates=None
):
    if (
        epochs not in (1, 2)
        or cpus not in (1, 2, 4, 8)
        or max_steps is not None
        and not 1 <= max_steps <= 1024
    ):
        raise PipelineError("Request technical pilots are capped at2epochs and8CPUs")
    if diagnostic_updates not in (None, 100, 300):
        raise PipelineError(
            "Short learning-curve diagnostics are capped at100/300updates and180seconds"
        )
    dataset, output = Path(dataset).resolve(), Path(output).resolve()
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise PipelineError("Run must be outside immutable dataset")
    manifest = verify_requests(dataset)
    if manifest["rows"]["train"] > 250_000:
        raise PipelineError(
            "Request pilot capped at250k train rows; scale training remains separate"
        )
    kind = config["kind"]
    if kind not in ("deep_mlp", "residual_glu", "denoising_autoencoder"):
        raise PipelineError("Unsupported request research candidate")
    identity = {
        "dataset_sha256": manifest["dataset_sha256"],
        "config_sha256": digest(config),
        "implementation_sha256": implementation_identity(),
        "environment": environment_identity(),
        "diagnostic_updates": diagnostic_updates,
    }
    stop = [None]

    def stopped(sig, _):
        stop[0] = signal.Signals(sig).name

    old_handlers = {s: signal.signal(s, stopped) for s in (signal.SIGTERM, signal.SIGINT)}
    started = time.monotonic()
    config_training = {
        "learning_rate": config["learning_rate"],
        "scheduler": "warmup_cosine",
        "warmup_steps": config.get("warmup_steps", 5),
        "total_steps": config["total_steps"],
        "min_lr_ratio": 0.05,
    }
    try:
        with RunLock(output), resource_envelope(cpus, 16) as (guard, resources):
            x, binary, family = selected_training(dataset, kind)
            if diagnostic_updates:
                epochs = math.ceil(diagnostic_updates / math.ceil(len(x) / 128))
            if kind not in AUTOENCODERS and len(np.unique(binary)) != 2:
                raise PipelineError("Supervised request fitting needs both binary classes")
            rng = np.random.default_rng(17)
            if resume:
                loaded = load_checkpoint(output)
                model, state, permutation = loaded.model, loaded.state, loaded.permutation
                if any(state.get(k) != v for k, v in identity.items()):
                    raise PipelineError("Request resume data/config/source/environment mismatch")
                rng.bit_generator.state = state["rng"]
            else:
                if (output / "latest.json").exists():
                    raise PipelineError("Use explicit resume or a fresh run")
                objective = (
                    None
                    if kind in AUTOENCODERS
                    else {"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.2}
                )
                if objective is not None and config.get("binary_weighting") == "balanced":
                    counts = np.bincount(binary, minlength=2)
                    objective["binary_class_weights"] = (len(binary) / (2 * counts)).tolist()
                model = Model(x.shape[1], config["width"], kind, 17, objective=objective)
                permutation = rng.permutation(len(x))
                state = {
                    **identity,
                    "epoch": 0,
                    "cursor": 0,
                    "global_step": 0,
                    "history": [],
                    "optimizer_seconds": 0.0,
                    "loss_sum": 0.0,
                    "loss_rows": 0,
                    "training_views": len(x),
                    "kind": kind,
                }
            if state["epoch"] > epochs or len(permutation) != len(x):
                raise PipelineError("Request checkpoint epoch/sampler mismatch")
            reason = None
            last_checkpoint = time.monotonic()
            while state["epoch"] < epochs:
                while state["cursor"] < len(x):
                    if (
                        stop[0]
                        or time.monotonic() - started > (180 if diagnostic_updates else 480)
                        or guard.check()
                        or guard.thermal_limit_reached
                    ):
                        reason = stop[0] or "resource_or_duration_guard"
                        break
                    if max_steps is not None and model.steps >= max_steps:
                        reason = "technical_step_cap"
                        break
                    if diagnostic_updates is not None and model.steps >= diagnostic_updates:
                        reason = "diagnostic_update_cap"
                        break
                    indices = permutation[state["cursor"] : state["cursor"] + 128]
                    before = time.monotonic()
                    loss = model.train_batch(
                        x[indices],
                        family[indices],
                        learning_rate(config_training, model.steps),
                        binary_targets=binary[indices] if kind not in AUTOENCODERS else None,
                    )
                    state["optimizer_seconds"] += time.monotonic() - before
                    state["cursor"] += len(indices)
                    state["global_step"] = model.steps
                    state["loss_sum"] += loss * len(indices)
                    state["loss_rows"] += len(indices)
                    if time.monotonic() - last_checkpoint >= 30:
                        state["rng"] = rng.bit_generator.state
                        save_checkpoint(output, model, state, permutation)
                        last_checkpoint = time.monotonic()
                if reason:
                    break
                state["epoch"] += 1
                state["history"].append(
                    {
                        "epoch": state["epoch"],
                        "training_loss": state["loss_sum"] / state["loss_rows"],
                        "step": model.steps,
                    }
                )
                state.update(cursor=0, loss_sum=0.0, loss_rows=0)
                permutation = rng.permutation(len(x))
            state.update(rng=rng.bit_generator.state, stop_reason=reason or "epochs_complete")
            save_checkpoint(output, model, state, permutation)
        result = {
            "kind": kind,
            "epoch": state["epoch"],
            "steps": model.steps,
            "stop_reason": state["stop_reason"],
            "unique_training_views": len(x),
            "optimizer_seconds": state["optimizer_seconds"],
            "history": state["history"],
            "resources": resources,
            "formal_training": False,
        }
        atomic_json(output / "training-result.json", result)
        return result
    finally:
        for s, h in old_handlers.items():
            signal.signal(s, h)


def benign_threshold(scores, alpha=0.01):
    scores = np.asarray(scores, np.float32)
    if not len(scores) or not np.isfinite(scores).all() or not 0 < alpha < 1:
        raise PipelineError("Invalid benign-only calibration sample")
    rank = min(len(scores), math.ceil((len(scores) + 1) * (1 - alpha)))
    q = np.sort(scores)[rank - 1]
    threshold = float(np.nextafter(q, np.float32(np.inf)))
    return {
        "threshold": threshold,
        "benign_count": len(scores),
        "target_fpr": alpha,
        "calibration_fpr": float(np.mean(scores >= threshold)),
        "limitation": "Empirical correlated request/view sample, not a production exchangeability guarantee",
    }


def export_request(dataset, checkpoint, output, cpus=4):
    dataset = Path(dataset)
    manifest = verify_requests(dataset)
    loaded = load_checkpoint(checkpoint)
    if loaded.state["dataset_sha256"] != manifest["dataset_sha256"]:
        raise PipelineError("Request checkpoint/dataset mismatch")
    output = new_destination(output)
    model = loaded.model
    spec = load_json(dataset / "feature_spec.json")
    with tempfile.TemporaryDirectory(prefix=".request-export-", dir=output.parent) as temporary:
        work = Path(temporary)
        onnx.save_model(graph_for(model), work / "model.onnx")
        atomic_json(work / "feature_spec.json", spec)
        session = cpu_session(work / "model.onnx", cpus)
        calibration = {}
        validation = []
        maximum = 0.0
        parity_rows = 0
        for row_batch in pq.ParquetFile(dataset / "features.parquet").iter_batches(
            batch_size=512, use_threads=False
        ):
            rows = row_batch.to_pylist()
            x = np.asarray([r["x"] for r in rows], np.float32)
            native = model.predict(x)
            exported = session.run(None, {"input": x})
            for a, b in zip(native, exported):
                if (
                    not np.isfinite(a).all()
                    or not np.isfinite(b).all()
                    or not np.allclose(a, b, rtol=1e-5, atol=1e-6)
                ):
                    raise PipelineError("Request ONNX parity failed")
                maximum = max(maximum, float(np.max(np.abs(a - b))))
            parity_rows += len(rows)
            for r, score in zip(rows, exported[0]):
                if r["split"] == "calibration" and r["label"] == 0:
                    calibration.setdefault(r["source_id"], []).append(float(score))
                if r["split"] == "val" and r["label"] is not None:
                    validation.append((r, float(score)))
        fitted = {s: benign_threshold(v) for s, v in calibration.items()}
        if not fitted:
            raise PipelineError("No benign calibration sources")
        threshold = max(v["threshold"] for v in fitted.values())
        metrics = binary_metrics(
            [r["label"] for r, s in validation], [s for r, s in validation], threshold
        )
        by_source = {
            s: binary_metrics(
                [r["label"] for r, x in validation if r["source_id"] == s],
                [x for r, x in validation if r["source_id"] == s],
                threshold,
            )
            for s in sorted({r["source_id"] for r, x in validation})
        }
        card = {
            "format_version": 1,
            "profile": manifest["profile"],
            "model_kind": model.kind,
            "dataset_sha256": manifest["dataset_sha256"],
            "checkpoint_manifest_sha256": file_sha256(loaded.path / "manifest.json"),
            "feature_version": spec["feature_version"],
            "input_shape": [None, model.input_dim],
            "input_dtype": "float32",
            "threshold": threshold,
            "calibration": fitted,
            "calibration_policy": "max of independently source-fitted benign quantiles; no attack scores choose threshold",
            "validation": metrics,
            "validation_by_source": by_source,
            "parity": {
                "rows": parity_rows,
                "all_rows_match": True,
                "max_absolute_error": maximum,
                "rtol": 1e-5,
                "atol": 1e-6,
            },
            "files": {f: file_sha256(work / f) for f in ["model.onnx", "feature_spec.json"]},
            "objective": model.metadata().get("objective"),
            "classes": list(CLASSES),
            "score_semantics": "MSE reconstruction, not attack probability"
            if model.kind in AUTOENCODERS
            else "1-P(benign); public unknown family never imputed",
            "family_output": "disabled; conditional family heads lack independent validation",
            "champion_selected": False,
            "deployment_status": "offline research candidate only",
        }
        atomic_json(work / "model_manifest.json", card)
        os.replace(work, output)
    return card

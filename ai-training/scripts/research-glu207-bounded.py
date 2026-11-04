"""Frozen train-only GLU207 research run; never scores validation or test."""

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.models import Model
from idps_ai.training.resources import resource_envelope
from idps_ai.training.runner import implementation_identity
from idps_ai.training.schedule import learning_rate

AI_ROOT = Path(__file__).resolve().parents[1]


def load_train(plan):
    dataset = AI_ROOT / plan["dataset"]
    manifest = load_json(dataset / "dataset_manifest.json")
    if (
        file_sha256(dataset / "features.parquet") != plan["features_sha256"]
        or file_sha256(dataset / "feature_spec.json") != plan["spec_sha256"]
        or file_sha256(dataset / "dataset_manifest.json") != plan["manifest_sha256"]
        or manifest["dataset_sha256"] != plan["dataset_sha256"]
        or implementation_identity() != plan["implementation_sha256"]
    ):
        raise PipelineError("Frozen dataset, manifest, feature spec, or implementation changed")
    spec = load_json(dataset / "feature_spec.json")
    if spec["feature_version"] != "ai-features-5" or len(spec["columns"]) != 207:
        raise PipelineError("GLU207 feature order/version mismatch")
    pf = pq.ParquetFile(dataset / "features.parquet")
    xs, ys, families, views = [], [], Counter(), {}
    for group in range(pf.num_row_groups):
        # The boundary row group contains train and val. Split is checked per row;
        # no non-train vector or label is admitted to model input or diagnostics.
        rows = pf.read_row_group(group, columns=["split", "label", "attack_family", "x"])
        for row in rows.to_pylist():
            if row["split"] != "train":
                continue
            vector = np.asarray(row["x"], dtype=np.float32)
            label = int(row["label"])
            if vector.shape != (207,) or not np.isfinite(vector).all() or not 0 <= label < 8:
                raise PipelineError("Invalid train vector or label")
            digest = hashlib.sha256(vector.tobytes()).digest()
            views.setdefault(digest, set()).add(label)
            xs.append(vector)
            ys.append(label)
            families[row["attack_family"]] += 1
    if len(xs) != plan["train_rows"] or len(views) != plan["unique_views"]:
        raise PipelineError("Train count/view contract changed")
    conflicts = sum(len(labels) > 1 for labels in views.values())
    if conflicts != plan["conflicting_views"]:
        raise PipelineError("Train view-label conflict count changed")
    if conflicts:
        raise PipelineError("Conflicting supervised train views require explicit quarantine")
    if dict(families) != plan["family_counts"]:
        raise PipelineError("Train family distribution changed")
    return np.stack(xs), np.asarray(ys, dtype=np.int64)


def permutations(count, epochs, seed):
    rng = np.random.default_rng(seed)
    return np.concatenate([rng.permutation(count) for _ in range(epochs)]).astype(np.int64)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--through-epoch", type=int, required=True, choices=(1, 2))
    args = parser.parse_args()
    root = AI_ROOT / ".artifacts/research_glu207_bounded_final_20261104"
    plan = load_json(root / "freeze.json")
    if file_sha256(__file__) != plan["script_sha256"]:
        raise PipelineError("Frozen training script changed")
    x, y = load_train(plan)
    training = plan["training"]
    epoch_batches = math.ceil(len(x) / training["batch_size"])
    order = permutations(len(x), training["epochs"], training["seed"])
    run = root / "run"
    start = time.monotonic()
    losses = []
    with RunLock(run), resource_envelope(4, 16) as (guard, resources):
        if (run / "latest.json").exists():
            loaded = load_checkpoint(run)
            model = loaded.model
            state = loaded.state
            if (
                state.get("freeze_sha256") != file_sha256(root / "freeze.json")
                or state.get("script_sha256") != plan["script_sha256"]
                or state.get("dataset_sha256") != plan["dataset_sha256"]
                or not np.array_equal(loaded.permutation, order)
                or model.kind != "residual_glu"
                or model.input_dim != 207
                or model.steps != state["global_step"]
            ):
                raise PipelineError("Checkpoint not compatible with frozen research run")
            first_epoch = state["completed_epochs"]
        else:
            model = Model(207, 1024, "residual_glu", training["seed"])
            first_epoch = 0
        if sum(p.size for p in model.parameters.values()) != 9_675_784:
            raise PipelineError("Incorrect model parameter count")
        if args.through_epoch <= first_epoch:
            raise PipelineError("Requested epoch already completed")
        for epoch in range(first_epoch, args.through_epoch):
            epoch_losses = []
            for batch in range(epoch_batches):
                if guard.check() or guard.thermal_limit_reached:
                    raise PipelineError("Resource/thermal guard stopped training")
                if time.monotonic() - start > training["max_seconds_per_invocation"]:
                    raise PipelineError("Bounded invocation time exceeded")
                offset = epoch * len(x) + batch * training["batch_size"]
                ids = order[offset : min(offset + training["batch_size"], (epoch + 1) * len(x))]
                loss = float(
                    model.train_batch(x[ids], y[ids], learning_rate(training, model.steps))
                )
                if not math.isfinite(loss):
                    raise PipelineError("Non-finite loss")
                epoch_losses.append(loss)
            losses.extend(epoch_losses)
            state = {
                "purpose": "bounded_research_fit_development_train_only",
                "freeze_sha256": file_sha256(root / "freeze.json"),
                "script_sha256": plan["script_sha256"],
                "dataset_sha256": plan["dataset_sha256"],
                "completed_epochs": epoch + 1,
                "global_step": model.steps,
                "train_rows_seen": (epoch + 1) * len(x),
                "epoch_mean_loss": float(np.mean(epoch_losses)),
                "epoch_first_20_loss": float(np.mean(epoch_losses[:20])),
                "epoch_last_20_loss": float(np.mean(epoch_losses[-20:])),
                "non_train_rows_used": 0,
                "scope": "research_fitting_not_independent_evaluation",
            }
            checkpoint = save_checkpoint(run, model, state, order)
            readback = load_checkpoint(run)
            if readback.model.steps != model.steps or not all(
                np.array_equal(readback.model.arrays()[name], array)
                for name, array in model.arrays().items()
            ):
                raise PipelineError("Checkpoint parameter/optimizer readback mismatch")
            guard.check()
            stage = {
                "completed_epochs": epoch + 1,
                "updates": model.steps,
                "train_rows_seen": state["train_rows_seen"],
                "epoch_mean_loss": state["epoch_mean_loss"],
                "epoch_first_20_loss": state["epoch_first_20_loss"],
                "epoch_last_20_loss": state["epoch_last_20_loss"],
                "checkpoint": str(checkpoint),
                "checkpoint_manifest_sha256": file_sha256(checkpoint / "manifest.json"),
                "readback": "PASS_PARAMETERS_AND_ADAM_STATE_EXACT",
                "elapsed_seconds": time.monotonic() - start,
                "resource_guard": guard.metrics(),
                "resource_envelope": resources,
            }
            atomic_json(root / f"epoch-{epoch + 1}.json", stage)
            print(
                json.dumps(
                    {
                        k: stage[k]
                        for k in (
                            "completed_epochs",
                            "updates",
                            "epoch_mean_loss",
                            "elapsed_seconds",
                        )
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()

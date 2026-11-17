"""Second data-recovery round, reusing the fixed R26 URI100 training machinery."""

# isort: skip_file

import argparse
import os
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from r26_common import SEED, atomic_json, check, file_sha256, read, status
from r26_recovery_pilot import data, warm
from r26_learning import BATCH, assessment, epoch, make_training, schedule_for
from r26_train import export
from idps_ai.common import digest
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from r16_train import batched_predict
from r18_train import WeightedSwiGLU, logistic_onnx

EPOCHS, PATIENCE = 24, 5


def run(parent):
    check(
        read(parent / "source2-recovery/pilot.json")["full_training_allowed"],
        "Three-source pilot did not justify full training",
    )
    started = time.monotonic()
    out = parent / "augmentation-b"
    out.mkdir(exist_ok=True)
    train, tune = data(parent, pilot=False)
    x, y, weight, sources = make_training(train, 100)
    schedule = schedule_for(len(y), EPOCHS)
    source_names = (
        "WAF_PUBLISHER_NORMAL_ANOMALOUS",
        "NOTES_SYNTHETIC_BENIGN_MALICIOUS",
        "SRBH_PUBLISHER_CAPEC_NORMAL",
    )
    for report, name in zip(sources, source_names, strict=True):
        report["label_task"] = name
    plan = {
        "schema_width": 100,
        "parameters": 400256,
        "seed": SEED,
        "epochs": EPOCHS,
        "patience": PATIENCE,
        "batch_cells": BATCH,
        "schedule": schedule,
        "source_class_balance": "Equal mass per source/class with new-vector capped group weighting",
        "sources": sources,
        "fit_originals": sum(s["originals"] for s in sources),
        "warm_start": read(parent / "model-selection.json")["best_checkpoint"],
        "regularization": warm(parent).regularization,
        "code_sha256": file_sha256(__file__),
        "learning_sha256": file_sha256(Path(__file__).with_name("r26_learning.py")),
        "adapter_sha256": file_sha256(Path(__file__).with_name("r26_recovery_pilot.py")),
        "waf_sha256": read(parent / "data-v2/waf-manifest.json")["dataset_sha256"],
        "notes_manifest_sha256": file_sha256(parent / "notes/manifest.json"),
        "source2_manifest_sha256": file_sha256(parent / "source2-recovery/manifest.json"),
        "pilot_sha256": file_sha256(parent / "source2-recovery/pilot.json"),
        "selection": "Same R26 TUNING-only macro source URI-only recall under global per-source dual FPR<=1%, then vector recall, AP",
        "new_SOURCE2_test_or_old_NOTES_test_opened_for_training": False,
        "native_ground_truth": False,
    }
    path = out / "training-plan.json"
    if path.exists():
        check(read(path) == plan, "Recovery training binding changed")
    else:
        atomic_json(path, plan)
    binding = digest(plan)
    root = out / "training/model"
    batches = (len(y) + BATCH - 1) // BATCH
    with RunLock(root):
        current, best_epoch, best, history = 0, 0, (-1.0, -1.0, -1.0), []
        model = warm(parent)
        if (root / "latest.json").exists():
            saved = load_checkpoint(root)
            state = saved.state
            check(
                not saved.used_previous
                and state["binding"] == binding
                and saved.model.steps == state["epoch"] * batches,
                "Recovery checkpoint ownership/cursor",
            )
            model = WeightedSwiGLU.from_arrays(saved.model.metadata(), saved.model.arrays())
            current, best_epoch, best, history = (
                state["epoch"],
                state["best_epoch"],
                tuple(state["best"]),
                state["history"],
            )
        while current < EPOCHS and current - best_epoch < PATIENCE:
            permutation, loss = epoch(model, x, y, weight, current, schedule)
            current += 1
            report = assessment(lambda a: batched_predict(model, a), tune, 100)
            rank = tuple(report["selection_rank"])
            improved = rank > best
            if improved:
                best, best_epoch = rank, current
            history.append({"epoch": current, "loss": loss, "step": model.steps, "tuning": report})
            save_checkpoint(
                root,
                model,
                {
                    "binding": binding,
                    "epoch": current,
                    "best_epoch": best_epoch,
                    "best": list(best),
                    "history": history,
                    "last_loss": loss,
                },
                permutation,
                is_best=improved,
            )
            elapsed = time.monotonic() - started
            status(
                out,
                "RUNNING",
                "THREE_SOURCE_TRAIN",
                epoch=current,
                best_epoch=best_epoch,
                optimizer_step=model.steps,
                fit_originals=plan["fit_originals"],
                eta_seconds=(EPOCHS - current) * elapsed / current,
            )
        selected = read(root / "best.json")
        model = load_checkpoint(root / selected["path"]).model
    bundle = out / "bundle"
    bundle.mkdir(exist_ok=True)
    export(bundle / "swiglu.onnx", graph_for(model))
    session = cpu_session(bundle / "swiglu.onnx", 1)
    examples = np.concatenate([f["x"][:, :100] for f in tune.values()])
    expected = batched_predict(model, examples)
    actual = session.run(["score"], {"input": examples})[0]
    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-6)
    neural = assessment(lambda a: session.run(["score"], {"input": a})[0], tune, 100)
    baseline = LogisticRegression(C=1, max_iter=600, random_state=SEED).fit(
        x, y, sample_weight=weight
    )
    check(baseline.n_iter_.max() < 600, "Recovery logistic convergence")
    graph = logistic_onnx(baseline)
    graph.graph.input[0].type.tensor_type.shape.dim[1].dim_value = 100
    export(bundle / "logistic.onnx", graph)
    simple_session = cpu_session(bundle / "logistic.onnx", 1)
    simple = assessment(lambda a: simple_session.run(["score"], {"input": a})[0], tune, 100)
    old_session = cpu_session(parent / "bundle/swiglu.onnx", 1)
    previous = assessment(lambda a: old_session.run(["score"], {"input": a})[0], tune, 100)
    models = {"swiglu": neural, "logistic": simple}
    choice = max(models, key=lambda name: (models[name]["selection_rank"], name == "logistic"))
    atomic_json(
        out / "model-selection.json",
        {
            "selected": choice,
            "models": models,
            "baseline_R26A_same_tuning": previous,
            "sha256": {name: file_sha256(bundle / f"{name}.onnx") for name in models},
            "best_epoch": best_epoch,
            "completed_epochs": current,
            "best_checkpoint": selected,
            "fit_originals": plan["fit_originals"],
            "schema_width": 100,
            "binding": binding,
            "numpy_onnx_max_abs": float(np.max(np.abs(expected - actual))),
            "seconds": time.monotonic() - started,
            "selection_used_any_research_test": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)

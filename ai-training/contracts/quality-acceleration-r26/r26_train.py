"""Full source-balanced URI100 fitting, immutable checkpoints and ONNX export."""

# isort: skip_file

import argparse
import os
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from r26_common import SEED, atomic_json, check, file_sha256, read, status
from r26_learning import BATCH, assessment, epoch, make_training, schedule_for, source_data, warm
from idps_ai.common import digest
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from r16_train import batched_predict
from r18_train import WeightedSwiGLU, logistic_onnx

EPOCHS, PATIENCE = 24, 5


def export(path, graph):
    content = graph.SerializeToString()
    if path.exists():
        check(path.read_bytes() == content, "Immutable ONNX artifact differs")
    else:
        pending = path.with_suffix(".pending")
        pending.write_bytes(content)
        pending.replace(path)


def run(out):
    started = time.monotonic()
    pilot = read(out / "pilot.json")
    check(pilot["full_training_allowed"], "Pilot has not established a training benefit")
    check(
        read(out / "cross-source-overlap.json")["status"] == "PASS_NO_EXACT_OVERLAP",
        "Original identity reconciliation",
    )
    width = int(pilot["selected"].rsplit("_", 1)[1])
    train, tune = source_data(out)
    x, y, weight, data_report = make_training(train, width)
    schedule = schedule_for(len(y), EPOCHS)
    template = warm(width)
    plan = {
        "schema_width": width,
        "seed": SEED,
        "batch_cells": BATCH,
        "parameters": sum(v.size for v in template.parameters.values()),
        "max_epochs": EPOCHS,
        "patience": PATIENCE,
        "schedule": schedule,
        "regularization": template.regularization,
        "objective": template.objective,
        "source_weighting": "Equal source and class mass; group mass min(8,sqrt(n)); retain all publisher labels",
        "sources": data_report,
        "fit_distinct_originals": sum(row["originals"] for row in data_report),
        "source_labels": [
            "WAF publisher normal/anomalous",
            "Notes synthetic publisher benign/malicious",
        ],
        "canonical_native_train": 0,
        "selection": "TUNING macro source URI-only recall at one global per-source dual FPR<=1%, vector recall, AP; earlier on ties",
        "calibration_or_research_test_read": False,
        "code_sha256": file_sha256(__file__),
        "learning_code_sha256": file_sha256(Path(__file__).with_name("r26_learning.py")),
        "pilot_sha256": file_sha256(out / "pilot.json"),
        "waf_manifest_sha256": file_sha256(out / "data-v2/waf-manifest.json"),
        "notes_manifest_sha256": file_sha256(out / "notes/manifest.json"),
        "overlap_sha256": file_sha256(out / "cross-source-overlap.json"),
    }
    plan_path = out / "training-plan.json"
    if plan_path.exists():
        check(read(plan_path) == plan, "Frozen training plan differs")
    else:
        atomic_json(plan_path, plan)
    binding = digest(plan)
    root = out / "training/model"
    batches = (len(y) + BATCH - 1) // BATCH
    with RunLock(root):
        current_epoch, best_epoch, best = 0, 0, (-1.0, -1.0, -1.0)
        history = []
        model = template
        if (root / "latest.json").exists():
            saved = load_checkpoint(root)
            state = saved.state
            check(not saved.used_previous and state["binding"] == binding, "Checkpoint binding")
            check(saved.model.steps == state["epoch"] * batches, "Checkpoint cursor")
            model = WeightedSwiGLU.from_arrays(saved.model.metadata(), saved.model.arrays())
            current_epoch, best_epoch = state["epoch"], state["best_epoch"]
            history, best = state["history"], tuple(state["best"])
        while current_epoch < EPOCHS and current_epoch - best_epoch < PATIENCE:
            permutation, loss = epoch(model, x, y, weight, current_epoch, schedule)
            current_epoch += 1
            report = assessment(lambda values: batched_predict(model, values), tune, width)
            rank = tuple(report["selection_rank"])
            improved = rank > best
            if improved:
                best, best_epoch = rank, current_epoch
            history.append(
                {"epoch": current_epoch, "loss": loss, "steps": model.steps, "tuning": report}
            )
            save_checkpoint(
                root,
                model,
                {
                    "binding": binding,
                    "epoch": current_epoch,
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
                "FULL_TRAIN",
                epoch=current_epoch,
                max_epochs=EPOCHS,
                best_epoch=best_epoch,
                optimizer_step=model.steps,
                original_fit=plan["fit_distinct_originals"],
                effective_originals_per_second=plan["fit_distinct_originals"]
                * current_epoch
                / max(elapsed, 0.001),
                eta_seconds=(EPOCHS - current_epoch) * elapsed / current_epoch,
            )
        best_pointer = read(root / "best.json")
        best_model = load_checkpoint(root / best_pointer["path"]).model
    bundle = out / "bundle"
    bundle.mkdir(exist_ok=True)
    export(bundle / "swiglu.onnx", graph_for(best_model))
    check_model = np.concatenate([frame["x"][:, :width] for frame in tune.values()])
    expected = batched_predict(best_model, check_model)
    actual = cpu_session(bundle / "swiglu.onnx", 1).run(["score"], {"input": check_model})[0]
    np.testing.assert_allclose(expected, actual, rtol=1e-5, atol=1e-6)
    neural = assessment(
        lambda a: cpu_session(bundle / "swiglu.onnx", 1).run(["score"], {"input": a})[0],
        tune,
        width,
    )
    logistic = LogisticRegression(C=1, max_iter=600, random_state=SEED).fit(
        x, y, sample_weight=weight
    )
    check(logistic.n_iter_.max() < 600, "Full logistic convergence")
    graph = logistic_onnx(logistic)
    graph.graph.input[0].type.tensor_type.shape.dim[1].dim_value = width
    export(bundle / "logistic.onnx", graph)
    ls = cpu_session(bundle / "logistic.onnx", 1)
    np.testing.assert_allclose(
        ls.run(["score"], {"input": check_model})[0],
        logistic.predict_proba(check_model)[:, 1],
        rtol=1e-5,
        atol=1e-6,
    )
    simple = assessment(lambda a: ls.run(["score"], {"input": a})[0], tune, width)
    models = {"swiglu": neural, "logistic": simple}
    selected = max(models, key=lambda n: (models[n]["selection_rank"], n == "logistic"))
    atomic_json(
        out / "model-selection.json",
        {
            "selected": selected,
            "models": models,
            "width": width,
            "sha256": {name: file_sha256(bundle / f"{name}.onnx") for name in models},
            "best_checkpoint": best_pointer,
            "best_epoch": best_epoch,
            "completed_epochs": current_epoch,
            "fit_originals": plan["fit_distinct_originals"],
            "numpy_onnx_max_abs": float(np.max(np.abs(expected - actual))),
            "binding": binding,
            "seconds": time.monotonic() - started,
            "research_test_or_calibration_used_for_selection": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)

# isort: skip_file

"""One justified continuation from B16, in a new checkpoint namespace."""

import math
import os
import shutil
import time

import numpy as np
from sklearn.linear_model import LogisticRegression

from common import PARENT, atomic_json, check, file_sha256, output_arg, read, status
from idps_ai.common import digest
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import (
    RunLock,
    load_checkpoint,
    save_checkpoint,
    validate_generation,
)
from r16_train import batched_predict
from r18_train import WeightedSwiGLU, logistic_onnx
from r26_learning import BATCH, assessment, epoch, make_training
from r26_recovery_pilot import data
from r26_train import export


def clone_checkpoint(source, destination, expected):
    destination.mkdir(parents=True, exist_ok=True)
    for label, pointer in expected.items():
        origin = source / pointer["path"]
        validate_generation(origin, pointer["manifest_sha256"])
        target = destination / pointer["path"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".copying")
            shutil.copytree(origin, temporary)
            validate_generation(temporary, pointer["manifest_sha256"])
            temporary.replace(target)
        validate_generation(target, pointer["manifest_sha256"])
        if not (destination / f"{label}.json").exists():
            atomic_json(destination / f"{label}.json", pointer)


def run(out):
    began = time.monotonic()
    audit = read(out / "checkpoint-audit.json")
    check(audit["continuation_justified_by_TUNING_only"], "B16 continuation not justified")
    plan = read(PARENT / "augmentation-b/training-plan.json")
    check(digest(plan) == audit["binding"], "Original training binding changed")
    train, tune = data(PARENT, False)
    x, y, weights, sources = make_training(train, 100)
    root = out / "training/model"
    execution = {
        "parent_plan_sha256": audit["original_plan_sha256"],
        "original_binding": audit["binding"],
        "parent_checkpoint": audit["pointers"]["latest"],
        "threads": int(os.environ["OPENBLAS_NUM_THREADS"]),
        "numeric_scope": "Preserve parent weights, Adam, step, seed, sampler and scheduler; BLAS thread count follows bounded benchmark. Bit-exact replay is within this declared thread configuration.",
        "max_additional_epochs": 8,
        "max_epochs_total": 24,
        "patience": 5,
        "code_sha256": file_sha256(__file__),
        "calibration_or_test_used": False,
    }
    binding = digest(execution)
    if (out / "continuation-plan.json").exists():
        check(read(out / "continuation-plan.json") == execution, "Continuation execution binding")
    else:
        atomic_json(out / "continuation-plan.json", execution)
    with RunLock(root):
        clone_checkpoint(PARENT / "augmentation-b/training/model", root, audit["pointers"])
        saved = load_checkpoint(root)
        check(
            not saved.used_previous and saved.state["binding"] == audit["binding"],
            "Continuation cursor invalid",
        )
        if saved.state["epoch"] > 16:
            check(
                saved.state["r261_environment_binding"] == binding,
                "Continuation environment changed",
            )
        model = WeightedSwiGLU.from_arrays(saved.model.metadata(), saved.model.arrays())
        current, best_epoch = saved.state["epoch"], saved.state["best_epoch"]
        best, history = tuple(saved.state["best"]), saved.state["history"]
        check(model.steps == current * math.ceil(len(y) / BATCH), "Continuation optimizer step")
        while current < 24 and current - best_epoch < 5:
            permutation, loss = epoch(model, x, y, weights, current, plan["schedule"])
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
                    "binding": audit["binding"],
                    "r261_environment_binding": binding,
                    "epoch": current,
                    "best_epoch": best_epoch,
                    "best": list(best),
                    "history": history,
                    "last_loss": loss,
                },
                permutation,
                is_best=improved,
            )
            status(
                out,
                "RUNNING",
                "CONTINUATION",
                epoch=current,
                optimizer_step=model.steps,
                best_epoch=best_epoch,
                fit_originals=433261,
                eta_seconds=(24 - current) * (time.monotonic() - began) / max(1, current - 16),
            )
        selected = read(root / "best.json")
        best_model = load_checkpoint(root / selected["path"]).model
    bundle = out / "bundle"
    export(bundle / "b-final.onnx", graph_for(best_model))
    session = cpu_session(bundle / "b-final.onnx", 1)
    examples = np.concatenate([frame["x"][:, :100] for frame in tune.values()])
    expected = batched_predict(best_model, examples)
    actual = session.run(["score"], {"input": examples})[0]
    np.testing.assert_allclose(expected, actual, rtol=1e-5, atol=1e-6)
    neural = assessment(lambda a: session.run(["score"], {"input": a})[0], tune, 100)
    baseline = LogisticRegression(C=1, max_iter=600, random_state=2601).fit(
        x, y, sample_weight=weights
    )
    check(baseline.n_iter_.max() < 600, "Logistic did not converge")
    graph = logistic_onnx(baseline)
    graph.graph.input[0].type.tensor_type.shape.dim[1].dim_value = 100
    export(bundle / "logistic.onnx", graph)
    simple_session = cpu_session(bundle / "logistic.onnx", 1)
    simple = assessment(lambda a: simple_session.run(["score"], {"input": a})[0], tune, 100)
    models = {
        "B_FINAL": neural,
        "LOGISTIC": simple,
        "B16": audit["matched_TUNING"]["B16"],
        "R26A": audit["matched_TUNING"]["R26A"],
    }
    selected_name = max(
        models, key=lambda name: (models[name]["selection_rank"], name == "LOGISTIC")
    )
    atomic_json(
        out / "model-selection.json",
        {
            "selected": selected_name,
            "models": models,
            "best_checkpoint": selected,
            "best_epoch": best_epoch,
            "completed_epochs": current,
            "continued_from_epoch": 16,
            "initial_step": 400,
            "final_step": model.steps,
            "fit_originals": 433261,
            "parameters": 400256,
            "schema": "URI100",
            "source_counts": sources,
            "continuation_binding": binding,
            "numpy_onnx_max_abs": float(np.max(np.abs(expected - actual))),
            "sha256": {
                name: file_sha256(bundle / filename)
                for name, filename in (
                    ("B_FINAL", "b-final.onnx"),
                    ("B16", "b16.onnx"),
                    ("LOGISTIC", "logistic.onnx"),
                )
            },
            "seconds": time.monotonic() - began,
            "TEST_or_CAL_used_to_select": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

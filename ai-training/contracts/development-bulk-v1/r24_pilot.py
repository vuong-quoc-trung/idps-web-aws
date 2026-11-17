"""Short warm-start architecture probe and separate checkpoint resume audit."""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import onnx
from r16_train import batched_predict
from r18_data import check, read, status
from r18_train import WeightedSwiGLU
from r20_quality import PINS, R19
from r21_quality import R20, R20_ONNX
from r24_eval import evaluate
from sklearn.linear_model import LogisticRegression

from idps_ai.common import REPO_ROOT, atomic_json, digest, file_sha256
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.schedule import learning_rate

SEED, BATCH = 2401, 2048
ROOT = R19 / "training/model"
EPOCHS = 2
ARCH = {"core": "residual_glu", "width": 204, "inputs": 100, "parameters": 400256}


def data(out):
    manifest = read(out / "dataset-manifest.json")
    dataset = out / "publisher-r24-uri100.npz"
    check(
        manifest["data_sha256"] == file_sha256(dataset)
        and manifest["fit_uri100"]["originals"] == 400_000
        and not manifest["roles"]["protected_roles_read"],
        "R24 development dataset binding",
    )
    fields = (
        "pilot_fit_x",
        "pilot_fit_y",
        "pilot_fit_mass",
        "pilot_lexical",
        "tune_x",
        "tune_y",
        "tune_groups",
        "tune_context",
        "binary_class_weights",
    )
    with np.load(dataset, allow_pickle=False) as rows:
        return {k: rows[k] for k in fields}


def anchor():
    check(
        file_sha256(ROOT / "best.json") == PINS["training/model/best.json"],
        "R19 best pointer differs",
    )
    selected = read(ROOT / "best.json")
    directory = ROOT / selected["path"]
    check(
        file_sha256(directory / "manifest.json") == selected["manifest_sha256"],
        "R19 checkpoint pin differs",
    )
    result = load_checkpoint(directory)
    check(result.model.steps == selected["global_step"] == 55, "Unexpected warm-start cursor")
    return result.model, selected["manifest_sha256"]


def warm_start(source, width, balance):
    objective = dict(source.objective, binary_class_weights=balance.tolist())
    regularization = {
        name: source.regularization[name] for name in ("dropout", "label_smoothing", "weight_decay")
    }
    model = WeightedSwiGLU(
        width, ARCH["width"], ARCH["core"], SEED, objective=objective, regularization=regularization
    )
    for name, value in source.parameters.items():
        if name == "Win":
            model.parameters[name].fill(0)
            model.parameters[name][: len(value)] = value
        else:
            model.parameters[name][:] = value
    return model


def ep(model, x, y, mass, epoch, schedule):
    idx = np.random.default_rng(SEED + epoch).permutation(len(y))
    losses = [
        model.train_original_batch(
            x[rows], y[rows], mass[rows], learning_rate(schedule, model.steps)
        )
        for rows in np.array_split(idx, int(np.ceil(len(idx) / BATCH)))
    ]
    return idx, float(np.mean(losses))


def run(out):
    started = time.monotonic()
    status(out, "R24_ARCHITECTURE_PILOT")
    rows = data(out)
    x, y, mass, tune, yt, groups, context, balance = (
        rows[k]
        for k in (
            "pilot_fit_x",
            "pilot_fit_y",
            "pilot_fit_mass",
            "tune_x",
            "tune_y",
            "tune_groups",
            "tune_context",
            "binary_class_weights",
        )
    )
    source, source_sha = anchor()
    check(
        file_sha256(R19 / "bundle/swiglu.onnx") == PINS["bundle/swiglu.onnx"]
        and file_sha256(R20 / "bundle/swiglu.onnx") == R20_ONNX,
        "ONNX baseline binding",
    )
    schedule = {
        "scheduler": "warmup_cosine",
        "learning_rate": 0.00015,
        "warmup_steps": 2,
        "total_steps": EPOCHS * int(np.ceil(len(y) / BATCH)),
        "min_lr_ratio": 0.1,
    }
    plan = {
        "dataset_sha256": file_sha256(out / "publisher-r24-uri100.npz"),
        "dataset_manifest_sha256": file_sha256(out / "dataset-manifest.json"),
        "code_sha256": file_sha256(__file__),
        "R19_checkpoint_sha256": source_sha,
        "R20_onnx_sha256": R20_ONNX,
        "architecture": ARCH,
        "seed": SEED,
        "batch_max": BATCH,
        "weighting": "Capped parent URI76 mass; preserve label proportions and R19 class balance",
        "new_dimensions": "Initialize Win rows 76:100 to zero; reset Adam moments for both warm-start arms",
        "optimizer": "Repository float64 accumulation, AdamW beta 0.9/0.999, same R19 regularization and binary loss",
        "regularization": source.regularization,
        "schedule": schedule,
        "pilot_epochs": EPOCHS,
        "comparisons": "Pooled matched FP budgets phase-specific descriptive only; 5-fold grouped threshold transfer from four folds to one without breaking ties",
        "selection": "Favor consistency over thresholds across folds, both budgets and major workflow strata; evaluate no independent TEST and make no release claim",
    }
    with RunLock(out / "training"):
        plan_path = out / "pilot-plan.json"
        check(not plan_path.exists(), "R24 pilot plan already committed")
        atomic_json(plan_path, plan)
        arms = {}
        for name, baseline in (
            ("R20_isotonic", R20 / "bundle/swiglu.onnx"),
            ("R19_raw", R19 / "bundle/swiglu.onnx"),
        ):
            vector = tune[:, :76]
            scores = cpu_session(baseline, 1).run(["score"], {"input": vector})[0]
            arms[name] = evaluate(vector, yt, scores, groups, context)
        logit_weight = mass * balance[y]
        for name, width in (
            ("logistic_uri76", 76),
            ("logistic_structure", 100),
            ("logistic_symbol_ngram", 204),
        ):
            train = (
                x[:, :width]
                if width != 204
                else np.column_stack(
                    (x[:, :76], rows["pilot_lexical"][: len(x)].astype(np.float32) / 15)
                )
            )
            valid = (
                tune[:, :width]
                if width != 204
                else np.column_stack(
                    (tune[:, :76], rows["pilot_lexical"][len(x) :].astype(np.float32) / 15)
                )
            )
            model = LogisticRegression(max_iter=600, C=1, random_state=SEED).fit(
                train, y, sample_weight=logit_weight
            )
            check(model.n_iter_.max() < 600, "Logistic model did not converge")
            arms[name] = evaluate(
                valid, yt, model.predict_proba(valid)[:, 1].astype(np.float32), groups, context
            )
        transfer = {}
        for name, width in (("swiglu_uri76_control", 76), ("swiglu_uri100", 100)):
            model = warm_start(source, width, balance)
            check(
                sum(a.size for a in model.parameters.values())
                == (395360 if width == 76 else ARCH["parameters"]),
                "R24 model dimension",
            )
            np.testing.assert_allclose(
                batched_predict(model, tune[:128, :width]),
                batched_predict(source, tune[:128, :76]),
                rtol=1e-5,
                atol=1e-7,
            )
            history = []
            arm = out / "training" / name
            for i in range(EPOCHS):
                order, loss = ep(model, x[:, :width], y, mass, i, schedule)
                history.append(loss)
                if width == 100:
                    save_checkpoint(
                        arm,
                        model,
                        {"epoch": i + 1, "binding": digest(plan), "loss": loss},
                        order,
                        is_best=i == EPOCHS - 1,
                    )
            scores = batched_predict(model, tune[:, :width])
            arms[name] = evaluate(tune[:, :width], yt, scores, groups, context)
            transfer[name] = {"fit_loss": history, "global_step": model.steps}
            if width == 100:
                onnx_path = out / "pilot-uri100.onnx"
                onnx.save(graph_for(model), onnx_path)
                actual = cpu_session(onnx_path, 1).run(["score"], {"input": tune})[0]
                np.testing.assert_allclose(actual, scores, rtol=1e-5, atol=1e-6)
                transfer[name] |= {
                    "pilot_onnx_sha256": file_sha256(onnx_path),
                    "python_vs_onnx_max_abs": float(np.max(np.abs(actual - scores))),
                    "pilot_checkpoint": read(arm / "best.json"),
                }
    sys.path.insert(0, str(REPO_ROOT / "ai-training/contracts/local-acceptance-v1"))
    from readiness import reviewed

    native = reviewed()
    atomic_json(
        out / "pilot.json",
        {
            "scope": "EXPOSED_WAF_TUNING_DEVELOPMENT_ONLY",
            "training_sample_count": len(y),
            "tuning_originals": len(yt),
            "arms": arms,
            "training": transfer,
            "pilot_seconds": time.monotonic() - started,
            "native": {k: v for k, v in native.items() if k != "requests"},
            "independent_holdout_read": False,
        },
    )


def verify(out):
    rows = data(out)
    plan = read(out / "pilot-plan.json")
    check(
        plan["code_sha256"] == file_sha256(__file__)
        and file_sha256(out / "publisher-r24-uri100.npz") == plan["dataset_sha256"],
        "Pilot resume binding",
    )
    arm = out / "training/swiglu_uri100"
    previous = read(arm / "previous.json")
    epoch_one = arm / previous["path"]
    check(
        file_sha256(epoch_one / "manifest.json") == previous["manifest_sha256"],
        "Previous manifest pin",
    )
    start = load_checkpoint(epoch_one)
    finish = load_checkpoint(arm)
    check(
        start.state["epoch"] == 1
        and finish.state["epoch"] == 2
        and start.state["binding"] == finish.state["binding"] == digest(plan),
        "Pilot checkpoint epoch binding",
    )
    model = WeightedSwiGLU.from_arrays(start.model.metadata(), start.model.arrays())
    order, loss = ep(
        model, rows["pilot_fit_x"], rows["pilot_fit_y"], rows["pilot_fit_mass"], 1, plan["schedule"]
    )
    check(
        model.steps == finish.model.steps and loss == finish.state["loss"],
        "Resume loss or step drift",
    )
    np.testing.assert_array_equal(order, finish.permutation)
    for name, a in model.arrays().items():
        np.testing.assert_array_equal(a, finish.model.arrays()[name])
    atomic_json(
        out / "resume.json",
        {
            "state": "PASS",
            "method": "New worker replayed epoch 2 from immutable epoch 1",
            "optimizer_weights_loss_and_permutation": "BIT_EXACT",
            "prior_checkpoint_sha256": previous["manifest_sha256"],
            "global_step": model.steps,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pilot", "verify"))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    (run if args.action == "pilot" else verify)(args.out)

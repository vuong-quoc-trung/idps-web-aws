"""One bounded three-source pilot. Old R26A artifacts and TEST remain untouched."""

# isort: skip_file

import argparse
import os
import time
from pathlib import Path

import numpy as np

from r26_common import SEED, atomic_json, check, file_sha256, read
from r26_learning import assessment, epoch, make_training, schedule_for, source_data
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint
from r16_train import batched_predict
from r18_train import WeightedSwiGLU


def data(out, pilot):
    manifest = read(out / "source2-recovery/manifest.json")
    check(manifest["augmentation_training_ready"], "Source2 closure support is insufficient")
    train, tune = source_data(out, pilot=pilot)
    frames = {}
    for role in ("FIT", "TUNING"):
        path = out / "source2-recovery" / f"{role.lower()}.npz"
        check(
            file_sha256(path) == manifest["roles"][role]["sha256"], "Source2 grouped-role binding"
        )
        with np.load(path, allow_pickle=False) as z:
            frames[role] = {name: z[name] for name in z.files}
    train.append((frames["FIT"]["x"], frames["FIT"]["y"], None))
    tune["SRBH_PUBLISHER"] = frames["TUNING"]
    return train, tune


def warm(out):
    root = out / "training/model"
    selected = read(root / "best.json")
    check(selected == read(out / "model-selection.json")["best_checkpoint"], "R26A warm checkpoint")
    source = load_checkpoint(root / selected["path"]).model
    model = WeightedSwiGLU(
        100,
        204,
        "residual_glu",
        SEED,
        objective=dict(source.objective, binary_class_weights=[1.0, 1.0]),
        regularization={
            key: source.regularization[key]
            for key in ("dropout", "weight_decay", "label_smoothing")
        },
    )
    for key, value in source.parameters.items():
        model.parameters[key][:] = value
    return model


def run(out):
    started = time.monotonic()
    train, tune = data(out, pilot=True)
    x, y, weight, report = make_training(train, 100)
    plan = {
        "source2_manifest_sha256": file_sha256(out / "source2-recovery/manifest.json"),
        "trigger": "Prespecified allowed FIT source transfer FPR >1%; no Notes TEST feedback",
        "warm_start": read(out / "model-selection.json")["best_checkpoint"],
        "feature_schema": "URI100 unchanged",
        "seed": SEED,
        "epochs": 4,
        "optimizer": "Same R26 schedule/regularization, reset Adam for additional data",
        "selection": "Macro TUNING recall at one global per-source dual FPR<=1%; require >=5pp gain and no >2pp decline on WAF/Notes",
        "new_research_test_opened": False,
        "code_sha256": file_sha256(__file__),
    }
    atomic_json(out / "source2-recovery/pilot-plan.json", plan)
    session = cpu_session(out / "bundle/swiglu.onnx", 1)
    baseline = assessment(lambda a: session.run(["score"], {"input": a})[0], tune, 100)
    model = warm(out)
    schedule = schedule_for(len(y), 4)
    losses = []
    for number in range(4):
        _, loss = epoch(model, x, y, weight, number, schedule)
        losses.append(loss)
    candidate = assessment(lambda a: batched_predict(model, a), tune, 100)
    gain = candidate["selection_rank"][0] - baseline["selection_rank"][0]
    declines = {
        name: candidate["sources"][name]["URI_ONLY"]["original_request"]["recall"]
        - baseline["sources"][name]["URI_ONLY"]["original_request"]["recall"]
        for name in ("WAF", "NOTES_SYNTHETIC")
    }
    allowed = gain >= 0.05 and min(declines.values()) >= -0.02
    atomic_json(
        out / "source2-recovery/pilot.json",
        {
            "baseline_R26A": baseline,
            "candidate": candidate,
            "gain": gain,
            "source_recall_deltas": declines,
            "full_training_allowed": allowed,
            "training_source_counts": report,
            "loss": losses,
            "decision": "FULL_AUGMENTATION_TRAINING"
            if allowed
            else "KEEP_VALIDATED_R26A_NO_REPEAT_SEARCH",
            "seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)

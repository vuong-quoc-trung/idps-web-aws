# isort: skip_file

"""Exact continuation epoch replay, separate from Rust compilation."""

import os

import numpy as np

from common import PARENT, atomic_json, check, output_arg, read
from idps_ai.training.checkpoint import load_checkpoint
from r18_train import WeightedSwiGLU
from r26_learning import epoch, make_training
from r26_recovery_pilot import data


def run(out):
    plan = read(PARENT / "augmentation-b/training-plan.json")
    train, _ = data(PARENT, False)
    x, y, weights, _ = make_training(train, 100)
    root = out / "training/model"
    previous = load_checkpoint(root / read(root / "previous.json")["path"])
    latest = load_checkpoint(root)
    model = WeightedSwiGLU.from_arrays(previous.model.metadata(), previous.model.arrays())
    permutation, loss = epoch(model, x, y, weights, previous.state["epoch"], plan["schedule"])
    check(
        loss == latest.state["last_loss"] and model.steps == latest.model.steps,
        "Continuation replay scalar mismatch",
    )
    np.testing.assert_array_equal(permutation, latest.permutation)
    for name, value in model.arrays().items():
        np.testing.assert_array_equal(value, latest.model.arrays()[name])
    atomic_json(
        out / "continuation-replay.json",
        {
            "state": "PASS",
            "from_epoch": previous.state["epoch"],
            "to_epoch": latest.state["epoch"],
            "global_step": model.steps,
            "parameters_adam_sampler_loss": "BIT_EXACT",
            "threads": int(os.environ["OPENBLAS_NUM_THREADS"]),
            "mid_batch_claimed": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

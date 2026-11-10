"""One publisher-anomaly experiment, grouped sampler and exact checkpoint cursor."""

import math
from collections import defaultdict

import numpy as np

from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model


def order_for_epoch(rng, groups):
    queues = defaultdict(list)
    for i, g in enumerate(groups):
        queues[int(g)].append(i)
    keys = list(rng.permutation(sorted(queues)))
    queues = {k: list(rng.permutation(queues[k])) for k in keys}
    result = []
    while any(queues.values()):
        for k in keys:
            if queues[k]:
                result.append(int(queues[k].pop()))
    assert sorted(result) == list(range(len(groups)))
    return np.asarray(result, np.int64)


def make_model(y, seed=17):
    n = np.bincount(np.asarray(y, np.int64), minlength=2)
    assert np.all(n > 0)
    objective = {
        "kind": "partial_binary_v1",
        "smoothing": 0.005,
        "family_weight": 0.0,
        "binary_class_weights": (len(y) / (2 * n)).tolist(),
    }
    model = Model(588, 64, "deep_mlp", seed, objective=objective)
    assert model.layer_dims == [588, 64, 64, 64, 64, 8]
    assert sum(v.size for v in model.parameters.values()) == 50696
    return model


def initial_state(model, groups, plan):
    rng = np.random.default_rng(plan["seed"])
    order = order_for_epoch(rng, groups)
    return {
        "epoch": 0,
        "cursor": 0,
        "RNG": rng.bit_generator.state,
        "plan_fingerprint": plan["fingerprint"],
        "dataset_fingerprint": plan["dataset_fingerprint"],
        "split_fingerprint": plan["split_fingerprint"],
        "planned_steps": plan["planned_steps"],
        "scheduler": {
            "kind": "constant",
            "learning_rate": plan["learning_rate"],
            "step": model.steps,
        },
        "losses": [],
    }, order


def update_once(model, state, order, x, y, groups, plan):
    assert model.steps < len(state["losses"]) + 1
    ids = order[state["cursor"] : state["cursor"] + plan["batch_size"]]
    assert len(ids) > 0
    family = np.where(y[ids] == 0, 0, -1).astype(np.int64)
    loss = float(model.train_batch(x[ids], family, plan["learning_rate"], binary_targets=y[ids]))
    assert np.isfinite(loss)
    state["losses"].append(
        {
            "step": int(model.steps),
            "epoch": int(state["epoch"]),
            "batch_rows": int(len(ids)),
            "loss": loss,
        }
    )
    state["cursor"] += int(len(ids))
    if state["cursor"] == len(order):
        state["epoch"] += 1
        if state["epoch"] < plan["epochs"]:
            rng = np.random.default_rng()
            rng.bit_generator.state = state["RNG"]
            order = order_for_epoch(rng, groups)
            state["RNG"] = rng.bit_generator.state
            state["cursor"] = 0
    state["scheduler"]["step"] = int(model.steps)
    assert len(state["losses"]) == model.steps
    return order


def save(run, model, state, order):
    return save_checkpoint(run / "model", model, state, order)


def reload(run, plan, n):
    checkpoint = load_checkpoint(run / "model")
    state = checkpoint.state
    model = checkpoint.model
    assert (
        state["plan_fingerprint"] == plan["fingerprint"]
        and state["dataset_fingerprint"] == plan["dataset_fingerprint"]
    )
    assert (
        state["split_fingerprint"] == plan["split_fingerprint"]
        and state["planned_steps"] == plan["planned_steps"]
    )
    assert len(state["losses"]) == model.steps == state["scheduler"]["step"]
    assert state["scheduler"] == {
        "kind": "constant",
        "learning_rate": plan["learning_rate"],
        "step": model.steps,
    }
    assert sorted(checkpoint.permutation.tolist()) == list(range(n))
    assert model.metadata()["layer_dims"] == [588, 64, 64, 64, 64, 8]
    return model, state, checkpoint.permutation, checkpoint.path


def planned_steps(n, epochs, batch_size):
    return int(epochs * math.ceil(n / batch_size))

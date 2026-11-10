"""Sampler/checkpoint exactness, not model-quality assertions."""

import numpy as np

from idps_ai.common import digest
from idps_ai.training.student_publisher import (
    initial_state,
    make_model,
    order_for_epoch,
    planned_steps,
    reload,
    save,
    update_once,
)


def test_each_view_once_per_epoch_and_seeded_groups():
    groups = np.array([1, 1, 1, 2, 2, 3, 4, 4, 5])
    a = order_for_epoch(np.random.default_rng(17), groups)
    b = order_for_epoch(np.random.default_rng(17), groups)
    assert np.array_equal(a, b) and sorted(a.tolist()) == list(range(len(groups)))
    assert len(set(groups[a[:5]])) == 5


def test_actual_binary_updates_checkpoint_reload_and_epoch_boundary(tmp_path):
    rng = np.random.default_rng(3)
    x = rng.normal(size=(70, 588)).astype(np.float32) * 0.02
    y = np.array([0, 1] * 35, np.int64)
    groups = np.arange(70) // 2
    model = make_model(y)
    assert sum(v.size for v in model.parameters.values()) == 50696
    plan = {
        "seed": 17,
        "dataset_fingerprint": "fixture",
        "split_fingerprint": "fixed",
        "planned_steps": planned_steps(70, 2, 64),
        "batch_size": 64,
        "epochs": 2,
        "learning_rate": 0.001,
    }
    plan["fingerprint"] = digest(plan)
    state, order = initial_state(model, groups, plan)
    initial = model.parameters["W0"].copy()
    order = update_once(model, state, order, x, y, groups, plan)
    assert (
        model.steps == 1
        and state["cursor"] == 64
        and not np.array_equal(initial, model.parameters["W0"])
    )
    save(tmp_path, model, state, order)
    restored, rs, ro, path = reload(tmp_path, plan, len(x))
    assert restored.steps == 1 and rs["cursor"] == 64
    while model.steps < plan["planned_steps"]:
        order = update_once(model, state, order, x, y, groups, plan)
        ro = update_once(restored, rs, ro, x, y, groups, plan)
        assert all(np.array_equal(v, restored.arrays()[k]) for k, v in model.arrays().items())
        assert (
            state["epoch"] == rs["epoch"]
            and state["cursor"] == rs["cursor"]
            and np.array_equal(order, ro)
        )
    assert model.steps == 4 and state["epoch"] == 2 and len(state["losses"]) == 4
    assert sum(v["batch_rows"] for v in state["losses"]) == 140
    assert model.objective["family_weight"] == 0 and model.objective["kind"] == "partial_binary_v1"

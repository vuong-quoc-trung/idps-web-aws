"""New adapter guarantees; no private data or frozen artifacts required."""

import json

import numpy as np
import pytest

from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3
from idps_ai.training.checkpoint import save_checkpoint
from idps_ai.training.frozen_body_adapter import FrozenBodyAdapter, load_adapter, selection
from idps_ai.training.models import Model


def inputs():
    rng = np.random.default_rng(71)
    prefix = rng.random((4, 588), dtype=np.float32)
    syntax = [
        body.extract(None, "application/json"),
        body.extract(b"", "application/x-www-form-urlencoded"),
        body.extract(
            b"message=%3Csvg+onload%3Dalert%281%29%3E", "application/x-www-form-urlencoded"
        ),
        body.extract(b'{"description":"Literal mathematical (2+3)=5"}', "application/json"),
    ]
    return np.stack([request_v3.assemble(x, b) for x, b in zip(prefix, syntax, strict=True)])


def test_schema_rule_and_exact_zero_path_survive_optimizer_updates():
    backbone = Model(588, 64, "deep_mlp", 17)
    reference = Model.from_arrays(backbone.metadata(), backbone.arrays())
    adapter = FrozenBodyAdapter(backbone)
    x = inputs()
    assert adapter.A.size == 1984 and len(selection()["selected"]) == 31
    assert [v["input_index"] for v in selection()["selected"]] == list(range(603, 634))
    assert adapter.predict(x)[0].tobytes() == reference.predict(x[:, :588])[0].tobytes()
    before = {k: v.tobytes() for k, v in backbone.parameters.items()}
    adapter.train_batch(x, np.array([0, 0, 1, 0]))
    assert any(np.any(v) for v in [adapter.A, adapter.m, adapter.v])
    assert set(adapter.arrays()) == {"p_A", "m_A", "v_A"}
    assert adapter.predict(x[:2])[0].tobytes() == reference.predict(x[:2, :588])[0].tobytes()
    assert (
        adapter.predict(x, disable=True)[0].tobytes() == reference.predict(x[:, :588])[0].tobytes()
    )
    assert all(
        v.tobytes() == before[k] and not v.flags.writeable for k, v in backbone.parameters.items()
    )
    with pytest.raises(ValueError):
        backbone.parameters["b0"][0] = 1


def test_adapter_gradient_matches_finite_difference_and_state_media_have_no_parameter():
    a = FrozenBodyAdapter(Model(588, 64, "deep_mlp", 17))
    x = inputs()
    y = np.array([0, 0, 1, 0])
    _, g = a.loss_and_gradient(x, y)
    for row, col in [(0, 0), (6, 1), (10, 2)]:
        eps = 0.01
        a.A[row, col] = eps
        plus = a.loss_and_gradient(x, y)[0]
        a.A[row, col] = -eps
        minus = a.loss_and_gradient(x, y)[0]
        a.A[row, col] = 0
        assert abs((plus - minus) / (2 * eps) - g[row, col]) < 2e-4
    changed = x.copy()
    changed[2:4, 599:603] = x[2:4, 599:603][:, [1, 0, 2, 3]]
    a.A.fill(0.02)
    assert a.predict(x)[0].tobytes() == a.predict(changed)[0].tobytes()
    assert a.A.shape == (31, 64)  # no optimizer coordinates for15state/media rows
    bad = x.copy()
    bad[0, 603] = 1 / 6
    with pytest.raises(AssertionError, match="non-OK"):
        a.predict(bad)


def test_adapter_checkpoint_load_restores_only_adapter_and_rejects_corrupt_latest(tmp_path):
    base = Model(588, 64, "deep_mlp", 17)
    a = FrozenBodyAdapter(base)
    x = inputs()
    y = np.array([0, 0, 1, 0])
    a.train_batch(x, y)
    state = {"plan_fingerprint": "bound-plan", "epoch": 0, "cursor": 4}
    first = save_checkpoint(tmp_path, a, state, np.arange(4, dtype=np.int64))
    loaded = load_adapter(tmp_path, base, "bound-plan")
    assert loaded.model.steps == 1 and loaded.state["cursor"] == 4
    assert all(np.array_equal(v, loaded.model.arrays()[k]) for k, v in a.arrays().items())
    a.train_batch(x, y)
    latest = save_checkpoint(tmp_path, a, state, np.arange(4, dtype=np.int64))
    (latest / "arrays.npz").write_bytes(b"corrupt")
    recovered = load_adapter(tmp_path, base, "bound-plan")
    assert recovered.used_previous and recovered.path == first and recovered.model.steps == 1
    with pytest.raises(ValueError):
        load_adapter(tmp_path, base, "wrong-plan")
    assert json.loads((first / "state.json").read_text())["model"]["trainable_parameters"] == 1984

import numpy as np
import pytest

from idps_ai.training.models import Model


def test_explicit_regularization_roundtrips_resume_and_onnx(tmp_path):
    import onnx

    from idps_ai.common import PipelineError
    from idps_ai.export.onnx import cpu_session, graph_for
    from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint

    regularization = {"dropout": 0.03, "label_smoothing": 0.005, "weight_decay": 0.0002}
    model = Model(3, 8, "residual_glu", 29, regularization=regularization)
    x = np.array([[1, 2, 3], [-1, 0, 2], [0, 2, 1]], np.float32)
    y = np.array([0, 1, 2])
    model.train_batch(x, y, 0.0003)
    save_checkpoint(tmp_path / "run", model, {"global_step": 1}, np.arange(3))
    restored = load_checkpoint(tmp_path / "run").model
    assert restored.metadata()["regularization"]["label_smoothing"] == 0.005
    model.train_batch(x, y, 0.0003)
    restored.train_batch(x, y, 0.0003)
    for name, value in model.arrays().items():
        np.testing.assert_array_equal(value, restored.arrays()[name])
    onnx.save_model(graph_for(restored), tmp_path / "model.onnx")
    for a, b in zip(
        restored.predict(x), cpu_session(tmp_path / "model.onnx", 1).run(None, {"input": x})
    ):
        np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6)
    with pytest.raises(PipelineError, match="regularization"):
        Model(3, 8, "residual_glu", regularization={"dropout": 1.0})
    with pytest.raises(PipelineError, match="regularization"):
        Model(3, 8, "mlp", regularization=regularization)


def test_main_model_has_real_ten_million_capacity_and_all_tensors_receive_gradients():
    model = Model(207, 1024, "residual_glu", 43)
    assert sum(p.size for p in model.parameters.values()) == 9_675_784
    assert model.metadata()["gradient_clip"] == 1.0
    assert model.metadata()["optimizer"] == "adamw-v1"
    x = np.random.default_rng(9).normal(size=(3, 207)).astype(np.float32)
    loss, grad = model.loss_and_gradients(x, np.array([0, 2, 5]))
    assert np.isfinite(loss)
    assert set(grad) == set(model.parameters)
    assert all(
        g.dtype == np.float32 and np.isfinite(g).all() and np.any(g != 0) for g in grad.values()
    )


def test_normalized_glu_has_hand_checked_gradient_and_checkpoint_restores_dropout(tmp_path):
    from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint

    model = Model(3, 8, "residual_glu", 29)
    x = np.random.default_rng(12).normal(size=(5, 3)).astype(np.float32)
    y = np.array([0, 2, 0, 3, 4])
    _, grad = model.loss_and_gradients(x, y)
    for name in ("Win", "Wvalue0", "Wgate1", "Wdown2", "gamma0", "betaout", "Wout"):
        index = (0, 0) if model.parameters[name].ndim == 2 else (0,)
        old = float(model.parameters[name][index])
        model.parameters[name][index] = old + 0.001
        upper = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = old - 0.001
        lower = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = old
        assert grad[name][index] == pytest.approx((upper - lower) / 0.002, abs=0.0015)
    model.train_batch(x, y, 0.0003)
    save_checkpoint(tmp_path / "run", model, {"global_step": 1}, np.arange(5))
    restored = load_checkpoint(tmp_path / "run").model
    model.train_batch(x, y, 0.0003)
    restored.train_batch(x, y, 0.0003)
    for name, value in model.arrays().items():
        np.testing.assert_array_equal(value, restored.arrays()[name])


def test_glu_onnx_keeps_normalization_and_fp64_reductions(tmp_path):
    import onnx

    from idps_ai.export.onnx import cpu_session, graph_for

    model = Model(189, 32, "residual_glu", 17)
    x = np.random.default_rng(7).uniform(-20, 20, size=(32, 189)).astype(np.float32)
    model.train_batch(x, np.arange(len(x)) % 8, 0.0002)
    p = tmp_path / "glu.onnx"
    onnx.save_model(graph_for(model), p)
    first = model.predict(x)
    second = model.predict(x)
    for a, b, c in zip(first, second, cpu_session(p, 1).run(None, {"input": x})):
        np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(a, c, rtol=1e-5, atol=1e-6)


def test_warmup_cosine_uses_committed_step_and_main_formal_refuses_small_corpus(prepared, tmp_path):
    import yaml

    from idps_ai.common import AI_ROOT, PipelineError
    from idps_ai.training.runner import train
    from idps_ai.training.schedule import learning_rate

    schedule = {
        "learning_rate": 1.0,
        "scheduler": "warmup_cosine",
        "warmup_steps": 2,
        "total_steps": 6,
        "min_lr_ratio": 0.2,
    }
    assert [learning_rate(schedule, s) for s in (0, 1, 2, 4, 6, 10)] == pytest.approx(
        [0.5, 1.0, 1.0, 0.6, 0.2, 0.2]
    )
    config = yaml.safe_load((AI_ROOT / "configs/scale_model_config.yaml").read_text())
    with pytest.raises(PipelineError, match="2M admitted"):
        train(prepared, tmp_path / "blocked", config, epochs=1, max_threads=1)
    assert not (tmp_path / "blocked/latest.json").exists()


def test_main_pipeline_mid_epoch_resume_restores_schedule_and_regularization(prepared, tmp_path):
    import yaml

    from idps_ai.common import AI_ROOT
    from idps_ai.training.checkpoint import load_checkpoint
    from idps_ai.training.runner import train

    config = yaml.safe_load((AI_ROOT / "configs/scale_pilot_config.yaml").read_text())
    config["model"]["hidden_dim"] = 8
    config["training"]["batch_size"] = 8
    train(
        prepared,
        tmp_path / "resumed",
        config,
        epochs=2,
        max_steps=3,
        max_threads=1,
        max_duration_minutes=1,
    )
    train(
        prepared,
        tmp_path / "resumed",
        config,
        epochs=2,
        resume_from=tmp_path / "resumed",
        max_threads=1,
        max_duration_minutes=1,
    )
    train(prepared, tmp_path / "reference", config, epochs=2, max_threads=1, max_duration_minutes=1)
    a, b = load_checkpoint(tmp_path / "resumed"), load_checkpoint(tmp_path / "reference")
    assert a.state["history"] == b.state["history"]
    assert a.state["scheduler"] == b.state["scheduler"]
    for n, v in a.model.arrays().items():
        np.testing.assert_array_equal(v, b.model.arrays()[n])

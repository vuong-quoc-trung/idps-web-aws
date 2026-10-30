import numpy as np
import pytest

from idps_ai.training.models import Model


def test_confident_wrong_deep_prediction_has_finite_true_cross_entropy_and_gradient():
    model = Model(3, 8, "deep_mlp", 17)
    for value in model.parameters.values():
        value.fill(0)
    model.parameters["b4"][0] = 1000
    loss, grad = model.loss_and_gradients(np.zeros((1, 3), np.float32), np.array([1]))
    assert loss == pytest.approx(1000)
    assert grad["b4"][0] == 1 and grad["b4"][1] == -1


@pytest.mark.parametrize("kind", ["deep_mlp", "denoising_autoencoder", "gated_residual"])
def test_deep_candidate_has_required_capacity_and_learns_with_verified_gradients(kind):
    large = Model(189, 256, kind, 17)
    assert 200_000 < sum(v.size for v in large.parameters.values()) < 600_000
    model = Model(3, 8, kind, 29)
    x = np.array([[0.3, 0.8, -0.1], [-0.2, -0.9, 0.5]], np.float32)
    y = np.array([0, 2])
    initial, gradients = model.loss_and_gradients(x, y)
    for name in model.parameters:
        if not name.startswith("W"):
            continue
        index = (0, 0)
        old = float(model.parameters[name][index])
        epsilon = 0.001
        model.parameters[name][index] = old + epsilon
        upper = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = old - epsilon
        lower = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = old
        assert gradients[name][index] == pytest.approx((upper - lower) / (2 * epsilon), abs=0.0005)
    for _ in range(40):
        model.train_batch(x, y, 0.003)
    assert model.loss_and_gradients(x, y)[0] < initial * 0.85


@pytest.mark.parametrize("kind", ["deep_mlp", "denoising_autoencoder", "gated_residual"])
def test_deep_model_checkpoint_restores_next_update_and_onnx_matches_wide_inputs(tmp_path, kind):
    import onnx

    from idps_ai.export.onnx import cpu_session, graph_for
    from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint

    m = Model(189, 256, kind, 43)
    x = np.random.default_rng(77).uniform(-20, 20, size=(24, 189)).astype(np.float32)
    y = np.arange(len(x)) % 8
    m.train_batch(x, y, 0.0003)
    save_checkpoint(tmp_path / "run", m, {"global_step": 1}, np.arange(len(x)))
    restored = load_checkpoint(tmp_path / "run").model
    m.train_batch(x, y, 0.0003)
    restored.train_batch(x, y, 0.0003)
    for name, value in m.arrays().items():
        np.testing.assert_array_equal(value, restored.arrays()[name])
    path = tmp_path / "model.onnx"
    onnx.save_model(graph_for(m), path)
    output = cpu_session(path, 1).run(None, {"input": x})
    for native, exported in zip(m.predict(x), output):
        np.testing.assert_allclose(native, exported, rtol=1e-5, atol=1e-6)

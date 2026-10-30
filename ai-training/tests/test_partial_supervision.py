import numpy as np
import pytest


def test_unknown_family_uses_attack_probability_mass_without_inventing_a_class():
    from idps_ai.training.partial import partial_loss

    z = np.zeros((1, 8), np.float32)
    loss, gradient = partial_loss(z, np.array([1]), np.array([-1]), smoothing=0.0)
    assert loss == pytest.approx(-np.log(7 / 8))
    np.testing.assert_allclose(gradient[0], [0.125] + [-0.125 / 7] * 7, rtol=1e-6)
    first = partial_loss(np.arange(8, dtype=np.float32)[None, :], [1], [-1])[0]
    second = partial_loss(np.array([[0, 7, 6, 5, 4, 3, 2, 1]], np.float32), [1], [-1])[0]
    assert first == pytest.approx(second)


def test_partial_supervision_gradients_and_invalid_family_contract():
    from idps_ai.training.partial import partial_loss

    z = np.array([[0.1, -0.3, 0.9, 0.2, -0.1, 0.6, 0.3, 0.8]], np.float64)
    _, grad = partial_loss(z, [1], [2], smoothing=0.005, family_weight=0.2)
    for i in range(8):
        hi, lo = z.copy(), z.copy()
        hi[0, i] += 1e-4
        lo[0, i] -= 1e-4
        difference = (
            partial_loss(hi, [1], [2], smoothing=0.005)[0]
            - partial_loss(lo, [1], [2], smoothing=0.005)[0]
        ) / 2e-4
        assert grad[0, i] == pytest.approx(difference, abs=1e-5)
    with pytest.raises(ValueError):
        partial_loss(z, [0], [2])


def test_binary_class_weights_change_prior_without_changing_or_inventing_labels():
    from idps_ai.training.partial import partial_loss

    z = np.zeros((2, 8), np.float32)
    loss, grad = partial_loss(z, [0, 1], [0, -1], smoothing=0.0, binary_class_weights=[3.0, 1.0])
    assert loss == pytest.approx((3 * -np.log(1 / 8) - np.log(7 / 8)) / 4)
    assert grad[0, 0] == pytest.approx(-0.875 * 3 / 4)
    assert grad[1, 0] == pytest.approx(0.125 / 4)


def test_partial_model_checkpoint_resume_and_onnx_keep_objective(tmp_path):
    import onnx

    from idps_ai.export.onnx import cpu_session, graph_for
    from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
    from idps_ai.training.models import Model

    objective = {"kind": "partial_binary_v1", "smoothing": 0.005, "family_weight": 0.2}
    model = Model(3, 8, "residual_glu", 29, objective=objective)
    x = np.array([[1, 2, 3], [-1, 0, 2], [0, 2, 1]], np.float32)
    family, binary = np.array([0, -1, 2]), np.array([0, 1, 1])
    model.train_batch(x, family, 0.0003, binary_targets=binary)
    save_checkpoint(tmp_path / "run", model, {"global_step": 1}, np.arange(3))
    restored = load_checkpoint(tmp_path / "run").model
    assert restored.metadata()["objective"] == objective
    model.train_batch(x, family, 0.0003, binary_targets=binary)
    restored.train_batch(x, family, 0.0003, binary_targets=binary)
    for k, a in model.arrays().items():
        np.testing.assert_array_equal(a, restored.arrays()[k])
    onnx.save_model(graph_for(restored), tmp_path / "model.onnx")
    for a, b in zip(
        model.predict(x), cpu_session(tmp_path / "model.onnx", 1).run(None, {"input": x})
    ):
        np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6)
    with pytest.raises(ValueError, match="binary"):
        restored.train_batch(x, family, 0.0003)

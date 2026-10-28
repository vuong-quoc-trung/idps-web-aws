import numpy as np
import pytest

from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.models import Model


@pytest.mark.parametrize("kind", ["mlp", "autoencoder", "residual"])
def test_checkpoint_restores_optimizer_and_next_update_exactly(tmp_path, kind):
    model = Model(3, 4, kind, 42)
    x = np.array([[0.1, 0.2, 0.3], [1, -1, 0]], dtype=np.float32)
    y = np.array([0, 1])
    model.train_batch(x, y, 0.01)
    save_checkpoint(tmp_path, model, {"global_step": 1}, np.array([1, 0]))
    restored = load_checkpoint(tmp_path)
    model.train_batch(x, y, 0.01)
    restored.model.train_batch(x, y, 0.01)
    for name, value in model.arrays().items():
        np.testing.assert_array_equal(value, restored.model.arrays()[name])
    assert restored.permutation.tolist() == [1, 0]


def test_run_lock_prevents_two_trainers_from_publishing_the_same_run(tmp_path):
    with RunLock(tmp_path):
        with pytest.raises(ValueError, match="locked"):
            with RunLock(tmp_path):
                pass


def test_residual_candidate_learns_and_its_gradient_matches_a_numerical_reference():
    model = Model(3, 5, "residual", 29)
    x = np.array([[0.3, 0.8, -0.1], [-0.2, -0.9, 0.5]], np.float32)
    y = np.array([0, 2])
    initial, gradients = model.loss_and_gradients(x, y)
    for name in ("W1", "Wr", "W2"):
        original = float(model.parameters[name][0, 0])
        epsilon = 0.001
        model.parameters[name][0, 0] = original + epsilon
        upper = model.loss_and_gradients(x, y)[0]
        model.parameters[name][0, 0] = original - epsilon
        lower = model.loss_and_gradients(x, y)[0]
        model.parameters[name][0, 0] = original
        assert gradients[name][0, 0] == pytest.approx((upper - lower) / (2 * epsilon), abs=0.0003)
    for _ in range(30):
        model.train_batch(x, y, 0.01)
    assert model.loss_and_gradients(x, y)[0] < initial * 0.5

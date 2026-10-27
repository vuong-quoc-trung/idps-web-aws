import numpy as np
import pytest

from idps_ai.training.checkpoint import RunLock, load_checkpoint, save_checkpoint
from idps_ai.training.models import Model


@pytest.mark.parametrize("kind", ["mlp", "autoencoder"])
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

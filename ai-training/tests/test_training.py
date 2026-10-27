from copy import deepcopy

import numpy as np
import pytest
import yaml

from idps_ai.common import AI_ROOT
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.runner import train


@pytest.mark.parametrize("kind", ["mlp", "autoencoder"])
def test_two_plus_two_epochs_equals_four_continuous_epochs(prepared, tmp_path, kind):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    config["model"].update(kind=kind, hidden_dim=8)
    config["training"]["batch_size"] = 4
    config["training"]["scheduler_decay_steps"] = 3
    continuous, resumed = tmp_path / "continuous", tmp_path / "resumed"
    full = train(prepared, continuous, config, epochs=4, max_threads=1)
    train(prepared, resumed, config, epochs=2, max_threads=1)
    last = train(prepared, resumed, config, epochs=4, resume_from=resumed, max_threads=1)
    assert last["global_step"] == full["global_step"]
    a, b = load_checkpoint(continuous), load_checkpoint(resumed)
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    assert a.state["scheduler"] == b.state["scheduler"]
    assert a.state["scheduler"]["next_learning_rate"] < config["training"]["learning_rate"]
    np.testing.assert_array_equal(a.permutation, b.permutation)


def test_resume_refuses_changed_learning_config(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    run = tmp_path / "run"
    train(prepared, run, config, epochs=1, max_steps=1, max_threads=1)
    changed = deepcopy(config)
    changed["training"]["learning_rate"] = 0.005
    with pytest.raises(ValueError, match="checksum mismatch"):
        train(prepared, run, changed, epochs=2, resume_from=run, max_threads=1)

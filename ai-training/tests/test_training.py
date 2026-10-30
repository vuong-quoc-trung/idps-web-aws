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


@pytest.mark.parametrize("kind", ["deep_mlp", "denoising_autoencoder", "gated_residual"])
def test_deep_train_mid_epoch_resume_reproduces_optimizer_corruption_and_metrics(
    prepared, tmp_path, kind
):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    config["model"].update(kind=kind, hidden_dim=16)
    config["training"]["batch_size"] = 7
    full, resumed = tmp_path / "full", tmp_path / "resumed"
    train(prepared, full, config, epochs=3, max_threads=1)
    first = train(prepared, resumed, config, epochs=3, max_steps=1, max_threads=1)
    assert first["cursor"] == 7
    train(prepared, resumed, config, epochs=3, resume_from=resumed, max_threads=1)
    a, b = load_checkpoint(full), load_checkpoint(resumed)
    assert a.state["history"] == b.state["history"]
    assert a.state["numpy_rng"] == b.state["numpy_rng"]
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    if kind == "denoising_autoencoder":
        assert a.state["shard"]["row_count"] < 96


def test_balanced_training_preserves_weights_and_loss_history_across_resume(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/residual_config.yaml").read_text())
    config["model"]["hidden_dim"] = 8
    config["training"].update(class_weighting="balanced_sqrt", early_stopping_patience=0)
    continuous, resumed = tmp_path / "full", tmp_path / "resumed"
    train(prepared, continuous, config, epochs=3, max_threads=1)
    partial = train(prepared, resumed, config, epochs=3, max_steps=1, max_threads=1)
    assert partial["cursor"] > 0
    train(prepared, resumed, config, epochs=3, resume_from=resumed, max_threads=1)
    a, b = load_checkpoint(continuous), load_checkpoint(resumed)
    assert a.model.class_weights is not None
    np.testing.assert_array_equal(a.model.class_weights, b.model.class_weights)
    for name, value in a.model.arrays().items():
        np.testing.assert_array_equal(value, b.model.arrays()[name])
    assert a.state["history"] == b.state["history"]
    assert all(
        np.isfinite(h["training_loss"]) and np.isfinite(h["validation_loss"])
        for h in a.state["history"]
    )

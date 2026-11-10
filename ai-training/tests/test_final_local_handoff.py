"""One-shot gates and exact continuation fixtures, never a second research run."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from idps_ai.common import atomic_json, digest
from idps_ai.data.final_release_validation import GateError, check_cross_role, require, signed
from idps_ai.training.checkpoint import RunLock, load_checkpoint
from idps_ai.training.student_publisher import initial_state, make_model, save, update_once


def driver():
    spec = importlib.util.spec_from_file_location(
        "final_local_driver", Path(__file__).parents[1] / "scripts/final-local-publisher.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_gate_and_config_fingerprint_cannot_be_bypassed():
    with pytest.raises(GateError, match="INTEGRITY"):
        require(False, "INTEGRITY")
    cfg = {"task": "publisher_anomaly"}
    cfg["fingerprint"] = digest(cfg)
    signed(cfg, "CONFIG")
    cfg["task"] = "attack_intent"
    with pytest.raises(GateError, match="CONFIG"):
        signed(cfg, "CONFIG")


def test_actual_cross_role_near_checked_even_if_group_ids_differ():
    x = np.zeros((1, 588), np.float32)
    x[0, 76] = 1
    roles = {
        r: {"x": x.copy(), "groups": np.array([i])}
        for i, r in enumerate(["TRAIN", "CALIBRATION", "EVALUATION"])
    }
    roles["CALIBRATION"]["x"][0, 0] = 123
    with pytest.raises(GateError, match="CROSS_ROLE_CONTENT_NEAR"):
        check_cross_role(roles, lambda **kw: None)


def test_valid_separated_roles_and_group_leakage():
    roles = {}
    for i, r in enumerate(["TRAIN", "CALIBRATION", "EVALUATION"]):
        x = np.zeros((1, 588), np.float32)
        x[0, 76 + i] = 1
        roles[r] = {"x": x, "groups": np.array([i])}
    check_cross_role(roles, lambda **kw: None)
    roles["EVALUATION"]["groups"][0] = 0
    with pytest.raises(GateError, match="GROUP_ROLE_LEAKAGE"):
        check_cross_role(roles, lambda **kw: None)


def fixture_run(root):
    (root / "data").mkdir(parents=True)
    rng = np.random.default_rng(17)
    x = rng.normal(0, 0.1, (16, 588)).astype(np.float32)
    y = np.tile(np.array([0, 1], np.int64), 8)
    groups = np.arange(16)
    np.savez(root / "data/train.npz", x=x, y=y, groups=groups)
    plan = {
        "seed": 17,
        "epochs": 10,
        "batch_size": 64,
        "learning_rate": 0.001,
        "planned_steps": 10,
        "dataset_fingerprint": "fixture-data",
        "split_fingerprint": "fixture-split",
    }
    plan["fingerprint"] = digest(plan)
    return x, y, groups, plan


def test_interrupted_step1_resume_matches_uninterrupted_and_repeat_is_noop(tmp_path):
    m = driver()
    a, b = tmp_path / "whole", tmp_path / "interrupted"
    fixture_run(a)
    x, y, groups, plan = fixture_run(b)
    m.actual_prepare(a, plan, lambda **kw: None)
    model = make_model(y, 17)
    state, order = initial_state(model, groups, plan)
    order = update_once(model, state, order, x, y, groups, plan)
    save(b, model, state, order)
    m.actual_prepare(b, plan, lambda **kw: None)
    ca, cb = load_checkpoint(a / "model"), load_checkpoint(b / "model")
    assert ca.model.steps == cb.model.steps == 2
    assert all(np.array_equal(v, cb.model.arrays()[k]) for k, v in ca.model.arrays().items())
    assert ca.state == cb.state and np.array_equal(ca.permutation, cb.permutation)
    m.actual_prepare(b, plan, lambda **kw: None)
    assert load_checkpoint(b / "model").path == cb.path


def test_terminal_handoff_never_launches_and_duplicate_run_is_rejected(tmp_path):
    m = driver()
    root = tmp_path / m.RUN_ID
    root.mkdir()
    atomic_json(root / "terminal.json", {"state": "COMPLETED"})
    m.orchestrate(root)
    assert not (root / "attempts").exists()
    with pytest.raises(GateError, match="ONE_FIXED_FRESH_RUN"):
        m.authorize(root)
    with RunLock(tmp_path / "lock"):
        with pytest.raises(ValueError, match="locked"):
            with RunLock(tmp_path / "lock"):
                pytest.fail("Duplicate launcher lock acquired")

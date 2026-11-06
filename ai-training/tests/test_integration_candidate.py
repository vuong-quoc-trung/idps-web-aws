"""Behavioral checks for the one-candidate study and safety decision boundaries."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numeric_mask_stateless_and_never_mutates_content_or_source():
    study = script("integration-request-study.py")
    x = np.ones((256, 588), np.float32)
    a, n = study.masked_batch(x, 31, 4, 0.25)
    b, m = study.masked_batch(x, 31, 4, 0.25)
    assert np.array_equal(a, b) and n == m and 0 < n < len(x)
    assert np.array_equal(a[:, 76:], x[:, 76:]) and np.all(x == 1)
    assert not np.array_equal(a, study.masked_batch(x, 31, 5, 0.25)[0])


def test_guard_hard_stop_precedes_pause_or_resume():
    g = script("integration-guard.py")
    assert g.control_action(80, 0, True, 30) == "KILL"
    assert g.control_action(72, 0, False, 0) == "FREEZE"
    assert g.control_action(66, 7, False, 0) == "FREEZE"
    assert g.control_action(67, 0, True, 4.9) == "WAIT"
    assert g.control_action(67, 0, True, 5) == "THAW"
    assert g.control_action(60, 0, False, 0, True) == "FREEZE"
    assert g.watchdog_override("KILL", True, False, True) == "KILL"
    assert g.watchdog_override("WAIT", True, False, True) == "FREEZE"
    assert g.watchdog_override("WAIT", False, False, True) == "WAIT"


def test_thermal_reduction_never_increases_small_cpu_budget():
    g = script("integration-guard.py")
    for quota in [1, 2, 3, 5, 10, 25, 100]:
        assert 1 <= g.reduced_quota(quota) <= quota
    assert g.reduced_quota(3) == 1.5


def test_build_pause_retains_state_but_AI_still_kills_at_limit():
    g = script("integration-guard.py")
    assert g.build_control_action(65, 0, False, 0) == "FREEZE"
    assert g.build_control_action(80, 0, True, 10) == "KILL"
    assert g.build_control_action(61, 0, True, 10) == "WAIT"
    assert g.build_control_action(59, 0, True, 4.9) == "WAIT"
    assert g.build_control_action(59, 0, True, 5) == "THAW"
    assert g.control_action(80, 0, True, 10) == "KILL"


@pytest.mark.parametrize("build_pause", [False, True])
def test_independent_watchdog_kills_at_79_even_when_build_is_paused(tmp_path, monkeypatch, build_pause):
    g = script("integration-guard.py")
    (tmp_path / "heartbeat").touch()
    killed = []
    monkeypatch.setattr(g, "cpu_reading", lambda: (79, {}))
    monkeypatch.setattr(g, "ctl", lambda *a, **kw: None)
    monkeypatch.setattr(g, "kill_unit", killed.append)
    g.watchdog("test-only.service", tmp_path, build_pause)
    assert killed == ["test-only.service"]
    assert (tmp_path / "watchdog-tripped").read_text() == "temperature_79"


def test_watchdog_sensor_failure_stops_owned_workload(tmp_path, monkeypatch):
    g = script("integration-guard.py")
    killed = []
    def missing_sensor():
        raise OSError("test sensor missing")
    monkeypatch.setattr(g, "cpu_reading", missing_sensor)
    monkeypatch.setattr(g, "kill_unit", killed.append)
    g.watchdog("test-only.service", tmp_path)
    assert killed == ["test-only.service"]
    assert "sensor_or_control_error" in (tmp_path / "watchdog-tripped").read_text()

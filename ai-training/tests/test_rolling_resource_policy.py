import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "rolling", Path(__file__).parents[1] / "scripts/rolling-resource-policy.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_weighted_active_and_paused_are_separate():
    w = m.HeatWindow()
    w.add(0, 78, False)
    w.add(4, 60, True)
    a = w.add(5, 60, True)
    assert a["active_time_weighted_c"] == 78
    assert a["paused_time_weighted_c"] == 60
    assert a["full_run_time_weighted_c"] == pytest.approx(74.4)


def test_rolling_clips_interval_at_300_seconds():
    w = m.HeatWindow()
    for t in range(0, 401, 2):
        a = w.add(t, 70 if t < 100 else 78, False)
    assert a["window_seconds"] == 300
    assert a["rolling_300s_c"] == 78


def test_spikes_average_emergency_and_cooldown():
    assert m.action(82, 74, 0, False, 0) == "REDUCE"
    assert m.action(76, 80, 0, False, 0) == "FREEZE"
    assert m.action(90, 60, 0, True, 100) == "KILL"
    assert m.action(72, 76, 0, True, 14) == "WAIT"
    assert m.action(72, 76, 0, True, 15) == "THAW"
    assert m.action(60, 60, 0, False, 0, True) == "FREEZE"
    assert m.action(79, 76, 4, False, 0) == "FREEZE"


def test_sensor_gap_is_fail_closed():
    w = m.HeatWindow()
    w.add(0, 70, False)
    with pytest.raises(ValueError):
        w.add(6, 70, False)


def test_independent_watchdog_rolling_emergency(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "guard", Path(__file__).parents[1] / "scripts/integration-guard.py"
    )
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    (tmp_path / "heartbeat").touch()
    killed = []
    monkeypatch.setattr(g, "cpu_reading", lambda: (90, {}))
    monkeypatch.setattr(g, "kill_unit", killed.append)
    g.watchdog("test-only.service", tmp_path)
    assert killed == ["test-only.service"]
    assert (tmp_path / "watchdog-tripped").read_text() == "emergency_temperature"


def test_cpu_budget_accounts_for_other_apps_and_memory_pressure():
    assert m.cpu_budget(100, 1000, 70, 100, 32) == 1
    assert m.cpu_budget(100, 1000, 20, 100, 32) == 125
    assert m.cpu_budget(100, 100, 20, 100, 32) == 100
    assert m.memory_pressure(
        "some avg10=0 avg60=0 avg300=0 total=0\nfull avg10=1.01 avg60=0 avg300=0 total=0", 0, 0, 1
    )
    assert m.memory_pressure("full avg10=0 avg60=0 avg300=0 total=0", 20 * 1024**2, 0, 1)
    assert not m.memory_pressure("full avg10=0 avg60=0 avg300=0 total=0", 0, 0, 1)


def test_kernel_quota_property_has_systemd_fixed_point_precision():
    spec = importlib.util.spec_from_file_location("guard_quota", Path(__file__).parents[1] / "scripts/integration-guard.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    assert g.quota_property(139.98631520507138) == "CPUQuota=139.99%"
    assert g.quota_property(50) == "CPUQuota=50.00%"
    assert g.quota_property(1.23456789) == "CPUQuota=1.23%"

"""Simulated temperatures only; no real heating or host thermal changes."""

import importlib.util
from pathlib import Path

import pytest

from idps_ai.common import PipelineError
from idps_ai.training.adaptive_thermal import SensorReader, ThermalMachine


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / name
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize(
    "temperature,state",
    [
        (80, "NORMAL"),
        (88, "WARNING"),
        (91, "THROTTLE"),
        (94, "STRONG_THROTTLE"),
        (96, "THERMAL_EMERGENCY"),
    ],
)
def test_requested_bands(temperature, state):
    m = ThermalMachine()
    r = m.update(1, temperature)
    assert r["state"] == state
    assert r["stop"] == (temperature >= 96)
    if temperature == 91:
        assert r["quota"] == 10
    if temperature == 94:
        assert r["quota"] == 1


def test_spike_cooldown_hysteresis_and_gradual_resume():
    m = ThermalMachine()
    assert m.update(0, 63)["state"] == "NORMAL"
    r = m.update(0.1, 92)
    assert r["state"] == "THROTTLE" and not r["stop"] and r["quota"] == 10
    r = m.update(0.2, 95)
    assert r["state"] == "THERMAL_COOLDOWN" and r["paused"] and not r["stop"]
    assert m.update(0.3, 84)["paused"]
    for i in range(1, 15):
        assert m.update(0.3 + i, 84)["paused"]
    r = m.update(15.3, 84)
    assert not r["paused"] and r["quota"] == 1
    for i in range(1, 5):
        assert m.update(15.3 + i, 83)["quota"] == 1
    assert m.update(20.3, 83)["quota"] == 3
    assert m.update(20.4, 88)["quota"] <= 3
    # Cooling stability resets after a high sample; no immediate full restore.
    assert m.update(20.5, 84)["quota"] <= 3
    assert m.update(20.6, 96)["state"] == "THERMAL_EMERGENCY"
    assert m.update(20.7, 40)["stop"]  # no automatic restart


def test_sustained_strong_heat_and_failed_cooling():
    m = ThermalMachine(cooling_timeout=4)
    assert not m.update(0, 94)["paused"]
    assert not m.update(1, 94)["paused"]
    assert m.update(2, 94)["paused"]
    for i in [3, 4, 5]:
        assert m.update(i, 94)["paused"]
    assert m.update(6, 94)["state"] == "COOLING_TIMEOUT"


def test_sensor_monitor_failure_and_lower_limit():
    assert ThermalMachine().update(0, None)["state"] == "SENSOR_FAILURE"
    assert ThermalMachine().update(0, float("nan"))["state"] == "SENSOR_FAILURE"
    assert ThermalMachine().update(0, 60, supervisor_healthy=False)["stop"]
    assert ThermalMachine().update(0, 60, hardware_emergency=True)["state"] == "THERMAL_EMERGENCY"
    assert ThermalMachine(emergency=92).update(0, 92)["state"] == "THERMAL_EMERGENCY"
    m = ThermalMachine()
    m.update(0, 60)
    assert m.update(3, 60)["state"] == "SENSOR_SAMPLING_STALE"
    with pytest.raises(PipelineError):
        ThermalMachine(emergency=100)


def test_pause_does_not_require_worker_heartbeat(tmp_path):
    guard = module("adaptive-thermal-guard.py")
    supervisor = tmp_path / "supervisor.heartbeat"
    supervisor.touch()
    assert guard.heartbeat_healthy(supervisor)
    assert not guard.heartbeat_healthy(tmp_path / "absent")
    assert not guard.heartbeat_healthy(supervisor, supervisor.stat().st_mtime + 4)
    m = ThermalMachine()
    m.update(0, 60)
    assert m.update(0.1, 95)["paused"]
    # No worker-heartbeat input: intentional cgroup freeze cannot stale the supervisor.
    assert m.update(0.2, 94, supervisor_healthy=guard.heartbeat_healthy(supervisor))["paused"]


def test_cgroup_scope_and_command_readback(tmp_path, monkeypatch):
    g = module("adaptive-thermal-guard.py")
    with pytest.raises(PipelineError):
        g.CgroupControl("nginx.service")
    c = object.__new__(g.CgroupControl)
    c.unit = "idps-student-adaptive-work-fixture.service"
    c.path = tmp_path
    c.quota = 20
    c.paused = False
    (tmp_path / "cpu.max").write_text("2000 10000")
    (tmp_path / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    commands = []

    def ctl(*args, **kw):
        commands.append(args)
        if args[0] == "set-property":
            quota = int(args[-1].split("=")[1].strip("%"))
            (tmp_path / "cpu.max").write_text(f"{quota * 100} 10000")
        if args[0] in {"freeze", "thaw"}:
            (tmp_path / "cgroup.events").write_text(
                "populated 1\nfrozen " + ("1" if args[0] == "freeze" else "0") + "\n"
            )

    monkeypatch.setattr(g, "ctl", ctl)
    c.quota_set(10)
    c.freeze(True)
    c.freeze(False)
    c.quota_set(1)
    assert c.quota == 1 and not c.paused
    assert all(c.unit in args for args in commands)
    c.stop()
    assert commands[-3][0] == "kill" and commands[-2][0] == "thaw"


def test_resume_skips_completed_milestones():
    p = module("student-data-recovery.py")
    assert p.pending_boundaries(23040) == [100000]
    assert p.pending_boundaries(4096) == [100000]
    assert p.pending_boundaries(100000) == []
    assert p.pending_boundaries(0) == [4096, 100000]
    with pytest.raises(PipelineError):
        p.pending_boundaries(100001)


def test_sensor_mapping_critical_and_auxiliary_domains(tmp_path):
    sensor = tmp_path / "temp1_input"
    sensor.write_text("92000")
    (tmp_path / "temp1_crit").write_text("105000")
    (tmp_path / "temp1_crit_alarm").write_text("0")
    aux = tmp_path / "temp2_input"
    aux.write_text("45000")
    (tmp_path / "temp2_crit").write_text("80000")
    snapshot = {
        "cpu_sensors": [
            {
                "path": str(sensor),
                "label": "Package id 0",
                "alarm": str(tmp_path / "temp1_crit_alarm"),
            }
        ],
        "effective_emergency_C": 96,
        "platform_zones": [],
        "auxiliary_sensors": [{"path": str(aux), "critical_C": 80, "driver": "nvme"}],
    }
    reader = SensorReader(snapshot)
    r = reader.read(1)
    assert r["temperature_C"] == 92 and not r["hardware_emergency"]
    aux.write_text("81000")
    assert reader.read(2)["hardware_emergency"]
    (tmp_path / "temp1_crit").write_text("95000")
    with pytest.raises(PipelineError):
        reader.read(3)
    sensor.unlink()
    with pytest.raises(OSError):
        reader.read(4)


def test_watchdog_process_loss_stops_only_worker(tmp_path, monkeypatch):
    from types import SimpleNamespace

    p = module("student-data-recovery.py")
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    (tmp_path / "memory.swap.max").write_text("0")
    stopped = []

    class Control:
        def __init__(self, unit):
            self.path = tmp_path
            self.unit = unit

        def stop(self):
            stopped.append(self.unit)

    def state(unit):
        return {
            "ActiveState": "failed" if "-watch-" in unit else "active",
            "SubState": "failed" if "-watch-" in unit else "running",
        }

    g = SimpleNamespace(CgroupControl=Control, unit_state=state, ctl=lambda *args, **kw: None)
    monkeypatch.setattr(
        p, "verify_binding", lambda *args: {"runtime_seconds": 120, "preflight": True}
    )
    monkeypatch.setattr(p, "guard_module", lambda: g)
    monkeypatch.setattr(p, "start_service", lambda *args, **kw: None)
    monkeypatch.setattr(p, "cursor", lambda *args: 23040)
    with pytest.raises(PipelineError):
        p.supervise(tmp_path, attempt)
    import json

    assert json.loads((attempt / "result.json").read_text())["state"] == "WATCHDOG_FAILURE"
    assert len(stopped) == 1 and "-work-" in stopped[0]


def test_real_control_probe_accepts_intentional_cool_pause():
    g = module("adaptive-thermal-guard.py")
    assert g.probe_safe(55, False, "NORMAL")
    assert not g.probe_safe(80, False, "NORMAL")
    assert not g.probe_safe(55, True, "NORMAL")
    assert not g.probe_safe(91, False, "THROTTLE")


def test_status_progress_does_not_wait_on_frozen_sqlite_writer(tmp_path):
    import sqlite3

    p = module("student-data-recovery.py")
    (tmp_path / "progress.json").write_text('{"rows_committed":23040}')
    db = sqlite3.connect(tmp_path / "index.sqlite")
    db.execute("CREATE TABLE fixture(i INTEGER)")
    db.commit()
    db.execute("BEGIN EXCLUSIVE")
    assert p.status_cursor(tmp_path) == 23040
    db.rollback()
    db.close()

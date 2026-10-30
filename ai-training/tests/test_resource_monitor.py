from types import SimpleNamespace


def test_resource_monitor_uses_reported_hardware_critical_limit(monkeypatch):
    import psutil

    from idps_ai.training.resources import resource_envelope

    monkeypatch.setattr(
        psutil,
        "sensors_temperatures",
        lambda: {
            "coretemp": [
                SimpleNamespace(current=99.0, critical=100.0, high=90.0, label="Package id0")
            ]
        },
    )
    with resource_envelope(1, 16) as (guard, report):
        guard.check()
        assert guard.thermal_limit_reached
    assert report["peak_cpu_temperature_celsius"] == 99
    assert report["thermal_stop_threshold_celsius"] == 95
    assert report["temperature_monitoring"] == "hardware_critical_limit_available"


def test_no_sensor_reading_is_reported_as_unavailable_not_zero_temperature(monkeypatch):
    import psutil

    from idps_ai.training.resources import resource_envelope

    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {})
    with resource_envelope(1, 16) as (guard, report):
        guard.check()
    assert not guard.thermal_limit_reached
    assert report["temperature_monitoring"] == "unavailable"
    assert report["peak_cpu_temperature_celsius"] is None


def test_training_checkpoints_before_update_when_hardware_limit_is_reached(
    prepared, tmp_path, monkeypatch
):
    import psutil
    import yaml

    from idps_ai.common import AI_ROOT
    from idps_ai.training.checkpoint import load_checkpoint
    from idps_ai.training.runner import train

    monkeypatch.setattr(
        psutil,
        "sensors_temperatures",
        lambda: {"coretemp": [SimpleNamespace(current=99.0, critical=100.0)]},
    )
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    report = train(
        prepared, tmp_path / "thermal", config, epochs=1, max_threads=1, max_duration_minutes=1
    )
    assert report["stop_reason"] == "thermal_limit"
    assert report["global_step"] == 0
    assert load_checkpoint(tmp_path / "thermal").model.steps == 0

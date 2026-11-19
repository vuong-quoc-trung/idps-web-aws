"""Pure and fixture checks for the runtime adapter. No services started."""

import errno
from pathlib import Path

import pytest

from idps_ai.common import PipelineError, atomic_json
from idps_ai.training import resource_adapter as adapter


def test_ownership_rejects_replacement_before_control(monkeypatch):
    worker = adapter.OwnedWorker("1" * 32, "/user.slice/user-123.slice/user@123.service")
    worker.invocation = "2" * 32
    monkeypatch.setattr(
        adapter,
        "properties",
        lambda unit: {
            "Id": unit,
            "Transient": "yes",
            "Description": worker.description,
            "ControlGroup": worker.group,
            "InvocationID": "3" * 32,
        },
    )
    monkeypatch.setattr(adapter, "systemctl", lambda *args: pytest.fail("Unowned mutation"))
    with pytest.raises(PipelineError, match="invocation changed"):
        worker.freeze(True)


def test_quota_readback_precedes_thaw(tmp_path):
    calls = []

    class Worker:
        def quota(self, quota):
            calls.append(("quota", quota))

        def freeze(self, paused):
            calls.append(("freeze", paused))

    decision = {"action": "APPLY_QUOTA", "cpu_quota_percent_one_cpu": 5}
    result = adapter.apply_decision(
        Worker(), decision, True, 25, lambda quota: calls.append(("readback", quota)), tmp_path
    )
    assert result == (False, 5)
    assert calls == [("quota", 5), ("readback", 5), ("freeze", False)]


@pytest.mark.parametrize(
    "violation", ["cpu.max", "memory.max", "memory.high", "memory.swap.max", "pids.max"]
)
def test_refuse_mismatched_readback(tmp_path, violation):
    worker = adapter.OwnedWorker("1" * 32, "/user.slice/user-123.slice/user@123.service")
    worker.path = tmp_path
    worker.inode = tmp_path.stat().st_ino
    data = {
        "cpu.max": "25000 100000",
        "memory.max": str(256 * adapter.MIB),
        "memory.high": str((256 * adapter.MIB * 4 // 5) // 4096 * 4096),
        "memory.swap.max": "0",
        "pids.max": "16",
    }
    for name, value in data.items():
        (tmp_path / name).write_text("max 100000" if name == violation else value)
    with pytest.raises((PipelineError, ValueError)):
        worker.limits(
            {"KillMode": "control-group", "Restart": "no", "KillSignal": "9"},
            {0},
            25,
            256 * adapter.MIB,
            16,
        )


def test_barrier_refuses_unbound_approval(tmp_path, monkeypatch):
    (tmp_path / "start.allowed").write_text('{"invocation":"wrong"}')
    atomic_json(
        tmp_path / "preflight.json",
        {
            "worker_pid": adapter.os.getpid(),
            "worker_start_ticks": adapter.process_identity(adapter.os.getpid()),
            "invocation": "expected",
        },
    )
    monkeypatch.setattr(adapter.os, "execvpe", lambda *a: pytest.fail("Unverified exec"))
    with pytest.raises(PipelineError, match="approval does not match"):
        adapter.barrier(tmp_path)


@pytest.mark.parametrize(
    "reason,cleanup,previous,requested,expected",
    [
        ("SLICE_COMPLETE", True, False, True, True),
        ("SLICE_COMPLETE", True, True, True, False),
        ("SLICE_COMPLETE", True, False, False, False),
        ("SLICE_COMPLETE", False, False, True, False),
        ("THERMAL_EMERGENCY", True, False, True, False),
        ("RUNTIME_CONTROL_FAILURE", True, False, True, False),
        ("SLICE_CHECKPOINT_UNCONFIRMED", True, False, True, False),
        ("GUARDIAN_EXIT_WITHOUT_RESULT", True, False, True, False),
    ],
)
def test_resume_requires_graceful_result_and_explicit_permission(
    reason, cleanup, previous, requested, expected
):
    result = {"reason": reason, "cleanup_verified": cleanup}
    verdict = adapter.resume_verdict(
        result,
        bindings_match=True,
        checkpoint_valid=True,
        used_previous=previous,
        fresh_preflight=True,
        explicit_resume_request=requested,
    )
    assert verdict["allowed"] is expected


def test_slice_receipt_must_bind_invocation(tmp_path: Path):
    info = {"Result": "success", "ExecMainStatus": "0"}
    atomic_json(tmp_path / "checkpoint-request.json", {"invocation": "expected"})
    assert adapter.completion_reason(tmp_path, "expected", info) == "SLICE_CHECKPOINT_UNCONFIRMED"
    atomic_json(
        tmp_path / "checkpoint-receipt.json",
        {
            "invocation": "wrong",
            "checkpoint_committed": True,
        },
    )
    assert adapter.completion_reason(tmp_path, "expected", info) == "SLICE_CHECKPOINT_UNCONFIRMED"
    atomic_json(
        tmp_path / "checkpoint-receipt.json",
        {
            "invocation": "expected",
            "checkpoint_committed": True,
        },
    )
    assert adapter.completion_reason(tmp_path, "expected", info) == "SLICE_COMPLETE"


@pytest.fixture
def exit_case(tmp_path, monkeypatch):
    worker = adapter.OwnedWorker("1" * 32, "/user.slice/user-123.slice/user@123.service")
    worker.invocation, worker.inode = "2" * 32, 1
    worker.path = tmp_path / "removed-cgroup"
    info = {
        "Id": worker.unit,
        "Transient": "yes",
        "Description": worker.description,
        "ControlGroup": "",
        "InvocationID": worker.invocation,
        "SubState": "exited",
        "ActiveState": "active",
        "MainPID": "0",
        "ExecMainPID": "100",
        "ExecMainStartTimestampMonotonic": "200",
        "ExecMainExitTimestampMonotonic": "300",
        "ExecMainCode": str(adapter.os.CLD_EXITED),
        "ExecMainStatus": "0",
        "Result": "success",
        "OOMPolicy": "stop",
    }
    monkeypatch.setattr(adapter, "properties", lambda unit: info)
    monkeypatch.setattr(adapter, "process_identity", lambda pid: None)
    return worker, info


def memory_enoent(worker):
    return FileNotFoundError(errno.ENOENT, "missing", str(worker.path / "memory.events"))


@pytest.mark.parametrize(
    "name",
    [
        "memory.events",
        "pids.events",
        "memory.current",
        "cpu.max",
        "cgroup.events",
        "cgroup.procs",
        "child/cgroup.procs",
        "",
    ],
)
def test_verified_fast_exit_and_cgroup_read_race_use_same_completion(exit_case, tmp_path, name):
    worker, info = exit_case
    assert worker.exit_info(100, "200") == info
    missing = FileNotFoundError(errno.ENOENT, "missing", str(worker.path / name))
    caught = adapter.reconcile_cgroup_read_exit(missing, worker, 100, "200")
    assert caught == info
    assert adapter.completion_reason(tmp_path, worker.invocation, caught) == "COMPLETED"


def test_exit_race_preserves_checkpoint_receipt_binding(exit_case, tmp_path):
    worker, _ = exit_case
    atomic_json(tmp_path / "checkpoint-request.json", {"invocation": worker.invocation})
    info = adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200")
    assert adapter.completion_reason(tmp_path, worker.invocation, info) == (
        "SLICE_CHECKPOINT_UNCONFIRMED"
    )
    atomic_json(
        tmp_path / "checkpoint-receipt.json",
        {"invocation": worker.invocation, "checkpoint_committed": True},
    )
    assert adapter.completion_reason(tmp_path, worker.invocation, info) == "SLICE_COMPLETE"


@pytest.mark.parametrize("current_identity", [1234, 9999], ids=["live", "pid-reused"])
def test_missing_memory_counter_cannot_finish_live_or_reused_pid(
    exit_case, monkeypatch, current_identity
):
    worker, _ = exit_case
    monkeypatch.setattr(adapter, "process_identity", lambda pid: current_identity)
    with pytest.raises(PipelineError, match="exit or PID identity"):
        adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200")


def test_only_expected_reads_of_vanished_cgroup_are_recoverable(exit_case, tmp_path):
    worker, _ = exit_case
    error = FileNotFoundError(errno.ENOENT, "missing", str(tmp_path / "thermal-input"))
    assert adapter.reconcile_cgroup_read_exit(error, worker, 100, "200") is None
    worker.path.mkdir()
    assert adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200") is None


def test_unreaped_exit_does_not_authorize_completion(exit_case):
    worker, info = exit_case
    info.update(SubState="running", MainPID="100", ExecMainCode="0")
    assert worker.exit_info(100, "200") is None
    assert adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200") is None


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("InvocationID", "3" * 32, "invocation changed"),
        ("ExecMainPID", "101", "registered main process"),
        ("ExecMainStartTimestampMonotonic", "201", "registered main process"),
        ("MainPID", "101", "exit status could not be verified"),
        ("ExecMainExitTimestampMonotonic", "0", "exit status could not be verified"),
        ("ExecMainCode", "0", "exit status could not be verified"),
        ("ExecMainCode", str(adapter.os.CLD_KILLED), "verified successful exit"),
        ("ExecMainStatus", "1", "verified successful exit"),
        ("SubState", "dead", "verified successful exit"),
    ],
)
def test_exit_race_rejects_unbound_or_unconfirmed_status(exit_case, field, value, match):
    worker, info = exit_case
    info[field] = value
    with pytest.raises(PipelineError, match=match):
        adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200")


@pytest.mark.parametrize("unit_result", ["exit-code", "oom-kill", "signal"])
def test_exit_race_retains_failed_systemd_result(exit_case, tmp_path, unit_result):
    worker, info = exit_case
    info.update(ActiveState="failed", SubState="failed", Result=unit_result, ExecMainStatus="1")
    exit_info = adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200")
    assert adapter.completion_reason(tmp_path, worker.invocation, exit_info) == "WORKER_FAILED"


def test_exit_race_refuses_oom_policy_that_can_hide_an_oom_exit(exit_case):
    worker, info = exit_case
    info["OOMPolicy"] = "continue"
    assert adapter.reconcile_cgroup_read_exit(memory_enoent(worker), worker, 100, "200") is None


@pytest.mark.parametrize(
    "memory,pids",
    [
        ({"oom": 1, "oom_kill": 0}, None),
        ({"oom": 0, "oom_kill": 0}, {"max": 1}),
    ],
)
def test_observed_limit_event_precedes_later_cgroup_reads(tmp_path, monkeypatch, memory, pids):
    from types import SimpleNamespace

    telemetry = object.__new__(adapter.Telemetry)

    def counters(path):
        if path.name == "memory.events":
            return memory
        if pids is None:
            pytest.fail("An observed OOM must be handled before another read")
        assert path.name == "pids.events"
        return pids

    monkeypatch.setattr(adapter, "counters", counters)
    with pytest.raises(adapter.WorkerLimitExceeded):
        telemetry.sample(SimpleNamespace(path=tmp_path), tmp_path)


def test_exit_inventory_requires_reclaimed_cgroup(exit_case):
    worker, info = exit_case
    assert adapter.reclaimed_exit(worker, 100, "200") == info
    worker.path.mkdir()
    assert adapter.reclaimed_exit(worker, 100, "200") is None

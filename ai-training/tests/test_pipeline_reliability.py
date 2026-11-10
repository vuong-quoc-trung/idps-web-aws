"""Race/termination regression fixtures; no real heat or source re-ingestion."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from idps_ai.common import PipelineError, atomic_json
from idps_ai.data import resumable_near as near
from idps_ai.training import heartbeat as hb


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / name
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fixture_content():
    rng = np.random.default_rng(17)
    x = rng.normal(size=(35, 16)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    # Identical groups, near variants, zeros and threshold-adjacent float32 vectors.
    base = np.zeros((3, 16), np.float32)
    base[0, 0] = 1
    for i, score in enumerate([0.995 - 1e-7 - 1e-6, 0.995 - 1e-7 + 1e-6], 1):
        base[i, 0] = score
        base[i, 1] = np.sqrt(1 - score**2)
    return np.concatenate([x, x[:12], x[:12], base, np.zeros((3, 16), np.float32)])


def test_weighted_metric_equivalent_to_original_blocked_pairs(tmp_path):
    x = fixture_content()
    near.pack_vectors(tmp_path, x, "source")
    result = near.audit(tmp_path, "source", block=8)
    assert result["pairs"] == near.original_pairs(x)
    assert result["complete"] and result["unique_vectors"] < len(x)
    assert near.audit(tmp_path, "source", block=8) == result
    with pytest.raises(PipelineError):
        near.audit(tmp_path, "changed", block=8)


def test_atomic_accumulator_survives_process_exit_and_matches_uninterrupted(tmp_path):
    x = fixture_content()
    a = tmp_path / "interrupted"
    b = tmp_path / "whole"
    near.pack_vectors(a, x, "source")
    near.pack_vectors(b, x, "source")
    code = """import os,sys
from idps_ai.data.resumable_near import audit
audit(sys.argv[1], 'source', block=8, stop_after_chunks=2)
os._exit(9)
"""
    done = subprocess.run(
        [sys.executable, "-c", code, str(a)], env={**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    )
    assert done.returncode == 9
    first = json.loads((a / "checkpoint.json").read_text())["payload"]
    assert first["next_unique_anchor"] == 16 and first["pairs"] > 0
    # Deliberately stale progress must not roll back the real checkpoint.
    (a / "progress.json").write_text('{"unique_anchor_rows":0}')
    resumed = near.audit(a, "source", block=8)
    whole = near.audit(b, "source", block=8)
    assert resumed == whole
    assert (a / "checkpoint.json").read_bytes() == (b / "checkpoint.json").read_bytes()
    assert (
        json.loads((a / "progress.json").read_text())["unique_anchor_rows"]
        == resumed["unique_vectors"]
    )


def test_kill_before_commit_does_not_double_count_and_corruption_is_explicit(tmp_path, monkeypatch):
    x = fixture_content()
    near.pack_vectors(tmp_path, x, "source")
    original = near.cross_chunk

    def fail(*args, **kw):
        raise RuntimeError("interrupted before atomic commit")

    monkeypatch.setattr(near, "cross_chunk", fail)
    with pytest.raises(RuntimeError):
        near.audit(tmp_path, "source", block=8)
    assert (
        json.loads((tmp_path / "checkpoint.json").read_text())["payload"]["next_unique_anchor"] == 0
    )
    monkeypatch.setattr(near, "cross_chunk", original)
    assert near.audit(tmp_path, "source", block=8)["pairs"] == near.original_pairs(x)
    (tmp_path / "checkpoint.json").write_text('{"payload":{},"sha256":"corrupt"}')
    with pytest.raises(PipelineError, match="checksum"):
        near.audit(tmp_path, "source", block=8)
    assert "corrupt" in (tmp_path / "checkpoint.json").read_text()  # never silently reset


def test_corrupt_cache_and_checkpoint_policy_binding(tmp_path):
    x = fixture_content()
    near.pack_vectors(tmp_path, x, "source")
    near.audit(tmp_path, "source", block=8, stop_after_chunks=1)
    with pytest.raises(PipelineError):
        near.audit(tmp_path, "source", block=4)
    with (tmp_path / "counts.npy").open("ab") as f:
        f.write(b"corrupt")
    with pytest.raises(PipelineError, match="integrity"):
        near.audit(tmp_path, "source", block=8)


def test_legacy_filesystem_clock_race_and_bounded_future_skew(monkeypatch):
    g = module("adaptive-thermal-guard.py")
    events = []

    def stat():
        events.append("stat")
        return SimpleNamespace(st_mtime=100.000001)

    def now():
        events.append("time")
        return 100.0

    monkeypatch.setattr(g, "Path", lambda p: SimpleNamespace(stat=stat))
    monkeypatch.setattr(g.time, "time", now)
    assert g.heartbeat_healthy("fixture") and events == ["stat", "time"]
    assert not g.heartbeat_healthy("fixture", now=96)
    assert not g.heartbeat_healthy("fixture", now=104)


def record(path, mono, sequence=1):
    value = {
        "version": 1,
        "pid": 123,
        "start_ticks": 456,
        "boot_id": "fixtureboot",
        "sequence": sequence,
        "monotonic_ns": mono,
        "main_loop_monotonic_ns": mono,
        "wall_time": 100,
    }
    atomic_json(path, value)
    return value


def monitor(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, "boot_identity", lambda: "fixtureboot")
    monkeypatch.setattr(hb, "process_identity", lambda pid: 456 if pid == 123 else None)
    return hb.HeartbeatMonitor(tmp_path / "heartbeat.json", 123)


def test_monotonic_record_race_wall_clock_jumps_and_diagnostics(tmp_path, monkeypatch):
    m = monitor(tmp_path, monkeypatch)
    record(m.path, 1000000000)
    monkeypatch.setattr(hb.time, "monotonic_ns", lambda: 1001000000)
    monkeypatch.setattr(hb.time, "time", lambda: -1000)
    result = m.check()
    assert (
        result["healthy"]
        and result["age_seconds"] == 0.001
        and result["pid_alive_and_identity_matches"]
    )
    assert result["consecutive_failure_count"] == 0 and result["current_wall_time"] == -1000
    assert "observed_file_mtime" in result
    monkeypatch.setattr(hb.time, "monotonic_ns", lambda: 5000000001)
    assert m.check()["decision_reason"] == "HEARTBEAT_STALE"
    assert m.check()["consecutive_failure_count"] == 2


def test_dead_pid_reuse_future_boot_and_schema_fail_closed(tmp_path, monkeypatch):
    m = monitor(tmp_path, monkeypatch)
    record(m.path, 1000000000)
    monkeypatch.setattr(hb.time, "monotonic_ns", lambda: 1001000000)
    monkeypatch.setattr(hb, "process_identity", lambda pid: 999)
    assert m.check()["decision_reason"] == "SUPERVISOR_DEAD_OR_PID_REUSED"
    monkeypatch.setattr(hb, "process_identity", lambda pid: 456)
    record(m.path, 2000000000)
    assert m.check()["decision_reason"] == "MONOTONIC_FUTURE_INVALID"
    value = record(m.path, 1000000000)
    value["boot_id"] = "anotherboot"
    atomic_json(m.path, value)
    assert m.check()["decision_reason"] == "BOOT_OR_SCHEMA_MISMATCH"
    m.path.write_text("[]")
    assert not m.check()["healthy"]


def test_live_writer_pause_independence_and_stalled_main_loop(tmp_path):
    writer = hb.SupervisorHeartbeat(tmp_path / "hb.json")
    writer.start_writer()
    try:
        m = hb.HeartbeatMonitor(writer.path, os.getpid())
        writer.pulse()
        time.sleep(0.3)
        assert m.check()["healthy"]
        value = json.loads(writer.path.read_text())
        value["main_loop_monotonic_ns"] -= 4_000_000_000
        atomic_json(writer.path, value)
        assert m.check()["decision_reason"] == "SUPERVISOR_LOOP_STALE"
    finally:
        writer.close()


def test_derivative_rebuild_preserves_rows_without_ingest(tmp_path):
    from test_student_training import entry

    from idps_ai.data.student_training import StudentIndex

    p = module("student-finalize.py")
    root = tmp_path / "root"
    root.mkdir()
    atomic_json(
        root / "plan.json", {"fingerprint": "fixture", "teacher": {}, "candidate_positions": 6}
    )
    source = StudentIndex(
        root / "materialized", {"fingerprint": "fixture", "teacher": {}, "candidate_positions": 6}
    )
    rows = [entry(i) for i in range(6)]
    source.append_student(rows)
    source.close()
    actual = StudentIndex
    (root / "materialized/features").mkdir()
    (root / "materialized/features/fixture.npz").write_bytes(b"bytes copied only")
    p.clone_derivative(root, root / "rebuild")
    a = actual(
        root / "materialized", {"fingerprint": "fixture", "teacher": {}, "candidate_positions": 6}
    )
    b = actual(
        root / "rebuild", {"fingerprint": "fixture", "teacher": {}, "candidate_positions": 6}
    )
    assert list(a.db.execute("SELECT j FROM r ORDER BY i")) == list(
        b.db.execute("SELECT j FROM r ORDER BY i")
    )
    assert a.finish({}, {}) == b.finish({}, {})
    a.close()
    b.close()

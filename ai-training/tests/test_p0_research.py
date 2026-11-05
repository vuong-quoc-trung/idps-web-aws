"""Evidence semantics and actual stop/resume decisions for the bounded P0 study."""

import importlib.util
import json
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_oracle_does_not_accept_form_echo():
    capture = script("p0-dvwa-capture.py")
    case = {"oracle": "command_stdout_canary", "expected": "CANARY_TEST"}
    response = b'<div class="vulnerable_code_area"><input value="CANARY_TEST"><pre></pre></div>'
    matched, _ = capture.oracle(case, response, {})
    assert not matched
    response = b'<div class="vulnerable_code_area"><pre>CANARY_TEST</pre></div>'
    assert capture.oracle(case, response, {})[0]


def test_sql_oracle_requires_injected_result_not_payload_echo():
    capture = script("p0-dvwa-capture.py")
    case = {"oracle": "injected_sql_rows", "expected": "INJECTED_ROW"}
    response = b'<div class="vulnerable_code_area"><pre>ID: INJECTED_ROW<br />First name: admin<br />Surname: admin</pre></div>'
    assert not capture.oracle(case, response, {"1": ["admin", "admin"]})[0]


def test_request_plan_has_unique_ids_both_classes_and_no_model_dependency():
    capture = script("p0-dvwa-capture.py")
    cases = capture.make_cases()
    assert len(cases) == 111
    assert len({r["request_id"] for r in cases}) == len(cases)
    assert {r["family"] for r in cases} == {"sqli", "xss", "cmd_injection", "path_traversal"}
    for family in {r["family"] for r in cases}:
        assert {r["planned_intent"] for r in cases if r["family"] == family} == {"benign", "attack"}


def test_confusion_keeps_unknown_separate_and_counts_all_four_outcomes():
    evaluation = script("p0-request-evaluate.py")
    rows = [
        {"lab_intent": intent, "flagged": flagged}
        for intent, flagged in [
            ("attack", True),
            ("attack", False),
            ("benign", True),
            ("benign", False),
            ("unknown", True),
        ]
    ]
    result = evaluation.confusion(rows)
    assert [result[k] for k in ["TP", "FP", "TN", "FN"]] == [1, 1, 1, 1]
    assert result["unknown_excluded"] == 1
    assert result["independent_population_recall"] is None


def test_mixed_feature_views_are_reported_and_not_quarantined_from_evaluation():
    evaluation = script("p0-request-evaluate.py")
    rows = [
        {"feature_view_sha256": "same", "lab_intent": label, "case_id": str(i)}
        for i, label in enumerate(["attack", "benign"])
    ]
    result = evaluation.collision_summary(rows)
    assert result["mixed_lab_intent_feature_views"] == 1
    assert result["rows_on_mixed_views"] == 2
    assert result["all_rows_retained_in_metrics"]


@pytest.mark.parametrize("repeat_hard_stop", [False, True])
@pytest.mark.parametrize("pause_temperature", [72, 74])
def test_thermal_supervisor_pauses_and_aborts_at80(
    tmp_path, monkeypatch, repeat_hard_stop, pause_temperature
):
    supervisor = script("p0-thermal-run.py")
    temperatures = iter([60, pause_temperature, 69, 69, 69] + ([81] if repeat_hard_stop else []))
    monkeypatch.setattr(
        supervisor,
        "cpu_sensors",
        lambda: {"coretemp": {"label": "Package id 0", "celsius": next(temperatures)}},
    )
    monkeypatch.setattr(
        supervisor.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=32_000_000_000, available=20_000_000_000),
    )
    monkeypatch.setattr(supervisor.psutil, "cpu_percent", lambda: 10)

    class Process:
        pid, returncode = 123456, 0

        def __init__(self):
            self.polls = iter([None] * (7 if repeat_hard_stop else 4) + [0])

        def poll(self):
            return next(self.polls)

        def wait(self, timeout):
            self.returncode = -15

    class Child:
        pid = 123456

        def children(self, **_):
            return []

        def memory_info(self):
            return SimpleNamespace(rss=1000)

        def is_running(self):
            return True

        def cpu_affinity(self, *_):
            return [0, 1, 2, 3]

    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *_, **__: Process())
    monkeypatch.setattr(supervisor.psutil, "Process", lambda *_: Child())
    monkeypatch.setattr(supervisor.time, "sleep", lambda *_: None)
    ticks = iter(range(0, 100, 2))
    monkeypatch.setattr(supervisor.time, "monotonic", lambda: next(ticks))
    signals = []
    monkeypatch.setattr(supervisor.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(
        sys, "argv", ["p0-thermal-run", "--output", str(tmp_path / "run"), "--", "unused"]
    )
    if repeat_hard_stop:
        with pytest.raises(RuntimeError, match="CPU thermal hard stop"):
            supervisor.main()
        assert signals[-1] == (123456, signal.SIGKILL)
    else:
        assert supervisor.main() == 0
        assert signals == [(123456, signal.SIGSTOP), (123456, signal.SIGCONT)]
    report = json.loads((tmp_path / "run/resource-report.json").read_text())
    assert [e["action"] for e in report["events"]] == ["PAUSE", "REDUCE_LOAD", "RESUME"] + (
        ["PAUSE"] if repeat_hard_stop else []
    )


def test_no_reliable_cpu_sensor_refuses_workload(tmp_path, monkeypatch):
    supervisor = script("p0-thermal-run.py")
    monkeypatch.setattr(supervisor.Path, "glob", lambda *_: iter([]))
    with pytest.raises(RuntimeError, match="No reliable CPU sensor"):
        supervisor.cpu_sensors()

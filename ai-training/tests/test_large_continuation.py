import hashlib
import http.client
import importlib.util
import json
import os
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from idps_ai.common import digest
from idps_ai.research import large_pipeline as pipeline
from idps_ai.training import data_quota_ramp as ramp_module

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "large_test_api", REPO / "ai-training/scripts/large-request-workflow.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def test_conservative_index_never_admits_true_near_neighbors():
    rng = np.random.default_rng(17)
    references = rng.random((40, 512), dtype=np.float32)
    references /= np.linalg.norm(references, axis=1, keepdims=True)
    index = pipeline.ConservativeNear(references, cap=4)
    for row in references[:10]:
        query = row + 0.001 * rng.random(512, dtype=np.float32)
        query /= np.linalg.norm(query)
        assert max(references.astype(np.float64) @ query.astype(np.float64)) >= 0.995 - 1e-7
        assert index.blocked(query)[0]
    assert index.blocked(references[0])[1] in ["PROTECTED_NEAR", "CONSERVATIVE_NEAR_OVERFLOW"]


def test_group_round_robin_consumes_every_unique_example_once():
    groups = np.array([1] * 100 + [2] * 3 + [3] * 2)
    order = pipeline.order_for_epoch(np.random.default_rng(17), groups)
    assert sorted(order.tolist()) == list(range(len(groups)))
    assert set(groups[order[:3]]) == {1, 2, 3}


def test_threshold_strict_ties_match_brute_force():
    y = np.array([0, 1, 0, 1, 1, 0])
    s = np.array([0.1, 0.7, 0.7, 0.9, 0.8, 0.1])

    def utility(t):
        p = s > t
        return 0.5 * (p[y == 1].mean() + (~p[y == 0]).mean())

    expected = max(np.unique(np.r_[0.0, s, 1.0]), key=lambda t: (utility(t), t))
    assert pipeline.choose_threshold(y, s) == expected


def test_measured_ramp_stops_when_extra_cpu_does_not_help(tmp_path, monkeypatch):
    worker = tmp_path / "worker.json"
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {"steps": [5, 10, 20, 30, 50], "window_seconds": 60, "worker_status": str(worker)}
        )
    )
    monkeypatch.setattr(ramp_module, "process_identity", lambda pid: 123)
    clock = [1000.0]
    monkeypatch.setattr(ramp_module.time, "time", lambda: clock[0])
    ramp = ramp_module.DataQuotaRamp(plan, tmp_path)
    n = r = 0
    for window, rate in enumerate([10, 20, 21]):
        for k in range(7):
            now = 1 + window * 70 + k * 10
            clock[0] = 1000 + now
            w = {
                "pid": os.getpid(),
                "start_ticks": 123,
                "heartbeat": clock[0],
                "state": "RUNNING",
                "phase": "SYNTHETIC_REQUEST_GENERATION",
                "completed": n + k * rate * 10,
                "verified_distinct_HTTP_requests": r + k * rate * 9,
                "receipt_errors": 0,
            }
            worker.write_text(json.dumps(w))
            ramp.observe(now, 55, False, False, ramp.ceiling, {os.getpid()})
        n = w["completed"]
        r = w["verified_distinct_HTTP_requests"]
    assert ramp.ceiling == 10 and ramp.halted
    assert ramp.history[-1]["action"] == "STOP_RAMP_NO_MEASURED_THROUGHPUT_GAIN"
    assert [h["next_ceiling"] for h in ramp.history] == [10, 20, 10]


def test_hot_window_never_authorizes_increase(tmp_path, monkeypatch):
    worker = tmp_path / "worker.json"
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {"steps": [5, 10, 20, 30, 50], "window_seconds": 60, "worker_status": str(worker)}
        )
    )
    monkeypatch.setattr(ramp_module, "process_identity", lambda pid: 123)
    monkeypatch.setattr(ramp_module.time, "time", lambda: 1000.0)
    ramp = ramp_module.DataQuotaRamp(plan, tmp_path)
    for k in range(7):
        worker.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "start_ticks": 123,
                    "heartbeat": 1000.0,
                    "state": "RUNNING",
                    "phase": "SYNTHETIC_REQUEST_GENERATION",
                    "completed": k * 100,
                    "verified_distinct_HTTP_requests": k * 90,
                    "receipt_errors": 0,
                }
            )
        )
        ramp.observe(1 + k * 10, 76, False, False, 5, {os.getpid()})
    assert ramp.ceiling == 5


def test_real_fixture_capture_to_topup_to_failed_gate_stops_training(tmp_path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    rows = [
        {
            "method": "GET",
            "url": "/catalog",
            "headers": "Accept: application/json",
            "body": "",
            "protocol": "HTTP/1.1",
            "label": "normal",
        },
        {
            "method": "POST",
            "url": "/lookup?query=1%27+OR+1%3D1--",
            "headers": "Accept: application/json",
            "body": "",
            "protocol": "HTTP/1.1",
            "label": "anomalous",
        },
    ]
    rows.append(rows[0] | {"label": "anomalous"})
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "source.parquet")
    empty = pipeline.ConservativeNear(np.empty((0, 512), np.float32))
    monkeypatch.setattr(
        pipeline, "protections", lambda *args: (empty, empty, empty, set(), set(), b"fixture-key")
    )
    cfg = {
        "source": {
            "path": "source.parquet",
            "rows": 3,
            "sha256": hashlib.sha256((tmp_path / "source.parquet").read_bytes()).hexdigest(),
        },
        "targets": {"distinct_requests": 1000000, "unique_TRAIN_examples": 1000000},
        "topup": {"near_candidate_cap": 4, "seconds": 30},
    }
    (root / "capture-complete.json").write_text(json.dumps({"verified_receipts": 0}))
    fake_api = SimpleNamespace(
        REPO=tmp_path,
        features=api.features,
        open_index=api.open_index,
        check_disk=lambda *args: None,
    )

    class Status:
        def write(self, **kw):
            pass

    result = pipeline.continue_after_capture(root, cfg, Status(), fake_api)
    assert result["state"] == "BLOCKED" and result["training"] == "NOT_STARTED"
    assert result["data"]["source_rows_accounted"] == 3
    assert "UNIQUE_TRAIN_SHORTFALL" in result["data"]["blockers"]
    with sqlite3.connect(root / "release-v1/index.sqlite") as db:
        assert db.execute("SELECT count(*) FROM origins").fetchone()[0] == 3
        assert (
            db.execute(
                "SELECT count(*) FROM examples WHERE publisher=-1 AND tier='UNLABELED'"
            ).fetchone()[0]
            == 1
        )


def test_passed_gate_hands_off_training_then_evaluation_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "materialize", lambda *args: {"state": "PASS", "blockers": []})

    def train(*args):
        calls.append("TRAIN")
        return object(), tmp_path / "trained"

    def evaluate(*args):
        calls.append("EVALUATE")
        return {"state": "BLOCKED", "blockers": ["QUALITY_FAILED"]}

    monkeypatch.setattr(pipeline, "train", train)
    monkeypatch.setattr(pipeline, "evaluate", evaluate)

    class Status:
        def write(self, **kw):
            pass

    result = pipeline.continue_after_capture(tmp_path, {}, Status(), None)
    assert calls == ["TRAIN", "EVALUATE"]
    assert result["training"] == "COMPLETED" and result["local_integration"] == "NOT_STARTED"


def test_real_benign_receipt_is_durable_before_client_receives_it(tmp_path):
    server = api.HTTPServer(("127.0.0.1", 0), api.Lab)
    server.receipt_journal = tmp_path / "receipts.jsonl"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request, _, intent, _ = api.scenario(0)
    assert intent == 0
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request(
            request["method"],
            request["url"],
            body=(request["body"] or "").encode(),
            headers=request["headers"],
        )
        response = connection.getresponse()
        receipt = json.loads(response.read())
        connection.close()
        assert response.status == 200 and receipt["request_hash"] == digest(request)
        stored = json.loads(server.receipt_journal.read_text())
        assert stored == receipt and len(stored["server_request_id"]) == 32
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_workflow_uses_tested_continuation_entrypoint(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        pipeline,
        "continue_after_capture",
        lambda root, cfg, status, bound_api: called.append((root, cfg, bound_api.features)),
    )
    api.validate_and_decide(tmp_path, {"target": 1000000}, None)
    assert called == [(tmp_path, {"target": 1000000}, api.features)]

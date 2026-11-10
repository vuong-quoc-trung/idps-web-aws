"""Evaluation/correlation fixtures only; none is presented as live traffic."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def module(path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_single_old_train_near_match_disallows_common_holdout():
    m = module(Path(__file__).parents[1] / "scripts/evaluate-final-local.py")
    x = np.zeros((1, 588), np.float32)
    x[0, 76] = 1
    different = np.zeros_like(x)
    different[0, 77] = 1
    old = {"x": x, "rows": np.array([0])}
    cal = {"x": different, "rows": np.array([1])}
    ev = {"x": x.copy(), "rows": np.array([2])}
    metadata = {i: {"raw": str(i), "view": str(i), "groups": [str(i)]} for i in range(3)}
    result = m.common_holdout_proof(cal, ev, old, metadata, metadata)
    assert not result["eligible_common_internal_holdout"]
    assert result["checks"]["EVALUATION"]["content_near_overlap"] == 1
    assert result["checks"]["CALIBRATION"]["content_near_overlap"] == 0


def test_fixed_probability_diagnostics_do_not_fit_scores():
    m = module(Path(__file__).parents[1] / "scripts/evaluate-final-local.py")
    d = m.probability_diagnostics(np.array([0, 1]), np.array([0.0, 1.0]))
    assert d["Brier"] == d["ECE_10_fixed_width_bins"] == 0


def test_actual_inference_record_and_missing_sensor_are_not_three_source_match(tmp_path):
    m = module(Path(__file__).parents[2] / "scripts/local-v1-acceptance.py")
    m.RUNTIME = tmp_path
    rid = "a" * 32
    for name, row in [
        ("nginx/access.log", {"request_id": rid}),
        ("student-audit/student-audit.log", {"request_id": rid}),
        (
            "ai/results.jsonl",
            {
                "request_id": rid,
                "kind": "inference",
                "status": "SCORED",
                "score": 0.1,
                "model_version": "fixture",
            },
        ),
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row) + "\n")

    def sql(_container, _database, query):
        assert "detector_alert_links" in query
        return "0"

    launcher = SimpleNamespace(sql=sql, container_name=lambda name: name)
    proof = m.receipt_evidence(
        launcher, [{"case": "fixture", "request_id": rid, "HTTP_STATUS": 200}]
    )[0]
    assert proof["AI_SHADOW_STATUS"] == "SCORED" and proof["AI_SCORE"] == 0.1
    assert proof["CORRELATION_STATUS"] == "NGINX_STUDENT_ONLY"
    assert proof["SURICATA_EVIDENCE"] == "UNAVAILABLE_NO_REQUEST_BOUND_SENSOR_RECORD"

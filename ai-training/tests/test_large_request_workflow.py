import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sklearn.feature_extraction.text import HashingVectorizer
from threadpoolctl import threadpool_limits

from idps_ai.common import PipelineError
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.research.large_request import LargeRequest, parameter_count
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "large_workflow", REPO / "ai-training/scripts/large-request-workflow.py"
)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def test_ten_million_count_is_actual_tabular_tensor_formula():
    for width in [8, 16]:
        model = LargeRequest(width)
        assert sum(v.size for v in model.parameters.values()) == parameter_count(width)
    assert 9500000 <= parameter_count(1024) == 10065928 <= 10500000


def test_distinct_tasks_abstain_without_renaming_publisher_as_intent():
    with threadpool_limits(1):
        model = LargeRequest(16)
        x = np.random.default_rng(17).random((16, 588), dtype=np.float32)
        y = np.column_stack([np.full(16, -1), np.arange(16) % 2])
        loss, grads = model.loss_and_gradients(x, y)
        assert np.isfinite(loss)
        assert np.all(grads["Wout"][:, :2] == 0)
        assert np.any(grads["Wout"][:, 2:4] != 0)
        assert np.any(grads["Wout"][:, 4:] != 0)
        assert all(
            np.isfinite(g).all() and np.any(g != 0) for k, g in grads.items() if k not in ["bout"]
        )
        with pytest.raises(PipelineError):
            model.loss_and_gradients(x, np.zeros(16))


def test_multitask_loss_has_correct_backpropagation():
    with threadpool_limits(1):
        model = LargeRequest(8)
        x = np.random.default_rng(19).random((16, 588), dtype=np.float32)
        y = np.array([[0, 1], [1, 0], [-1, -1], [1, -1]] * 4)
        _, grad = model.loss_and_gradients(x, y)
        for name in ["Wout", "Wgate0", "gamma1", "Win"]:
            p = model.parameters[name]
            index = np.unravel_index(np.abs(grad[name]).argmax(), p.shape)
            original = p[index].copy()
            p[index] = original + 0.001
            high = model.loss_and_gradients(x, y)[0]
            p[index] = original - 0.001
            low = model.loss_and_gradients(x, y)[0]
            p[index] = original
            assert np.isclose((high - low) / 0.002, grad[name][index], rtol=0.03, atol=0.0005), name


def test_multitask_checkpoint_recovers_exact_optimizer_next_update(tmp_path):
    with threadpool_limits(1):
        model = LargeRequest(16)
        x = np.random.default_rng(17).random((16, 588), dtype=np.float32)
        y = np.array([[0, 1], [1, 0], [-1, -1], [1, -1]] * 4)
        model.train_batch(x, y, 0.0003)
        save_checkpoint(tmp_path, model, {"task": "multitask_contract_test"}, np.arange(16))
        ck = load_checkpoint(tmp_path)
        recovered = LargeRequest.from_arrays(ck.state["model"], ck.model.arrays())
        model.train_batch(x, y, 0.0003)
        recovered.train_batch(x, y, 0.0003)
        assert recovered.steps == model.steps == 2
        assert all(np.array_equal(v, recovered.arrays()[k]) for k, v in model.arrays().items())
        for head in model.score_heads(x).values():
            assert np.isfinite(head).all() and ((head >= 0) & (head <= 1)).all()


def test_generator_does_not_count_identity_or_invisible_body_mutations():
    v = HashingVectorizer(
        analyzer="char",
        ngram_range=(3, 5),
        n_features=512,
        alternate_sign=False,
        norm="l2",
        dtype=np.float32,
    )
    r, role, intent, group = workflow.scenario(0)
    x, t = workflow.features(r, v)
    other = r | {
        "body": "a different whole body ignored by request-time contract",
        "request_id": "random-id-should-not-count",
    }
    xx, tt = workflow.features(other, v)
    assert np.array_equal(x, xx) and t == tt
    assert role in ["TRAIN", "CALIBRATION", "EVALUATION"] and intent in [0, 1]


def test_candidate_features_match_actual_frozen_request_projection():
    with threadpool_limits(1):
        frozen = ResearchMVP("request-v2", cpus=1)
        real = frozen.v2_model
        observed = []

        class Capture:
            def predict(self, x):
                observed.append(x.copy())
                return real.predict(x)

        frozen.v2_model = Capture()
        for i in [0, 1, 1024]:
            req, _, _, _ = workflow.scenario(i)
            x, _ = workflow.features(req, frozen.vectorizer)
            request = req | {
                "headers": "\r\n".join(k + ": " + v for k, v in req["headers"].items() if v),
                "body": None,
            }
            frozen.predict(
                {
                    "schema_version": "research-mvp-1",
                    "record_id": "contract-test",
                    "http_request": request,
                }
            )
            assert np.array_equal(x, observed[-1][0])


def test_duplicate_launch_preserves_active_status(tmp_path):
    root = tmp_path / "active"
    root.mkdir()
    original = json.dumps({"state": "RUNNING", "pid": os.getpid(), "start_ticks": 123})
    (root / "supervisor.json").write_text(original)
    (root / "launcher-owner.json").write_text(json.dumps({"pid": os.getpid()}))
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "ai-training/scripts/large-request-workflow.py"),
            "launch",
            "--run",
            str(root),
        ],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert (root / "supervisor.json").read_text() == original
    assert not (root / "terminal-status.json").exists()


def test_census_exact_duplicates_conflicting_labels_and_resume(tmp_path, monkeypatch):
    class Status:
        def write(self, **kw):
            pass

    monkeypatch.setattr(workflow, "REPO", tmp_path)
    monkeypatch.setattr(workflow, "check_disk", lambda *args: None)
    rows = [
        {
            "method": "GET",
            "url": "/one",
            "protocol": "HTTP/1.1",
            "headers": "",
            "body": "",
            "label": "normal",
        },
        {
            "method": "GET",
            "url": "/two",
            "protocol": "HTTP/1.1",
            "headers": "",
            "body": "",
            "label": "anomalous",
        },
    ]
    rows += [rows[0], rows[0] | {"label": "anomalous"}]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "train.parquet")
    cfg = {"source": {"rows": 4, "path": "train.parquet"}}
    report = workflow.census(tmp_path, cfg, Status())
    assert report["source_positions"] == 4 and report["distinct_publisher_representations"] == 2
    assert report["conflicting_publisher_representations"] == 1
    assert report["eligible_TRAIN_examples"] == 0
    again = workflow.census(tmp_path, cfg, Status())
    assert again == report


def test_data_gate_cannot_count_census_as_admitted_training(tmp_path):
    from idps_ai.research.large_pipeline import open_release, release_reasons

    cfg = {"targets": {"distinct_requests": 1000000, "unique_TRAIN_examples": 1000000}}
    (tmp_path / "public-census.json").write_text(
        json.dumps({"source_positions": 1924461, "distinct_publisher_representations": 1612017})
    )
    _, db = open_release(tmp_path, cfg)
    reasons = release_reasons(db, cfg, True)
    assert "UNIQUE_TRAIN_SHORTFALL" in reasons and "DISTINCT_ELIGIBLE_REQUEST_SHORTFALL" in reasons
    db.close()

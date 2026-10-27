import json
import shutil

import numpy as np
import pytest
import yaml

from idps_ai.cli import check_contract
from idps_ai.common import AI_ROOT, REPO_ROOT, load_json
from idps_ai.data.dataset import collect, iter_rows, verify_dataset
from idps_ai.data.privacy import entropy, request_numbers
from idps_ai.data.readers import Input, read_events
from idps_ai.training.checkpoint import load_checkpoint, save_checkpoint
from idps_ai.training.models import Model
from idps_ai.training.runner import train

KEY = b"test-only-redaction-key-32-bytes!!"


def test_schema_snapshot_is_exact_and_protected_producer_sources_match():
    contract = yaml.safe_load((AI_ROOT / "configs/schema_contract.yaml").read_text())
    assert contract["canonical_json_schema"] == load_json(
        REPO_ROOT / "contracts/canonical-event-v1.schema.json"
    )
    assert check_contract()["schema_version"] == "1.0"
    assert contract["database"]["columns"]["canonical"] == "JSONB"


def test_postgres_canonical_export_wrap_preserves_the_same_event_identity(tmp_path):
    fixture = load_json(REPO_ROOT / "contracts/fixtures/student-audit-v1.jsonl")
    a, b = tmp_path / "direct.jsonl", tmp_path / "wrapped.jsonl"
    a.write_text(json.dumps(fixture) + "\n")
    b.write_text(json.dumps({"id": 24, "canonical": fixture}) + "\n")
    direct = list(read_events([Input("canonical", a)], KEY))
    wrapped = list(read_events([Input("postgres-export", b)], KEY))
    assert direct == wrapped


def test_native_eve_enriches_bytes_and_only_past_same_flow_context(tmp_path):
    fixture = load_json(REPO_ROOT / "contracts/fixtures/student-audit-v1.jsonl")
    fixture.update(
        client_ip="192.0.2.1", request_id="request-flow", timestamp="2026-01-01T00:00:01Z"
    )
    http = {
        "timestamp": "2026-01-01T00:00:01.040Z",
        "event_type": "http",
        "src_ip": "192.0.2.1",
        "flow_id": 9007199254740993,
        "http": {
            "url": "/api/students",
            "http_method": "GET",
            "status": 200,
            "length": 512,
            "request_id": "request-flow",
        },
    }
    flow = {
        "timestamp": "2026-01-01T00:00:01.030Z",
        "event_type": "flow",
        "src_ip": "192.0.2.1",
        "flow_id": 9007199254740993,
        "flow": {
            "age": 2,
            "bytes_toserver": 128,
            "bytes_toclient": 512,
            "pkts_toserver": 2,
            "pkts_toclient": 4,
        },
    }
    future = {
        **flow,
        "timestamp": "2026-01-01T00:01:00Z",
        "flow": {**flow["flow"], "bytes_toclient": 999999},
    }
    a, b = tmp_path / "student.jsonl", tmp_path / "eve.json"
    a.write_text(json.dumps(fixture) + "\n")
    b.write_text("".join(json.dumps(e) + "\n" for e in [http, flow, future]))
    collect([Input("student", a), Input("suricata", b)], tmp_path / "dataset", KEY)
    rows = list(iter_rows(tmp_path / "dataset/requests.parquet"))
    assert len(rows) == 1
    assert rows[0]["response_bytes"] == 512
    assert json.loads(rows[0]["flow_json"])["bytes_to_client"] == 512
    assert json.loads(rows[0]["flow_json"])["duration_seconds"] == 2


def test_combined_log_escaped_user_agent_remains_private(tmp_path):
    path = tmp_path / "access.log"
    path.write_text(
        r'192.0.2.1 - - [27/Oct/2026:00:00:00 +0000] "GET /api/students?q=union%20select&token=CANARY HTTP/1.1" 200 512 "-" "Mozilla/5.0 \"CANARY\""'
        + "\n"
    )
    rows = list(read_events([Input("nginx", path)], KEY))
    assert len(rows) == 1
    assert rows[0]["numeric"]["sqli_keywords"] == 2
    assert "CANARY" not in json.dumps(rows)


def test_future_schema_or_arbitrary_extensions_never_enter_a_dataset(tmp_path):
    fixture = load_json(REPO_ROOT / "contracts/fixtures/student-audit-v1.jsonl")
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({**fixture, "schema_version": "2.0", "password": "CANARY"}) + "\n")
    stats = {}
    assert list(read_events([Input("student", path)], KEY, stats)) == []
    assert stats["invalid"] == 1
    with pytest.raises(ValueError, match="No valid"):
        collect([Input("student", path)], tmp_path / "dataset", KEY)
    assert not (tmp_path / "dataset").exists()


@pytest.mark.parametrize("kind", ["mlp", "autoencoder"])
def test_model_gradients_agree_with_an_independent_finite_difference(kind):
    model = Model(2, 3, kind)
    model.parameters["b1"][:] = 0.5
    x, y = np.array([[0.2, 0.3], [-0.1, 0.4]], np.float32), np.array([0, 1])
    _, gradients = model.loss_and_gradients(x, y)
    epsilon = 0.001
    for name, index in [("W1", (0, 0)), ("b2", (0,))]:
        original = float(model.parameters[name][index])
        model.parameters[name][index] = original + epsilon
        plus = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = original - epsilon
        minus = model.loss_and_gradients(x, y)[0]
        model.parameters[name][index] = original
        assert float(gradients[name][index]) == pytest.approx(
            (plus - minus) / (2 * epsilon), abs=0.001, rel=0.02
        )


def test_environment_drift_is_rejected_even_when_checkpoint_integrity_is_valid(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    train(prepared, tmp_path / "run", config, epochs=1, max_threads=1)
    saved = load_checkpoint(tmp_path / "run")
    saved.state["environment"]["python"] = "0.0.0"
    save_checkpoint(tmp_path / "run", saved.model, saved.state, saved.permutation)
    with pytest.raises(ValueError, match="checksum mismatch"):
        train(
            prepared,
            tmp_path / "run",
            config,
            epochs=2,
            resume_from=tmp_path / "run",
            max_threads=1,
        )


def test_early_stopping_is_terminal_and_does_not_restart_patience(prepared, tmp_path):
    config = yaml.safe_load((AI_ROOT / "configs/train_config.yaml").read_text())
    config["training"].update(learning_rate=1e-12, early_stopping_patience=1)
    result = train(prepared, tmp_path / "run", config, epochs=5, max_threads=1)
    assert result["stop_reason"] == "early_stopping"
    with pytest.raises(ValueError, match="Early-stopped"):
        train(
            prepared,
            tmp_path / "run",
            config,
            epochs=6,
            resume_from=tmp_path / "run",
            max_threads=1,
        )


def test_missing_shard_and_mathematical_entropy_cases(tmp_path, prepared):
    assert entropy("aabb") == 1.0
    assert entropy("aaaa") == 0.0
    assert request_numbers("/", "q=aa")["query_length"] == 4.0
    assert request_numbers("/", "q=aa")["query_entropy"] == 1.5
    target = tmp_path / "copy"
    shutil.copytree(prepared, target)
    (target / "features.parquet").unlink()
    with pytest.raises(ValueError, match="Missing"):
        verify_dataset(target)

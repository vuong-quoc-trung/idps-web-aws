import json
from pathlib import Path

from idps_ai.common import load_json
from idps_ai.data.dataset import collect, iter_rows
from idps_ai.data.readers import Input

KEY = b"test-only-redaction-key-32-bytes!!"


def test_same_request_is_merged_but_no_alert_is_not_a_benign_label(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "contracts/fixtures/student-audit-v1.jsonl"
    student = json.loads(fixture.read_text())
    student.update(
        client_ip="192.0.2.1", request_id="request-one", uri_path="/api/faculties", status_code=201
    )
    nginx = {
        "timestamp": student["timestamp"],
        "request_id": "request-one",
        "client_ip": "192.0.2.1",
        "http_method": "POST",
        "uri_path": "/api/faculties",
        "status": 201,
        "latency_seconds": 0.025,
    }
    a, b = tmp_path / "a.jsonl", tmp_path / "b.log"
    a.write_text(json.dumps(student) + "\n" + json.dumps(student) + "\n")
    b.write_text(json.dumps(nginx) + "\n")
    collect([Input("student", a), Input("nginx", b)], tmp_path / "dataset", KEY)
    rows = list(iter_rows(tmp_path / "dataset/requests.parquet"))
    assert len(rows) == 1
    assert rows[0]["observation_count"] == 2
    assert rows[0]["label"] is None
    assert rows[0]["label_source"] == "unknown"
    assert load_json(tmp_path / "dataset/dataset_manifest.json")["quality"]["duplicates"] == 1

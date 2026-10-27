import json
from pathlib import Path

from idps_ai.data.readers import Input, read_events

KEY = b"test-only-redaction-key-32-bytes!!"


def test_actual_student_contract_is_read_only_private_and_unlabeled(tmp_path):
    fixture = Path(__file__).resolve().parents[2] / "contracts/fixtures/student-audit-v1.jsonl"
    raw = json.loads(fixture.read_text())
    raw.update(
        query_string="token=CANARY_SECRET&q=CANARY_EMAIL@example.invalid",
        user_agent="Chrome CANARY_HEADER",
    )
    path = tmp_path / "student-audit.log"
    path.write_text(json.dumps(raw) + "\n")
    before = path.read_bytes()
    events = list(read_events([Input("student", path)], KEY))
    assert len(events) == 1
    assert events[0]["source"] == "STUDENT_AUDIT"
    assert events[0]["status_code"] == raw["status_code"]
    assert "CANARY" not in json.dumps(events)
    assert events[0]["request_key"] != raw["request_id"]
    assert "label" not in events[0]
    assert path.read_bytes() == before

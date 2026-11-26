import json
import sqlite3
from serve import initialize_journal, drain, slot
from receiver import record


def test_delivery_replay_and_conflict(tmp_path):
    db = sqlite3.connect(":memory:")
    initialize_journal(db)
    s = slot(None)
    assert s != slot("rollback")
    r = dict(
        request_id="1" * 32,
        lineage="test",
        dispatch_ns=1,
        receipt_ns=2,
        available_ns=3,
        cutoff_ns=1_000_000_001,
        guard_ns=1_000_000,
        model_sha256=s["sha256"],
        vector_sha256="a" * 64,
        availability="AVAILABLE",
        status="SCORED",
        score=0.1,
    )
    assert record(db, r) == "COMMITTED" and record(db, r) == "DUPLICATE"
    with (tmp_path / "events").open("ab") as stream:
        drain(db, stream, {s["sha256"]: s})
        drain(db, stream, {s["sha256"]: s})
        assert record(db, dict(r, vector_sha256="b" * 64)) == "QUARANTINED"
        drain(db, stream, {s["sha256"]: s})
    a, b = map(json.loads, (tmp_path / "events").read_text().splitlines())
    assert a["status"] == "SCORED" and not a["enforcement"]
    assert b["status"] == "CONFLICT" and b["score"] is None
    assert "features" not in a and "target" not in a


def test_incomplete_journal_record_is_separated_before_replay(tmp_path):
    from serve import resume_journal

    path = tmp_path / "events"
    committed = b'{"id":"committed"}\n'
    tail = b'{"id":"inter'
    path.write_bytes(committed + tail)
    with path.open("a+b") as stream:
        resume_journal(stream)
        stream.write(b'{"id":"interrupted"}\n')
    with path.open("a+b") as stream:
        resume_journal(stream)
    assert path.read_bytes() == committed + tail + b'\n{"id":"interrupted"}\n'


def test_error_and_abstention_remain_distinct_without_scores(tmp_path):
    with sqlite3.connect(":memory:") as db:
        initialize_journal(db)
        release = slot(None)
        for index, status in enumerate(("ABSTAIN", "INFERENCE_ERROR")):
            assert record(db, dict(
                request_id=str(index) * 32, lineage="test",
                dispatch_ns=1, receipt_ns=2, available_ns=3,
                cutoff_ns=1_000_000_001, guard_ns=1_000_000,
                model_sha256=release["sha256"], vector_sha256=None,
                availability="AVAILABLE", status=status,
            )) == "COMMITTED"
        with (tmp_path / "events").open("ab") as stream:
            drain(db, stream, {release["sha256"]: release})
    rows = [json.loads(line) for line in (tmp_path / "events").read_text().splitlines()]
    assert [(r["status"], r["score"], r["enforcement"]) for r in rows] == [
        ("ABSTAIN", None, False), ("INFERENCE_ERROR", None, False)
    ]

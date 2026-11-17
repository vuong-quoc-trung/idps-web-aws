import json
import time
from datetime import UTC, datetime

import pytest
from policy import attach
from store import (
    RI_MODEL,
    RI_PIN,
    collect,
    connect,
    enqueue,
    initialize,
    stats,
    vector_sha,
    verify_commits,
)


def row(index, *, scope="LOCAL_MIRROR_ONLY"):
    return {
        "request_id": f"{index:032x}",
        "dispatch_wall_ns": time.time_ns() - 1_000_000_000,
        "uri76_sha256": vector_sha([0.0] * 76),
        "scope": scope,
        "lineage": {"host_boot": "fixture"},
        "source_mask_at_cutoff": None,
        "r20": {"status": "ABSTAIN"},
    }


def test_commit_survives_close_reopen_and_replays_only_pending(tmp_path):
    path = tmp_path / "evidence.sqlite"
    db = connect(path)
    initialize(db)
    first, second = row(1), row(2)
    assert enqueue(db, first)
    collect(db, grace=0)
    assert enqueue(db, second)
    db.close()
    db = connect(path)
    assert not enqueue(db, first)
    assert not enqueue(db, first | {"uri76_sha256": "conflict"})
    assert stats(db)["cursor"] == 1 and stats(db)["pending"] == 1
    collect(db, grace=0)
    assert stats(db) == {
        "cursor": 2,
        "committed": 2,
        "rotated": 0,
        "duplicates": 1,
        "rejected": 1,
        "pending": 0,
        "retained": 2,
        "vectors_retained": 1,
        "paired_retained": 0,
        "nsa_retained": 0,
        "abstain_retained": 2,
    }
    db.close()


def test_rotation_never_drops_queued_rows_and_reuses_sqlite_pages(tmp_path):
    db = connect(tmp_path / "evidence.sqlite")
    initialize(db)
    for start in range(1, 70, 3):
        for index in range(start, start + 3):
            assert enqueue(db, row(index, scope="FIXTURE"), limit=3)
        assert not enqueue(db, row(start + 99), limit=3)
        collect(db, retain=2, grace=0)
        assert stats(db)["retained"] == 2 and stats(db)["pending"] == 0
    assert stats(db)["committed"] == 69 and stats(db)["rotated"] == 67
    assert db.execute("PRAGMA page_count").fetchone()[0] <= 12
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    db.close()


def test_live_join_retains_ri_only_with_matching_id_manifest_and_time(tmp_path):
    db = connect(tmp_path / "evidence.sqlite")
    initialize(db)
    candidate = row(1)
    assert enqueue(db, candidate)
    journal = tmp_path / "ri.jsonl"
    valid = {
        "request_id": candidate["request_id"],
        "event_id": "e" * 32,
        "kind": "inference",
        "status": "SCORED",
        "score": 0.1,
        "latency_ms": 3.0,
        "model_version": RI_MODEL,
        "manifest_sha256": RI_PIN,
        "observed_at": datetime.now(UTC).isoformat(),
        "enforcement_actions": 0,
    }
    journal.write_text(
        json.dumps(valid) + "\n" + json.dumps(valid | {"manifest_sha256": "wrong"}) + "\n"
    )
    collect(db, journal, grace=0)
    saved = json.loads(db.execute("SELECT payload FROM evidence").fetchone()[0])
    assert (
        saved["ri_v2"]["event_id"] == valid["event_id"] and saved["source_mask_at_cutoff"] is None
    )
    db.close()


def test_policy_join_checks_ri_binding_and_keeps_observation_timing():
    row = {
        "source_mask_at_cutoff": None,
        "ri_v2": {"status": "SCORED", "event_id": "b", "score": 0.1},
    }
    context = {
        "action": "LOG_ONLY",
        "automatic_block": False,
        "score": 0.1,
        "model": RI_MODEL,
        "signal": "BELOW_THRESHOLD_UNCALIBRATED",
        "ri_event_id": "a",
        "risk": 0,
        "rule_sources": [],
        "fingerprint": "f",
        "sources": ["NGINX"],
        "late_event": True,
        "correlation_proof_sha256": "c",
    }
    attach(row, context, "AVAILABLE")
    assert row["policy_context_status"] == "RI_BINDING_MISMATCH" and "hybrid" not in row
    attach(row, context | {"ri_event_id": "b"}, "AVAILABLE")
    assert row["hybrid"]["action"] == "LOG_ONLY" and row["source_mask_at_cutoff"] is None
    assert row["correlation"]["scope"] == "POST_OBSERVATION_ONLY"


def test_numeric_vector_validation():
    with pytest.raises(ValueError, match="Invalid URI76"):
        vector_sha([float("nan")] + [0.0] * 75)


def test_reopen_verifies_digest_even_when_sqlite_pages_are_valid(tmp_path):
    db = connect(tmp_path / "evidence.sqlite")
    initialize(db)
    assert enqueue(db, row(1))
    collect(db, grace=0)
    verify_commits(db)
    db.execute("UPDATE evidence SET sha256=?", ("0" * 64,))
    with pytest.raises(ValueError, match="Committed evidence digest mismatch"):
        verify_commits(db)
    db.close()

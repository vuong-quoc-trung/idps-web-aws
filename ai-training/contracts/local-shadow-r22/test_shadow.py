from types import SimpleNamespace

import guest
import pytest
from bundle import stage, verify
from evidence import append, labels, observed_sources, read
from r22 import PHASES, base_module, benign_roster

from idps_ai.common import atomic_json, canonical_bytes


def row(attempt, suffix):
    return {"attempt": attempt, "request_id": "id" + suffix, "request_key": "key" + suffix}


def test_checkpoint_dedup_conflict_and_cursor(tmp_path):
    ledger = tmp_path / "ledger.json"
    assert append(ledger, "run", 2, row(1, "a"))
    assert not append(ledger, "run", 2, row(1, "a"))
    for unexpected in (row(2, "a"), row(3, "b")):
        with pytest.raises(ValueError):
            append(ledger, "run", 2, unexpected)
    with pytest.raises(ValueError, match="checkpoint integrity"):
        append(ledger, "different-run", 2, row(2, "b"))
    assert append(ledger, "run", 2, row(2, "b"))
    checkpoint = read(ledger)
    assert checkpoint["cursor"] == 2
    checkpoint["rows"][1]["request_id"] = "tamper"
    atomic_json(ledger, checkpoint)
    with pytest.raises(ValueError, match="checkpoint integrity"):
        append(ledger, "run", 2, row(2, "b"))


def test_bundle_is_relocatable_and_rejects_changed_model(tmp_path):
    first, moved = tmp_path / "first", tmp_path / "moved"
    scope = stage(first)
    first.rename(moved)
    assert verify(moved) == scope
    (moved / "swiglu.onnx").write_bytes(b"untrusted model")
    with pytest.raises(ValueError, match="Invalid bundle member"):
        verify(moved)


def test_reported_scorer_cohort_excludes_oracle_only_and_quarantine():
    native = {
        "label": "BENIGN_VERIFIED",
        "manifest_sha256": "review",
        "disposition": "REVIEW_FOR_LINEAGE",
    }
    records = [
        native | {"request_key": "known"},
        native | {"request_key": "blocked", "disposition": "QUARANTINE"},
        native | {"request_key": "unknown", "label": "UNKNOWN", "oracle": True},
    ]
    assert set(labels({"requests": records})) == {"known"}


def test_fault_holds_real_poll_and_does_not_move_cutoff(monkeypatch):
    times = iter((1_000, 500_000_000, 1_250_001_000))
    monkeypatch.setattr(guest.time, "monotonic_ns", lambda: next(times))
    calls = []
    capture = SimpleNamespace(poll=lambda: calls.append(True))
    guest.hold_collector(capture)
    capture.poll()
    capture.poll()
    capture.poll()
    assert len(calls) == 1
    capture.poll()
    assert len(calls) == 2
    source = {"proof_sha256": "sha", "receipt_offset_ns": 10, "producer_offset_bounds_ns": [0, 1]}
    observed = observed_sources(
        [
            source | {"source": "N", "available_offset_ns": 999_000_000},
            source | {"source": "A", "available_offset_ns": 999_000_001},
        ]
    )
    assert observed["N"]["usable_at_cutoff"] and not observed["A"]["usable_at_cutoff"]


def test_roster_only_valid_benign_workflows_and_shared_session():
    rows = benign_roster(base_module().roster(0))
    assert [r["oracle"] for r in rows] == [
        "csrf",
        "login-admin",
        "principal-admin",
        "principal-admin",
        "principal-admin",
        "principal-admin",
    ]
    assert [r["attempt"] for r in rows] == list(range(1, len(PHASES) + 1))
    assert len({r["session"] for r in rows}) == 1 and all(r["intent"] == "BENIGN" for r in rows)


def test_bridge_accepts_form_login_mime_and_rejects_unapproved_value(tmp_path):
    rid = "a" * 32
    journal = tmp_path / "r22-ri.jsonl"
    record = {
        "request_id": rid,
        "method": "POST",
        "url": "/api/redacted",
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
    }
    journal.write_bytes(canonical_bytes(record) + b"\n")
    sent = []
    process = SimpleNamespace(pid=101, poll=lambda: None)

    def publish(kind, **value):
        sent.append((kind, value))

    guest.witness(tmp_path, 2, {"identity_verified": True}, rid, publish, process, None)
    assert sent[0][1]["telemetry"] == record
    journal.write_bytes(
        canonical_bytes(record | {"headers": {"Content-Type": "unapproved"}}) + b"\n"
    )
    with pytest.raises(ValueError, match="R22_TELEMETRY_HEADER_SCOPE"):
        guest.witness(tmp_path, 2, {"identity_verified": True}, rid, publish, process, None)

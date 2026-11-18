"""Fixture-only collector schedule tests, distinct from live evidence."""

from types import SimpleNamespace

import collector
from test_context import pair


class Base:
    def __init__(self):
        self.facts = []
        self.pending = []
        self.scope = "guest-boot-a"

    def resolve(self, scenario, sent, wire):
        if wire is None:
            return
        for source, offset, received, row in self.pending:
            self.facts.append(
                {
                    "source": source,
                    "byte_offset": offset,
                    "native_event_id": row.get("event_id"),
                    "proof_sha256": str(offset % 10) * 64,
                    "receipt_offset_ns": received - sent,
                    "available_offset_ns": received - sent,
                }
            )
        self.pending.clear()

    def result(self, *args):
        mask = "".join(
            s
            for s in "NSA"
            if any(f["source"] == s and f["available_offset_ns"] <= 999_000_000 for f in self.facts)
        )
        return {
            "request_key": "request-a",
            "events": self.facts,
            "identity_verified": True,
            "clock_valid": True,
            "native_mask": mask or "NONE",
        }


def make(monkeypatch):
    clock = {"ns": 20_000_000}
    monkeypatch.setattr(collector.time, "monotonic_ns", lambda: clock["ns"])
    campaign = SimpleNamespace(
        CampaignCapture=Base, timing=SimpleNamespace(clock_sample=lambda: (0, 0, 0))
    )
    collector.install(campaign)
    a, b = pair()
    raw = {
        "source": "STUDENT_AUDIT",
        "event_type": "http_request",
        "schema_version": "1.0",
        "source_instance": b["scope"],
        "event_id": a["event_id"],
        "role": "STUDENT",
        "user_id": "hmac-sha256:" + "a" * 64,
        "session_hmac": "hmac-sha256:" + "b" * 64,
    }
    capture = campaign.CampaignCapture()
    return capture, raw, clock


SCENARIO = {"method": "GET", "path": "/api/students/113"}
WIRE = SimpleNamespace(rid="nginx-trusted-rid")


def test_encoding_really_happens_before_result_and_duplicates_idempotent(monkeypatch):
    c, raw, clock = make(monkeypatch)
    c.pending = [("A", 1, 10_000_000, raw)]
    c.resolve(SCENARIO, 0, WIRE)
    assert (
        len(c.context_versions) == 1
        and c.context_versions[0]["encoded"]["status"] == "CONTEXT_AVAILABLE"
    )
    first = c.result(0, None, None)["trusted_context"]
    c.pending = [("A", 2, 30_000_000, dict(raw))]
    clock["ns"] = 40_000_000
    c.resolve(SCENARIO, 0, WIRE)
    second = c.result(0, None, None)["trusted_context"]
    assert first["encoded"] == second["encoded"]
    assert len(c.context_candidates) == 1 and len(c.context_seen) == 1
    assert first["encoding_completed_offset_ns"] == 20_000_000


def test_conflicting_duplicate_actor_never_cross_binds(monkeypatch):
    c, raw, clock = make(monkeypatch)
    c.pending = [("A", 1, 10_000_000, raw)]
    c.resolve(SCENARIO, 0, WIRE)
    c.pending = [("A", 2, 30_000_000, raw | {"user_id": "hmac-sha256:" + "c" * 64})]
    c.resolve(SCENARIO, 0, WIRE)
    result = c.result(0, None, None)["trusted_context"]
    assert result["encoded"]["state"] == "UNTRUSTED"
    assert result["projection_error"] == "AUDIT_CONTEXT_EVENT_CONFLICT"


def test_late_source_does_not_rewrite_frozen_vector(monkeypatch):
    c, raw, clock = make(monkeypatch)
    c.pending = [("A", 1, 10_000_000, raw)]
    c.resolve(SCENARIO, 0, WIRE)
    before = c.result(0, None, None)["trusted_context"]
    clock["ns"] = 1_200_000_000
    c.pending = [("S", 3, 1_100_000_000, {})]
    c.resolve(SCENARIO, 0, WIRE)
    after = c.result(0, None, None)["trusted_context"]
    assert after["encoded"] == before["encoded"]
    assert after["encoding_completed_offset_ns"] == before["encoding_completed_offset_ns"]


def test_early_missing_and_genuinely_late_context(monkeypatch):
    c, raw, clock = make(monkeypatch)
    assert c.result(0, None, None)["trusted_context"]["encoded"]["state"] == "MISSING"
    clock["ns"] = 1_200_000_000
    c.pending = [("A", 1, 1_100_000_000, raw)]
    c.resolve(SCENARIO, 0, WIRE)
    result = c.result(0, None, None)["trusted_context"]
    assert result["encoded"]["state"] == "OBSERVED_LATE"
    assert result["encoding_completed_offset_ns"] > 999_000_000

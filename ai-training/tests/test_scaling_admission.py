"""Adversarial admission invariants; fixtures are synthetic, no label certification."""

import json

import pytest

from idps_ai.common import PipelineError, digest
from idps_ai.data.scaling_admission import AdmissionIndex, simhash


def row(i, **changes):
    r = {
        "source": "fixture",
        "source_row": i,
        "request_key": digest(["req", i]),
        "representation_key": digest(["raw", i]),
        "view_key": digest(["view", i]),
        "groups": [digest(["group", i])],
        "workflow_key": digest(["workflow", i]),
        "role": "TRAIN",
        "tier": "A",
        "label": i % 2,
        "label_task": "attack_intent",
        "identity_verified": True,
        "label_verified": True,
        "feature_valid": True,
        "body_state": "EMPTY",
        "headers_available": True,
        "lineage_verified": True,
        "privacy_valid": True,
        "inherited_eligible": True,
        "reasons": [],
        "near_hash": None,
        "timestamp": None,
        "family": "fixture",
        "method": "GET",
    }
    return r | changes


def test_transaction_representation_and_publisher_counts_are_distinct(tmp_path):
    db = AdmissionIndex(tmp_path, {"input": "fixed"})
    db.append(
        [
            row(0),
            row(1, request_key=digest(["req", 0]), label=0),
            row(2, representation_key=digest(["raw", 0]), label=0),
            row(
                3,
                tier="C",
                label_task="publisher_anomaly",
                identity_verified=False,
                request_key=None,
                label_verified=False,
                inherited_eligible=False,
            ),
        ]
    )
    s = db.finalize()["counts"]
    db.close()
    assert s["TOTAL_SOURCE_ROWS"] == 4 and s["UNIQUE_HTTP_REQUESTS"] == 2
    assert s["STRICT_ELIGIBLE"] == 1 and s["QUARANTINED"] == 3
    assert s["UNKNOWN"] == 1 and s["LABEL_SUPPORTED"] == 3


def test_excluded_bridge_propagates_cross_role_and_conflicts_quarantine_both(tmp_path):
    g1, g2 = digest("g1"), digest("g2")
    db = AdmissionIndex(tmp_path, {"input": "fixed"})
    db.append(
        [
            row(0, groups=[g1]),
            row(1, groups=[g1, g2], inherited_eligible=False),
            row(2, groups=[g2], role="DEVELOPMENT"),
            row(3, view_key=digest("conflict"), label=0),
            row(4, view_key=digest("conflict"), label=1),
        ]
    )
    s = db.finalize()
    db.close()
    assert s["counts"]["STRICT_ELIGIBLE"] == 0
    assert s["quarantine_reasons_overlapping"]["CROSS_ROLE_CONNECTED_COMPONENT"] == 3
    assert s["quarantine_reasons_overlapping"]["CONTRADICTORY_DECLARED_TASK_LABEL"] == 2


def test_crash_resume_atomic_cursor_and_byte_identical_rebuild(tmp_path):
    interrupted = tmp_path / "interrupted"
    db = AdmissionIndex(interrupted, {"input": "fixed"})

    def fail():
        yield from (row(i) for i in range(5))
        raise RuntimeError("fixture-crash")

    with pytest.raises(RuntimeError):
        db.append(fail(), chunk=4)
    assert db.cursor == 4
    db.close()
    (interrupted / "progress.json").write_text('{"rows_committed":0}')
    db = AdmissionIndex(interrupted, {"input": "fixed"})
    assert json.loads((interrupted / "progress.json").read_text())["rows_committed"] == 4
    db.append([row(i) for i in range(db.cursor, 10)])
    s = db.finalize()
    db.close()
    other = tmp_path / "rebuild"
    db = AdmissionIndex(other, {"input": "fixed"})
    db.append([row(i) for i in range(10)])
    assert db.finalize() == s
    db.close()
    assert (other / "decisions.jsonl").read_bytes() == (
        interrupted / "decisions.jsonl"
    ).read_bytes()
    with pytest.raises(PipelineError):
        AdmissionIndex(interrupted, {"input": "changed"})


def test_unsafe_metadata_and_near_overflow_fail_closed(tmp_path):
    db = AdmissionIndex(tmp_path, {"input": "fixed"})
    with pytest.raises(PipelineError):
        db.append([row(0, raw_cookie="secret-canary")])
    assert db.cursor == 0
    # A 257th member must quarantine all previous members, without an unbounded bucket.
    db.append([row(i, label=0, near_hash="0" * 16) for i in range(257)])
    s = db.finalize()
    assert s["counts"]["STRICT_ELIGIBLE"] == 0
    assert s["quarantine_reasons_overlapping"]["NEAR_BUCKET_OVERFLOW"] == 257
    assert (
        db.db.execute("SELECT max(n) FROM (SELECT count(*) n FROM b GROUP BY band,k)").fetchone()[0]
        == 256
    )
    assert "secret-canary" not in (tmp_path / "decisions.jsonl").read_text()
    db.close()
    assert simhash("safe syntax tokens") == simhash("safe syntax tokens")

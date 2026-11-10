"""Student profile invariants; fixtures do not certify real label quality."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from test_scaling_admission import row

from idps_ai.common import PipelineError, digest
from idps_ai.data.student_training import (
    StudentIndex,
    apply_proposal,
    normalize_tier,
    protected_near,
    publisher_target,
    teacher_proposal,
    validate_metadata,
)


def pipeline():
    spec = importlib.util.spec_from_file_location(
        "student_pipeline", Path(__file__).parents[1] / "scripts/student-data-pipeline.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def meta(label="normal", slot=0):
    return {
        **publisher_target(label),
        "outcome": "UNKNOWN_OUTCOME",
        "parsed": True,
        "body_observation": "EMPTY",
        "headers_observation": "EMPTY",
        "feature_ref": {"shard": "features/000000000-000000256.npz", "slot": slot},
        "feature_contract": "student-http588-rich-v2-publisher-v1",
        "physical_identity": "UNVERIFIED",
        "teacher_pretrain_template_overlap": False,
        "pseudo": teacher_proposal(
            None, None, teacher="frozen", expected_teacher="frozen", threshold=0.8, allowed=False
        ),
    }


def entry(i, label=0, **changes):
    return [
        row(
            i,
            role="EXTERNAL_STAGING_EXPOSED",
            tier="C",
            label=label,
            label_task="publisher_anomaly",
            identity_verified=False,
            request_key=None,
            **changes,
        ),
        meta("anomalous" if label else "normal", i % 256),
    ]


def test_tier_semantics_and_teacher_conflict():
    assert normalize_tier("SILVER", original="anomalous")["intent"] == "UNKNOWN_INTENT"
    assert normalize_tier("UNLABELED")["target"] is None
    with pytest.raises(PipelineError):
        normalize_tier("GOLD", intent="ATTACK_INTENT", provenance="fixture")
    assert (
        normalize_tier("GOLD", intent="ATTACK_INTENT", oracle=True, provenance="fixture")["target"]
        == 1
    )
    with pytest.raises(PipelineError):
        normalize_tier("SILVER", original="attack")
    with pytest.raises(PipelineError):
        teacher_proposal(0.99, None, teacher="new", expected_teacher="old", threshold=0.8)

    def p(score, original):
        return teacher_proposal(
            score, original, teacher="frozen", expected_teacher="frozen", threshold=0.8
        )

    assert p(0.8, None)["abstained"]  # frozen strict greater-than
    assert p(0.1, 0)["label"] is None  # no guessed negative-confidence threshold
    assert p(0.99, 0)["conflict"] and p(0.99, 0)["abstained"]
    silver = apply_proposal(meta(), p(0.99, 0))
    assert silver["tier"] == "SILVER" and silver["target"] == 0
    bronze = apply_proposal(meta(None), p(0.99, None))
    assert bronze["tier"] == "BRONZE" and bronze["target_task"] == "teacher_high_risk_proxy"
    assert bronze["intent"] == "UNKNOWN_INTENT"


def test_resume_rebuild_duplicates_conflicts_and_protected_bridge(tmp_path):
    rows = [
        entry(0),
        entry(1, representation_key=digest(["raw", 0])),
        entry(2, view_key=digest("equal")),
        entry(3, view_key=digest("equal")),
        entry(4, view_key=digest("mixed")),
        entry(5, 1, view_key=digest("mixed")),
        entry(6, groups=[digest("a")]),
        entry(7, groups=[digest("a"), digest("b")]),
        entry(8, groups=[digest("b")]),
    ]
    sums = []
    for name, resumed in [("a", True), ("b", False)]:
        d = tmp_path / name
        ix = StudentIndex(d, {"frozen": 1})
        if resumed:
            ix.append_student(rows[:4])
            ix.close()
            (d / "progress.json").write_text('{"rows_committed":0}')
            ix = StudentIndex(d, {"frozen": 1})
            assert ix.cursor == 4
        ix.append_student(rows[ix.cursor :])
        ix.db.execute("INSERT INTO blocked VALUES(?,?)", (7, "PROTECTED_EXISTING_ROLE"))
        ix.db.commit()
        sums.append(ix.finish({"coverage": "fixture"}, {}))
        assert ix.finish({"coverage": "fixture"}, {}) == sums[-1]
        ix.close()
    assert sums[0] == sums[1]
    counts = sums[0]["counts"]
    assert counts["SOURCE_ROWS"] == 9 and counts["DEDUPLICATED_TRAINING_EXAMPLES"] == 3
    assert counts["QUARANTINED"] == 6 and counts["ACTUAL_TRAINING_CONSUMED"] == 0
    for name in ["ledger.jsonl", "training-index.jsonl"]:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    train = [json.loads(x) for x in (tmp_path / "a/training-index.jsonl").read_text().splitlines()]
    assert [r["feature_view_inverse_weight"] for r in train] == [1, 0.5, 0.5]
    with pytest.raises(PipelineError):
        StudentIndex(tmp_path / "a", {"frozen": 2})


def test_metadata_privacy_and_atomic_rollback(tmp_path):
    m = meta()
    m["raw_cookie"] = "secret-canary"
    with pytest.raises(PipelineError):
        validate_metadata(m)
    m = meta()
    m["feature_ref"]["shard"] = "../../secret"
    with pytest.raises(PipelineError):
        validate_metadata(m)
    ix = StudentIndex(tmp_path, {})

    def broken():
        yield entry(0)
        raise RuntimeError("interruption")

    with pytest.raises(RuntimeError):
        ix.append_student(broken())
    assert ix.cursor == 0 and ix.db.execute("SELECT count(*) FROM student").fetchone()[0] == 0
    ix.append_student([entry(0)])
    ix.finish({}, {})
    assert "secret-canary" not in (tmp_path / "ledger.jsonl").read_text()
    ix.close()


def test_full_near_metric_and_contract(tmp_path, monkeypatch):
    p = pipeline()
    a = np.eye(4, dtype=np.float32)
    assert protected_near(a, a[[0, 3]]).tolist() == [True, False, False, True]
    assert not protected_near(a, a[:0]).any()
    with pytest.raises(PipelineError):
        protected_near(a, a[:, :2])
    assert "secret-canary" not in p.selected_headers(
        "User-Agent: fixture Cookie: secret-canary Accept: */*"
    )
    # Actual parser frame selection, independent of scores; first-party count fixed.
    recovery = {"records": [{"fixture": i} for i in range(73)]}
    (tmp_path / "first-party-recovery.json").write_text(json.dumps(recovery))
    monkeypatch.setattr(
        p, "waf_rows", lambda start: iter((i, {"fixture": i}) for i in range(start, 1000))
    )
    all_rows = list(p.frames(tmp_path, 0, 512))
    assert len(all_rows) == 512 and sum(r[0] == "first-party" for r in all_rows) == 73
    assert all_rows[400:] == list(p.frames(tmp_path, 400, 512))
    # Atomic numeric storage is byte-identical and refuses incompatible overwrite.
    x = np.zeros((2, 588), np.float32)
    p.npz_atomic(tmp_path / "one.npz", x=x)
    p.npz_atomic(tmp_path / "two.npz", x=x)
    assert (tmp_path / "one.npz").read_bytes() == (tmp_path / "two.npz").read_bytes()
    with pytest.raises(AssertionError):
        p.npz_atomic(tmp_path / "one.npz", x=x + 1)

"""Synthetic controls; not evidence of native statistical independence."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from context22 import FIELDS, category, encode
from plan import FAMILIES, lineage_plan, roster
from semantic import AuthorizationOracle
from verify import fixture


@pytest.mark.parametrize("family", FAMILIES)
def test_locked_roles_population_and_semantic_domains(family):
    rows = roster(family)
    targets = [r for r in rows if r["population"] == "TARGET"]
    assert len(targets) == 2 and [r["attempt"] for r in rows] == list(range(1, len(rows) + 1))
    assert {r["label_task"] for r in targets} == {"AUTHORIZATION_POLICY_VIOLATION_ATTEMPT"}
    assert all(r["label_task"] == "SESSION_ESTABLISHMENT_CONTROL" for r in rows if r not in targets)
    assert [r["expected_status"] for r in targets] == FAMILIES[family]["expected"]
    assert sum(r["method"] == "POST" and r["population"] == "TARGET" for r in rows) == (
        2 if family == "academic-write" else 0
    )


@pytest.mark.parametrize(
    "role,cat,method,control",
    [
        ("ADMIN", "USER_ADMIN", "GET", "ALLOW"),
        ("STAFF", "USER_ADMIN", "GET", "DENY"),
        ("STUDENT", "SELF_PROFILE", "GET", "ALLOW"),
        ("ADMIN", "SELF_PROFILE", "GET", "DENY"),
        ("STAFF", "ACADEMIC_WRITE", "POST", "ALLOW"),
        ("STUDENT", "ACADEMIC_WRITE", "POST", "DENY"),
    ],
)
def test_whitelisted_current_context_and_separate_policy(role, cat, method, control):
    f = fixture(role, cat)
    f["binding"]["method"] = method
    result = encode(f["observation"], f["binding"])
    assert len(result["vector"]) == len(FIELDS) == 22
    assert result["status"] == "CONTEXT_AVAILABLE" and result["policy_control"] == control


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/users"),
        ("GET", "/api/training-programs"),
    ],
)
def test_no_unsupported_implicit_context(method, path):
    f = fixture("ADMIN", category(method, path))
    f["binding"]["method"] = method
    assert encode(f["observation"], f["binding"])["state"] == "WITHHELD"


def oracle(family, role, before, after):
    value = AuthorizationOracle.__new__(AuthorizationOracle)
    value.config = {"family": family, "policy": FAMILIES[family]["policy"]}
    value._before = before | {"actor_role": role}
    value.active = (None, {})
    value.database = lambda *_: after | {"actor_role": role}
    return value


def test_post_requires_real_commit_not_http_status():
    v = oracle("academic-write", "STAFF", {"count": 0}, {"count": 0, "resource": 1000})
    response = {
        "status": 201,
        "payload": {
            "id": 1000,
            "name": "R27 Research Curriculum",
            "majorId": 1,
            "cohort": 2027,
            "degreeType": "BACHELOR",
            "active": True,
        },
    }
    assert v.semantic("r27-academic-write", 201, response, None, None)[0] is False
    v.database = lambda *_: {"actor_role": "STAFF", "count": 1, "resource": 1000}
    assert v.semantic("r27-academic-write", 201, response, None, None)[0] is True


def test_denial_requires_policy_and_unchanged_database():
    v = oracle(
        "user-read",
        "STAFF",
        {"username": "resource", "role": "STAFF"},
        {"username": "tampered", "role": "STAFF"},
    )
    response = {"status": 403, "payload": {"status": 403, "message": "Access denied"}}
    assert v.semantic("r27-user-read", 403, response, None, None)[0] is False
    v.database = lambda *_: v._before
    assert v.semantic("r27-user-read", 403, response, None, None)[0] is True
    v.config["policy"] = "USER_ADMIN_ONLY"
    v._before["actor_role"] = "ADMIN"
    assert v.semantic("r27-user-read", 403, response, None, None)[0] is False


def test_self_owner_must_match_actual_actor():
    before = {"actor_number": 1, "owner": 2, "resource": 101, "marker": "private marker"}
    v = oracle("self-profile", "STUDENT", before, before)
    response = {"status": 200, "payload": {"userId": 1, "id": 101, "fullName": "private marker"}}
    assert v.semantic("r27-self-profile", 200, response, None, None)[0] is False


def test_independence_is_not_claimed_from_ids_or_setup_counts():
    p = lineage_plan()
    assert p["independent_final_exposure_anchors"] == 0
    assert p["setup_in_target_denominator"] is False
    assert {c["policy"] for c in FAMILIES.values()} == {
        "USER_ADMIN_ONLY",
        "SELF_PROFILE_STUDENT_ONLY",
        "ACADEMIC_WRITE_ADMIN_OR_STAFF",
    }


@pytest.mark.parametrize("mask", ["N", "S", "A", "NS", "NA", "SA", "NSA", "NONE"])
def test_inherited_missing_source_semantics(mask):
    f = fixture("STAFF", "ACADEMIC_WRITE", mask)
    f["binding"]["method"] = "POST"
    result = encode(f["observation"], f["binding"])
    assert result["vector"][-3:] == [int(mask != "NONE" and s in mask) for s in "NSA"]
    assert (result["status"] == "CONTEXT_AVAILABLE") == ("A" in mask)


@pytest.mark.parametrize(
    "key,value,state",
    [
        ("request_key", "other-request", "UNTRUSTED"),
        ("scope", "other-producer", "UNTRUSTED"),
        ("available_offset_ns", 999000001, "OBSERVED_LATE"),
        ("phase", "CACHED_SESSION", "UNTRUSTED"),
    ],
)
def test_inherited_identity_lateness_and_no_cache(key, value, state):
    f = fixture("STAFF", "ACADEMIC_WRITE")
    f["binding"]["method"] = "POST"
    f["observation"][key] = value
    assert encode(f["observation"], f["binding"])["state"] == state

"""Causal/trust controls; synthetic tests do not create native observations."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from context import BIND_KEYS, FIELDS, OBS_KEYS, STATES, category, encode, snapshot


def pair(role="STUDENT", category="STUDENT_DIRECTORY", mask="NSA"):
    observation = {
        "request_key": "request-a",
        "scope": "guest-boot-a",
        "event_id": "a1234567-1234-1234-1234-123456789abc",
        "proof_sha256": "a" * 64,
        "receipt_offset_ns": 10_000_000,
        "available_offset_ns": 11_000_000,
        "role": role,
        "actor_session_bound": True,
        "anonymous": False,
        "phase": "CURRENT_REQUEST_AUDIT",
    }
    binding = {
        key: observation[key] for key in ("request_key", "scope", "event_id", "proof_sha256")
    }
    binding |= {
        "identity_verified": True,
        "clock_valid": True,
        "source_mask": mask,
        "category": category,
        "method": "GET",
        "disposition": STATES[0],
    }
    return observation, binding


def test_abi_and_information_contrast():
    a, b = pair("ADMIN")
    c, d = pair("STUDENT")
    assert len(FIELDS) == len(encode(a, b)["vector"]) == 20
    assert encode(a, b)["vector"] != encode(c, d)["vector"]
    assert encode(a, b)["policy_control"] == "ALLOW"
    assert encode(c, d)["policy_control"] == "DENY"
    c, d = pair("STUDENT", "SELF_PRINCIPAL")
    assert encode(c, d)["policy_control"] == "ALLOW"  # role-only shortcut fails
    assert set(a) == OBS_KEYS and set(b) == BIND_KEYS


@pytest.mark.parametrize("mask", ("N", "S", "A", "NS", "NA", "SA", "NSA", "NONE"))
def test_masks_and_no_fake_source(mask):
    a, b = pair(mask=mask)
    result = encode(a, b)
    assert result["vector"][-3:] == [int(mask != "NONE" and s in mask) for s in "NSA"]
    assert (result["status"] == "CONTEXT_AVAILABLE") == ("A" in mask)


@pytest.mark.parametrize("state", STATES[1:])
def test_unavailable_states(state):
    a, b = pair()
    b["disposition"] = state
    v = encode(a, b)
    assert v["status"] == v["policy_control"] == "ABSTAIN"
    assert v["vector"][:11] == [0] * 11
    assert v["vector"][11:17] == [int(state == s) for s in STATES]


@pytest.mark.parametrize(
    "offset,expected",
    [(999_000_000, STATES[0]), (999_000_001, "OBSERVED_LATE"), (1_000_000_000, "OBSERVED_LATE")],
)
def test_cutoff_guard_exact(offset, expected):
    a, b = pair()
    a["available_offset_ns"] = offset
    assert encode(a, b)["state"] == expected


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_key", "request-b"),
        ("scope", "guest-b"),
        ("proof_sha256", "b" * 64),
        ("event_id", "b1234567-1234-1234-1234-123456789abc"),
        ("phase", "PRIOR_SESSION_SNAPSHOT"),
        ("receipt_offset_ns", -1),
        ("actor_session_bound", False),
        ("role", "CLIENT_ADMIN"),
    ],
)
def test_mismatch_stale_and_untrusted(key, value):
    a, b = pair()
    a[key] = value
    assert encode(a, b)["state"] == "UNTRUSTED"


@pytest.mark.parametrize("key", ["identity_verified", "clock_valid"])
def test_integrity_failure(key):
    a, b = pair()
    b[key] = False
    assert encode(a, b)["state"] == "UNTRUSTED"


def test_missing_and_no_cache_rotation_switch_revocation():
    a, b = pair("ADMIN")
    first = copy.deepcopy(encode(a, b))
    # No prior request/session cache is consulted. Account switch uses the new
    # current observation. A revoked session with no current evidence abstains.
    c, d = pair("STUDENT")
    assert encode(c, d)["vector"][4] == 1
    assert encode(None, d)["state"] == "MISSING"
    assert encode(a, b) == first
    a["role"] = None
    a["anonymous"] = True
    a["actor_session_bound"] = False
    assert encode(a, b)["policy_control"] == "ABSTAIN"
    assert encode(a, b)["vector"][:2] == [1, 0]


@pytest.mark.parametrize(
    "path", ["/api/auth/login", "/api/auth/logout", "/api/auth/csrf", "/api/unknown"]
)
def test_mutable_authentication_and_unsupported_paths_withheld(path):
    a, b = pair()
    b["category"] = category("GET", path)
    assert encode(a, b)["state"] == "WITHHELD"


def test_no_response_or_oracle_or_client_headers():
    a, b = pair()
    for key in ("outcome", "status_code", "oracle_label", "headers", "X-Role", "user_id", "cookie"):
        assert encode(a | {key: "ADMIN"}, b)["state"] == "UNTRUSTED"
    raw = {
        "source": "STUDENT_AUDIT",
        "event_type": "http_request",
        "schema_version": "1.0",
        "source_instance": b["scope"],
        "event_id": a["event_id"],
        "role": "STUDENT",
        "user_id": "hmac-sha256:" + "a" * 64,
        "session_hmac": "hmac-sha256:" + "b" * 64,
        "headers": {"X-Role": "ADMIN"},
        "status_code": 403,
        "outcome": "failure",
    }
    fact = {"native_event_id": a["event_id"], "proof_sha256": a["proof_sha256"]}
    view = snapshot(raw, fact, b["request_key"], b["scope"], 10, 20)
    assert view["role"] == "STUDENT" and set(view) == OBS_KEYS
    assert "hmac" not in json.dumps(view)
    with pytest.raises(ValueError):
        snapshot(raw | {"source_instance": "other"}, fact, b["request_key"], b["scope"], 10, 20)


def test_concurrent_request_bindings_and_prefix_invariance():
    a, b = pair("ADMIN")
    c, d = pair("STUDENT")
    c["request_key"] = d["request_key"] = "request-b"
    before = encode(a, b)
    assert encode(c, b)["state"] == "UNTRUSTED"
    assert encode(a, d)["state"] == "UNTRUSTED"
    assert encode(c, d)["status"] == "CONTEXT_AVAILABLE"
    assert encode(a, b) == before


def test_csrf_existing_http_only_session_keeps_real_evidence():
    from types import SimpleNamespace

    from session_transport import install

    def base(*args):
        return False, "ORIGINAL_CSRF_MISSING_SET_COOKIE"

    pilot = SimpleNamespace(semantic_oracle=base)
    install(pilot)
    response = {
        "status": 200,
        "continued_http_only_session": True,
        "csrf_check": {
            "json_type": True,
            "header_declaration": True,
            "masked_uuid": True,
            "http_only_session": False,
        },
    }
    assert pilot.semantic_oracle("csrf", 200, response, None, None) == (
        True,
        "CSRF_SEMANTIC_EXISTING_HTTPONLY_SESSION",
    )
    assert response["csrf_check"]["http_only_session"] is False  # never rewrite proof
    for invalid in (
        dict(response, continued_http_only_session=False),
        dict(response, status=403),
        dict(
            response,
            csrf_check={"json_type": True, "header_declaration": True, "masked_uuid": False},
        ),
    ):
        assert pilot.semantic_oracle("csrf", 200, invalid, None, None)[0] is False
    assert pilot.semantic_oracle("login-admin", 204, response, None, None) == base()


@pytest.mark.parametrize("invalid", [None, [], "client-role", 7])
def test_malformed_binding_abstains(invalid):
    a, b = pair()
    assert encode(a, invalid)["state"] == "UNTRUSTED"
    if invalid is not None:
        assert encode(invalid, b)["state"] == "UNTRUSTED"

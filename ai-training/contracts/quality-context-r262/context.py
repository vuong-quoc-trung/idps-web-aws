"""Private collector ABI. Inputs come from authenticated local evidence, never HTTP headers.

This projection deliberately keeps no session cache. Audit context on a protected
GET describes that request only; login/logout and mutable authentication paths
are withheld. It is advisory context at the 1s decision, not pre-authorization.
"""

import re
from uuid import UUID

SCHEMA = "idps-trusted-context20-r262-v1"
STATES = (
    "AVAILABLE_BEFORE_CUTOFF",
    "OBSERVED_LATE",
    "MISSING",
    "WITHHELD",
    "UNTRUSTED",
    "GROUND_TRUTH_ONLY",
)
ROLES = ("ADMIN", "STAFF", "STUDENT", "OTHER")
CATEGORIES = ("STUDENT_DIRECTORY", "SELF_PRINCIPAL", "AUTHENTICATION", "OTHER")
FIELDS = (
    "authentication_known",
    "authenticated",
    "role_admin",
    "role_staff",
    "role_student",
    "role_other",
    "actor_session_bound",
    "resource_student_directory",
    "resource_self_principal",
    "resource_authentication",
    "resource_other",
    *["state_" + s.lower() for s in STATES],
    "source_n",
    "source_s",
    "source_a",
)
MASKS = ("N", "S", "A", "NS", "NA", "SA", "NSA", "NONE")
HEX = re.compile(r"[a-f0-9]{64}")
PSEUDONYM = re.compile(r"hmac-sha256:[a-f0-9]{64}")
OBS_KEYS = {
    "request_key",
    "scope",
    "event_id",
    "proof_sha256",
    "receipt_offset_ns",
    "available_offset_ns",
    "role",
    "actor_session_bound",
    "anonymous",
    "phase",
}
BIND_KEYS = {
    "request_key",
    "scope",
    "event_id",
    "proof_sha256",
    "identity_verified",
    "clock_valid",
    "source_mask",
    "category",
    "method",
    "disposition",
}


def category(method, path):
    if method == "GET" and re.fullmatch(r"/api/students/[0-9]+", path):
        return "STUDENT_DIRECTORY"
    if method == "GET" and path == "/api/auth/me":
        return "SELF_PRINCIPAL"
    if path.startswith("/api/auth/"):
        return "AUTHENTICATION"
    return "OTHER"


def snapshot(raw, fact, request_key, scope, received, available):
    """Called at actual collector resolution; never reconstruct from posthoc Oracle.

    Actor/session HMACs are validated in memory and discarded. The collector
    retains the full-envelope hash alongside the ownership/correlation proof.
    No status, latency, outcome, policy verdict or Oracle data enters this ABI.
    """
    if (
        raw.get("source") != "STUDENT_AUDIT"
        or raw.get("event_type") != "http_request"
        or raw.get("source_instance") != scope
        or raw.get("schema_version") != "1.0"
        or raw.get("event_id") != fact.get("native_event_id")
    ):
        raise ValueError("Untrusted Audit producer")
    role, actor, session = (raw.get(k) for k in ("role", "user_id", "session_hmac"))
    anonymous = role is None and actor is None and raw.get("username") is None
    bound = bool(PSEUDONYM.fullmatch(str(actor)) and PSEUDONYM.fullmatch(str(session)))
    if not (anonymous or (bound and role in ROLES)):
        raise ValueError("Unresolved current principal")
    return {
        "request_key": request_key,
        "scope": scope,
        "event_id": raw["event_id"],
        "proof_sha256": fact["proof_sha256"],
        "receipt_offset_ns": received,
        "available_offset_ns": available,
        "role": role,
        "actor_session_bound": bound,
        "anonymous": anonymous,
        "phase": "CURRENT_REQUEST_AUDIT",
    }


def encode(observation, binding):
    """Return masked float32-exact booleans, or explicit ABSTAIN.

    binding must be supplied by the trusted collector/correlation registry, not
    by the sender of an observation. Equality with self-asserted JSON is not an
    authentication protocol. This module exposes no network ingestion endpoint.
    """
    if not isinstance(binding, dict):
        binding = {}
    valid_binding = (
        set(binding) == BIND_KEYS
        and binding.get("identity_verified") is True
        and binding.get("clock_valid") is True
        and isinstance(binding.get("request_key"), str)
        and bool(binding["request_key"])
        and isinstance(binding.get("scope"), str)
        and bool(binding["scope"])
        and binding.get("source_mask") in MASKS
        and binding.get("category") in CATEGORIES
        and binding.get("disposition") in STATES
        and binding.get("method") in ("GET", "POST", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE")
    )
    state = binding.get("disposition", "UNTRUSTED") if valid_binding else "UNTRUSTED"
    valid_observation = isinstance(observation, dict) and set(observation) == OBS_KEYS
    if valid_observation:
        try:
            valid_observation = (
                str(UUID(observation["event_id"])) == observation["event_id"]
                and bool(HEX.fullmatch(observation["proof_sha256"]))
                and all(
                    observation[k] == binding.get(k)
                    for k in ("request_key", "scope", "event_id", "proof_sha256")
                )
                and observation["phase"] == "CURRENT_REQUEST_AUDIT"
                and type(observation["receipt_offset_ns"]) is int
                and type(observation["available_offset_ns"]) is int
                and 0 <= observation["receipt_offset_ns"] <= observation["available_offset_ns"]
                and type(observation["anonymous"]) is bool
                and type(observation["actor_session_bound"]) is bool
                and (
                    (
                        observation["anonymous"]
                        and observation["role"] is None
                        and observation["actor_session_bound"] is False
                    )
                    or (
                        not observation["anonymous"]
                        and observation["role"] in ROLES
                        and observation["actor_session_bound"] is True
                    )
                )
            )
        except (ValueError, TypeError, KeyError):
            valid_observation = False
    if state == "AVAILABLE_BEFORE_CUTOFF":
        if observation is None:
            state = "MISSING"
        elif not valid_observation:
            state = "UNTRUSTED"
        elif observation["available_offset_ns"] > 999_000_000:
            state = "OBSERVED_LATE"
        elif "A" not in binding["source_mask"]:
            state = "UNTRUSTED"
        elif binding["method"] != "GET" or binding["category"] not in CATEGORIES[:2]:
            state = "WITHHELD"
    available = state == "AVAILABLE_BEFORE_CUTOFF"
    role = observation["role"] if available else None
    values = [int(available), int(available and not observation["anonymous"])]
    values += [int(available and role == r) for r in ROLES]
    values += [int(available and observation["actor_session_bound"])]
    # Category is only exposed with trusted, supported current-request context.
    values += [int(available and binding["category"] == c) for c in CATEGORIES]
    values += [int(state == s) for s in STATES]
    values += [
        int(valid_binding and binding["source_mask"] != "NONE" and s in binding["source_mask"])
        for s in "NSA"
    ]
    return {
        "schema": SCHEMA,
        "state": state,
        "vector": values,
        "status": "CONTEXT_AVAILABLE" if available else "ABSTAIN",
        "policy_control": policy_control(role, binding.get("category")) if available else "ABSTAIN",
    }


def policy_control(role, resource):
    """Separate deterministic advisory, never an ML score or enforcement action."""
    if role not in ROLES:
        return "ABSTAIN"
    if resource == "STUDENT_DIRECTORY":
        return "ALLOW" if role in ("ADMIN", "STAFF") else "DENY"
    return "ALLOW" if resource == "SELF_PRINCIPAL" else "ABSTAIN"

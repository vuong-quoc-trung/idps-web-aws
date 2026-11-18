"""Guest-only first-party policy/Oracle witness, independent of runner intent."""

import hmac
import json
import re
import time

from idps_ai.common import digest

PSEUDONYM = re.compile(r"hmac-sha256:[a-f0-9]{64}")


class AuthorizationOracle:
    def __init__(self, audit_path, scope, secret, rpc):
        self.audit_path, self.scope, self.secret, self.rpc = audit_path, scope, secret, rpc
        self.principals = {}

    def snapshot(self, db, row):
        if row["oracle"] != "record":
            return None
        actor = self.principals.get(row["session"])
        if actor is None:
            raise ValueError("REQUEST_BOUND_PRINCIPAL_REQUIRED")
        return self.rpc(db, f"ROLE {actor['database_id']}"), int(
            self.rpc(db, f"OWNER {row['record']}")
        )

    def observe(self, row, rid, result, db, before):
        principal_request = row["oracle"].startswith("principal-")
        if not principal_request and row["oracle"] != "record":
            return None
        observations = [e for e in result["events"] if e["source"] == "A"]
        if not (
            rid
            and result["request_key"]
            and result["identity_verified"]
            and result["clock_valid"]
            and result["oracle_verified"]
            and len(observations) == 1
        ):
            raise ValueError("SEMANTIC_AUDIT_BINDING_REQUIRED")
        events = [
            event
            for line in self.audit_path.read_text().splitlines()
            if (event := json.loads(line)).get("request_id") == rid
            and event.get("source_instance") == self.scope
        ]
        if len(events) != 1 or events[0].get("event_id") != observations[0]["native_event_id"]:
            raise ValueError("SEMANTIC_AUDIT_IDENTITY_AMBIGUOUS")
        actor, session, role = (events[0].get(name) for name in ("user_id", "session_hmac", "role"))
        if not (
            role in {"ADMIN", "STUDENT"}
            and PSEUDONYM.fullmatch(str(actor))
            and PSEUDONYM.fullmatch(str(session))
        ):
            raise ValueError("ACTOR_SESSION_OR_ROLE_UNRESOLVED")
        if principal_request:
            number = 1 if row["oracle"] == "principal-admin" else 2
            db_role = self.rpc(db, f"ROLE {number}")
            if result["oracle_basis"] != "PRINCIPAL_AND_JDBC_ROLE" or role != db_role:
                raise ValueError("PRINCIPAL_ROLE_ORACLE_MISMATCH")
            self.principals[row["session"]] = {
                "actor": actor,
                "session": session,
                "role": role,
                "database_id": number,
                "request_key": result["request_key"],
                "proof": observations[0]["proof_sha256"],
            }
            return None
        principal = self.principals[row["session"]]
        after = self.snapshot(db, row)
        if not (
            before == after
            and role == principal["role"] == after[0]
            and (actor, session) == (principal["actor"], principal["session"])
            and after[1] == row["record"]
        ):
            raise ValueError("ACTOR_POLICY_OWNER_NOT_STABLE")
        expected_authorized = role in {"ADMIN", "STAFF"}
        allowed = result["oracle_basis"] == "RECORD_ID_AND_JDBC_MARKER"
        denied = result["oracle_basis"] == "DENIAL_WITHOUT_JDBC_MARKER"
        if not ((expected_authorized and allowed) or (not expected_authorized and denied)):
            raise ValueError("SEMANTIC_APPLICATION_OUTCOME_MISMATCH")
        proof = {
            "request_key": result["request_key"],
            "policy": "STUDENT_RECORD_READ_ADMIN_OR_STAFF",
            "actor_role": role,
            "actor_session_matches_principal": True,
            "principal_request_key": principal["request_key"],
            "principal_audit_proof_sha256": principal["proof"],
            "target_audit_proof_sha256": observations[0]["proof_sha256"],
            "owner_scope_alias": hmac.digest(
                self.secret, f"owner:{after[1]}".encode(), "sha256"
            ).hex(),
            "resource_owner_differs_from_actor": after[1] != principal["database_id"],
            "owner_stable_before_after": True,
            "owner_matches_fixture_record": True,
            "expected_authorized": expected_authorized,
            "observed_action": "ALLOWED" if allowed else "DENIED",
            "application_outcome": result["oracle_basis"],
            "scope": "GROUND_TRUTH_ONLY",
            "label_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "label": "BENIGN_VERIFIED" if expected_authorized else "ATTACK_VERIFIED",
            "exploit_outcome": "not_applicable" if expected_authorized else "failed",
            "observed_offset_ns": time.monotonic_ns() - result["send_monotonic_ns"],
        }
        return proof | {"sha256": digest(proof)}

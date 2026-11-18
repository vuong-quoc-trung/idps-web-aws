"""Guest-only independent JDBC/application witness; never supplies model features."""

import json
import re
import time
from pathlib import Path

from idps_ai.common import digest

PSEUDONYM = re.compile(r"hmac-sha256:[a-f0-9]{64}")


class AuthorizationOracle:
    def __init__(self, audit_path, scope, secret, rpc):
        self.audit_path, self.scope, self.rpc = audit_path, scope, rpc
        self.config = json.loads(Path("/lab/r27-plan.json").read_text())
        self.principals = {}
        self.active = self.state = None
        import campaign_guest

        self.original_semantic = campaign_guest.pilot.semantic_oracle
        campaign_guest.pilot.semantic_oracle = self.semantic

    def database(self, db, row):
        number = 1 if row["account"] == "admin" else 2
        result = {"actor_role": self.rpc(db, f"ROLE {number}"), "actor_number": number}
        family = self.config["family"]
        if family == "user-read":
            result.update(
                resource=2,
                username=self.rpc(db, "USERNAME 2"),
                role=self.rpc(db, "ROLE 2"),
                enabled=self.rpc(db, "ENABLED 2"),
            )
        elif family == "self-profile":
            record = int(self.rpc(db, f"SELF {number}"))
            result.update(
                resource=record,
                owner=int(self.rpc(db, f"OWNER {record}")),
                marker=self.rpc(db, f"MARK {record}"),
            )
        else:
            count = int(self.rpc(db, "PCOUNT 1"))
            result.update(count=count, resource=int(self.rpc(db, "PID 1")) if count else None)
        return result

    def snapshot(self, db, row):
        self.active = (db, row)
        self.state = None
        if row["population"] != "TARGET":
            return None
        self._before = self.database(db, row)
        return self._before

    def allowed(self, role):
        policy = self.config["policy"]
        if policy == "USER_ADMIN_ONLY":
            return role == "ADMIN"
        if policy == "SELF_PROFILE_STUDENT_ONLY":
            return role == "STUDENT"
        if policy == "ACADEMIC_WRITE_ADMIN_OR_STAFF":
            return role in ("ADMIN", "STAFF")
        raise ValueError("Unknown policy")

    def semantic(self, rule, expected, response, before, after):
        if not rule.startswith("r27-"):
            return self.original_semantic(rule, expected, response, before, after)
        db, row = self.active
        start = self.database_before
        end = self.database(db, row)
        allowed = self.allowed(start["actor_role"])
        body = response.get("payload")
        stable = start["actor_role"] == end["actor_role"]
        if not allowed:
            valid = (
                stable
                and body == {"status": 403, "message": "Access denied"}
                and response["status"] == 403
                and start == end
            )
            basis = "POLICY_DENIAL_AND_JDBC_NO_MUTATION"
        elif self.config["family"] == "user-read":
            valid = (
                stable
                and response["status"] == 200
                and isinstance(body, dict)
                and start == end
                and body.get("id") == start["resource"]
                and body.get("username") == start["username"]
                and body.get("role") == start["role"]
                and str(body.get("enabled")).lower() == start["enabled"].lower()
            )
            basis = "USER_IDENTITY_FIELDS_AND_JDBC"
        elif self.config["family"] == "self-profile":
            valid = (
                stable
                and response["status"] == 200
                and isinstance(body, dict)
                and start == end
                and start["owner"] == start["actor_number"]
                and body.get("userId") == start["actor_number"]
                and body.get("id") == start["resource"]
                and body.get("fullName") == start["marker"]
            )
            basis = "PRINCIPAL_RESOLVED_SELF_OWNER_AND_JDBC_MARKER"
        else:
            valid = (
                stable
                and response["status"] == 201
                and isinstance(body, dict)
                and start["count"] == 0
                and end["count"] == 1
                and body.get("id") == end["resource"]
                and body.get("name") == "R27 Research Curriculum"
                and body.get("majorId") == 1
                and body.get("cohort") == 2027
                and body.get("degreeType") == "BACHELOR"
                and body.get("active") is True
            )
            basis = "COMMITTED_PROGRAM_ROW_AND_RESPONSE_FIELDS"
        valid = bool(valid and expected == response["status"])
        self.state = {
            "verified": valid,
            "basis": basis,
            "before": start,
            "after": end,
            "allowed": allowed,
        }
        return valid, basis

    @property
    def database_before(self):
        return self._before

    def observe(self, row, rid, result, db, before):
        principal = row["oracle"].startswith("principal-")
        if not principal and row["population"] != "TARGET":
            return None
        facts = [f for f in result["events"] if f["source"] == "A"]
        events = [
            e
            for line in self.audit_path.read_text().splitlines()
            if (e := json.loads(line)).get("request_id") == rid
            and e.get("source_instance") == self.scope
        ]
        if not (
            result["oracle_verified"]
            and result["identity_verified"]
            and result["clock_valid"]
            and len(facts) == len(events) == 1
            and events[0]["event_id"] == facts[0]["native_event_id"]
        ):
            raise ValueError("Request-bound semantic proof unavailable")
        raw = events[0]
        actor, session, role = (raw.get(k) for k in ("user_id", "session_hmac", "role"))
        number = 1 if row["account"] == "admin" else 2
        if not (
            role == self.rpc(db, f"ROLE {number}")
            and role == self.config["actors"][number - 1]
            and PSEUDONYM.fullmatch(str(actor))
            and PSEUDONYM.fullmatch(str(session))
        ):
            raise ValueError("Principal role provenance mismatch")
        if principal:
            self.principals[row["session"]] = {
                "actor": actor,
                "session": session,
                "role": role,
                "key": result["request_key"],
                "proof": facts[0]["proof_sha256"],
            }
            return None
        parent = self.principals[row["session"]]
        if (
            (actor, session, role) != (parent["actor"], parent["session"], parent["role"])
            or not self.state
            or not self.state["verified"]
        ):
            raise ValueError("Actor/session or application state not verified")
        proof = {
            "request_key": result["request_key"],
            "label_task": "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT",
            "label": "BENIGN_VERIFIED" if self.state["allowed"] else "ATTACK_VERIFIED",
            "policy": self.config["policy"],
            "family": self.config["family"],
            "actor_role": role,
            "actor_session_matches_principal": True,
            "principal_request_key": parent["key"],
            "principal_audit_proof_sha256": parent["proof"],
            "target_audit_proof_sha256": facts[0]["proof_sha256"],
            "resource_relation": "SELF"
            if self.config["family"] == "self-profile"
            else "GLOBAL_CATALOG"
            if self.config["family"] == "academic-write"
            else "SELF"
            if number == 2
            else "OTHER_ACTOR",
            "owner_relationship_verified": self.config["family"] == "self-profile",
            "database_before_sha256": digest(self.state["before"]),
            "database_after_sha256": digest(self.state["after"]),
            "mutation_committed": self.config["family"] == "academic-write"
            and self.state["allowed"],
            "application_basis": self.state["basis"],
            "expected_authorized": self.state["allowed"],
            "observed_action": "ALLOWED" if self.state["allowed"] else "DENIED",
            "scope": "GROUND_TRUTH_ONLY",
            "observed_offset_ns": time.monotonic_ns() - result["send_monotonic_ns"],
            "independent_human_review": False,
            "exploit_success": False,
        }
        return proof | {"sha256": digest(proof)}

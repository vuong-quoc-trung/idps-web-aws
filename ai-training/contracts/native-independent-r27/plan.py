"""Preregistered task populations; routine setup is never a target feature view."""

TASK = "AUTHORIZATION_POLICY_VIOLATION_ATTEMPT"
FAMILIES = {
    "user-read": {
        "role": "TRAIN",
        "actors": ["ADMIN", "STAFF"],
        "method": "GET",
        "path": "/api/users/2",
        "policy": "USER_ADMIN_ONLY",
        "expected": [200, 403],
        "category": "USER_ADMIN",
        "resource": 2,
    },
    "self-profile": {
        "role": "DEV",
        "actors": ["STUDENT", "ADMIN"],
        "method": "GET",
        "path": "/api/me/profile",
        "policy": "SELF_PROFILE_STUDENT_ONLY",
        "expected": [200, 403],
        "category": "SELF_PROFILE",
        "resource": None,
    },
    "academic-write": {
        "role": "DEV",
        "actors": ["STAFF", "STUDENT"],
        "method": "POST",
        "path": "/api/training-programs",
        "policy": "ACADEMIC_WRITE_ADMIN_OR_STAFF",
        "expected": [201, 403],
        "category": "ACADEMIC_WRITE",
        "resource": None,
    },
}
PROGRAM = {
    "name": "R27 Research Curriculum",
    "majorId": 1,
    "cohort": 2027,
    "degreeType": "BACHELOR",
    "active": True,
}


def configuration(family):
    cfg = dict(FAMILIES[family], family=family)
    cfg["usernames"] = {
        "admin": "r27_" + family.replace("-", "_") + "_first",
        "student": "r27_" + family.replace("-", "_") + "_second",
    }
    return cfg


def roster(family):
    cfg = configuration(family)
    rows = []
    for account, expected in zip(("admin", "student"), cfg["expected"], strict=True):
        actions = [
            ("GET", "/api/auth/csrf", "csrf", 200),
            ("POST", "/api/auth/login", "login-" + account, 204),
            ("GET", "/api/auth/me", "principal-" + account, 200),
        ]
        if cfg["method"] == "POST":
            actions.append(("GET", "/api/auth/csrf", "csrf", 200))
        actions.append((cfg["method"], cfg["path"], "r27-" + family, expected))
        for method, path, oracle, status in actions:
            rows.append(
                {
                    "attempt": len(rows) + 1,
                    "method": method,
                    "path": path,
                    "target": path,
                    "oracle": oracle,
                    "expected_status": status,
                    "record": None,
                    "account": account,
                    "session": family + "-" + account,
                    "intent": "UNUSED_FOR_GROUND_TRUTH",
                    "population": "TARGET"
                    if oracle.startswith("r27-")
                    else "SESSION_SETUP_CONTROL",
                    "label_task": TASK
                    if oracle.startswith("r27-")
                    else "SESSION_ESTABLISHMENT_CONTROL",
                }
            )
    return rows


def lineage_plan():
    return {
        "version": "idps-r27-task-scoped-lineage-v1",
        "task": TASK,
        "primary_ABI": "idps-uri100-context22-r27-v1",
        "setup_in_target_denominator": False,
        "setup_custody": "All setup receipts remain in each campaign/session component. They have no eligible target-task feature representation; coarse URI-only baseline or WITHHELD vectors do not assert target-sample equivalence.",
        "exact_edges": "Task + primary ABI + valid full feature view; preserve physical/session/campaign/actor/material-template and verified near edges even for rejected TARGET records.",
        "not_independence": "Different ID, hash, seed, guest or username is not sufficient. These three workflows have different role requirements, resource resolution and application outcomes (user read, self-owner read, committed catalog mutation).",
        "roles": {family: cfg["role"] for family, cfg in FAMILIES.items()},
        "planned_material_components": 3,
        "independent_final_exposure_anchors": 0,
        "scope": "WITHIN_LOCAL_LAB_POLICY_FAMILY_DISJOINT_RESEARCH_ONLY",
        "CAL_FIT_CAL_OP_TEST": "NOT_ACQUIRED; no claim of representative independent final evaluation",
        "fail_closed": "Any actual cross-role physical/exact/material/verified-near/protected link quarantines the connected component; never delete a bridge to obtain a split.",
        "old_R262_component_unchanged": True,
        "different_task_publisher_URI_views": "Do not equate publisher payload anomaly and authorization samples or fabricate cross-schema identity from coarse feature equality.",
    }

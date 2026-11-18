"""Only nonsecret lab configuration; credentials remain in guest memory."""

import json
from pathlib import Path


def login_username(oracle):
    if oracle not in ("login-admin", "login-student"):
        raise ValueError("Unsupported login role")
    return json.loads(Path("/lab/r27-plan.json").read_text())["usernames"][
        oracle.removeprefix("login-")
    ]


def program_body():
    return json.dumps(
        {
            "name": "R27 Research Curriculum",
            "majorId": 1,
            "cohort": 2027,
            "degreeType": "BACHELOR",
            "active": True,
        },
        separators=(",", ":"),
    )

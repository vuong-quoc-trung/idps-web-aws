#!/usr/bin/env python3
"""Finite Oracle gap cohort using the existing isolated lab collector, no models."""

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

import psutil

from idps_ai.common import atomic_json, digest, file_sha256

RUN = "attack-intent-20261107-v1"
ROOT = Path(__file__).resolve().parents[2]


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def cases():
    rows = []

    def add(env, role, group, family, method, path, fields, rule, expected, attack=False):
        rows.append(
            dict(
                case_id=f"gap-{len(rows):03}",
                request_id=digest([RUN, len(rows)])[:32],
                environment=env,
                role=role,
                workflow=group,
                campaign=RUN + ":" + role + ":" + group,
                family=family,
                intent="ATTACK_ATTEMPT" if attack else "BENIGN",
                method=method,
                path=path + ("?" + urlencode(fields) if method == "GET" and fields else ""),
                body=(json.dumps(fields) if env == "juice" else urlencode(fields))
                if method == "POST"
                else "",
                oracle=rule,
                expected=expected,
            )
        )

    # Technical text vs active markup on the same surface; no nonce-count padding.
    for value in [
        "Shell notes: printf '%s' value | cat; not an executable action.",
        "SQL lesson: SELECT fruit FROM basket WHERE price > 2;",
        "HTML notes: a < b && b > c, JSON {items:[1,2]}.",
    ]:
        add(
            "dvwa",
            "TRAIN",
            "stored-technical-literal",
            "benign",
            "POST",
            "/vulnerabilities/xss_s/",
            {"txtName": "LabReader", "mtxMessage": value, "btnSign": "Sign Guestbook"},
            "stored_literal",
            value,
        )
    for value in [
        '<iframe src="javascript:alert(41)"></iframe>',
        '<button onclick="alert(42)">press</button>',
    ]:
        add(
            "dvwa",
            "TRAIN",
            "stored-interactive-markup",
            "xss",
            "POST",
            "/vulnerabilities/xss_s/",
            {"txtName": "LabReader", "mtxMessage": value, "btnSign": "Sign Guestbook"},
            "unsafe_stored_reflection",
            value,
            True,
        )
    for value, marker in [
        ("127.0.0.1; printf '%s' AI_INTENT_PIPE | cat", "AI_INTENT_PIPE"),
        ("127.0.0.1; true && printf '%s' AI_INTENT_AND", "AI_INTENT_AND"),
    ]:
        add(
            "dvwa",
            "TRAIN",
            "command-pipeline-and-control",
            "cmd_injection",
            "POST",
            "/vulnerabilities/exec/",
            {"ip": value, "Submit": "Submit"},
            "command_stdout_canary",
            marker,
            True,
        )
    for value in [
        "SELECT & filter are words in this note",
        "A price comparison: 2 < 3; pipe | is text",
    ]:
        add(
            "dvwa",
            "CALIBRATION",
            "reflected-technical-literal",
            "benign",
            "GET",
            "/vulnerabilities/xss_r/",
            {"name": value},
            "literal_name_reflection",
            value,
        )
    add(
        "dvwa",
        "CALIBRATION",
        "public-file-read",
        "benign",
        "GET",
        "/vulnerabilities/fi/",
        {"page": "file2.php"},
        "included_public_page",
        "file2.php",
    )
    for role, descriptions in [
        ("TRAIN", ["Benign quote O'Connor; x < y", "Legitimate JSON {a:2} and path a/b"]),
        ("CALIBRATION", ["Account for literal SELECT notes"]),
    ]:
        for text in descriptions:
            email = f"intent{len(rows)}@example.test"
            add(
                "juice",
                role,
                "account-create",
                "benign",
                "POST",
                "/api/Users/",
                {
                    "email": email,
                    "password": "Fixture-only!7X",
                    "passwordRepeat": "Fixture-only!7X",
                    "securityQuestion": {"id": 1, "question": "Your eldest siblings middle name?"},
                    "securityAnswer": text,
                },
                "created_user",
                email,
            )
    add(
        "juice",
        "TRAIN",
        "login-sql-bypass",
        "sqli",
        "POST",
        "/rest/user/login",
        {"email": "' OR 1=1--", "password": "fixture-wrong"},
        "admin_auth_bypass",
        None,
        True,
    )
    for email in ["not-an-account@example.test", "'literal-note@example.test"]:
        add(
            "juice",
            "CALIBRATION",
            "ordinary-login-denial",
            "benign",
            "POST",
            "/rest/user/login",
            {"email": email, "password": "fixture-wrong"},
            "invalid_login_denied",
            None,
        )
    for value in ["apple", "no-intent-product-match"]:
        add(
            "juice",
            "CALIBRATION",
            "catalog-search",
            "benign",
            "GET",
            "/rest/products/search",
            {"q": value},
            "catalog_search",
            value,
        )
    return rows


def collector():
    q = module("quality-lab-cohort")
    q.RUN = RUN
    q.LABEL = "idps.research-run=" + RUN
    q.PORT = 17280
    q.PROXY = 17281
    original_pm = q.pm

    def limited_pm(*args, **kwargs):
        return original_pm(*["--cpus=.25" if a == "--cpus=.5" else a for a in args], **kwargs)

    q.pm = limited_pm
    # The existing collector launches this entrypoint for its ownership-bound watchdog.
    q.__file__ = str(Path(__file__).resolve())
    return q


def watchdog(root, q):
    thermal = module("p0-thermal-run")
    reason = "COMPLETED"
    last = None
    (root / "watchdog-ready").touch()
    try:
        while not (root / "watchdog-done").exists():
            now = time.monotonic()
            temp = max(v["celsius"] for v in thermal.cpu_sensors().values())
            rapid = last and (temp - last[1]) / max(now - last[0], 0.001) >= 5 and temp >= 77
            if (
                temp >= 80
                or rapid
                or time.time() - (root / "heartbeat").stat().st_mtime > 4
                or psutil.virtual_memory().available < 4 * 1024**3
            ):
                reason = "CONSERVATIVE_THERMAL_OR_MEMORY_OR_HEARTBEAT_STOP"
                q.stop_owned()
                break
            last = (now, temp)
            time.sleep(0.2)
    except BaseException:
        reason = "SENSOR_OR_SUPERVISOR_FAILURE"
        q.stop_owned()
    finally:
        atomic_json(
            root / "lab-watchdog-result.json",
            dict(reason=reason, owner=RUN, instant_stop_C=80, MemAvailable_reserve_GiB=4),
        )


def prepare(root, phase):
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=False)
    rows = cases()
    if phase == "preflight":
        # Fresh fixtures exercise each selected application Oracle before the cohort.
        chosen = {}
        for c in rows:
            chosen.setdefault((c["environment"], c["oracle"]), c)
        rows = list(chosen.values())
    plan = dict(
        schema_version="attack-intent-gap-capture-1",
        run_id=RUN,
        phase=phase,
        source_sha256=file_sha256(__file__),
        collector_sha256=file_sha256(Path(__file__).with_name("quality-lab-cohort.py")),
        helper_sha256={
            n: file_sha256(Path(__file__).with_name(n + ".py"))
            for n in ["p0-dvwa-capture", "juice-gt-factory", "p0-thermal-run"]
        },
        cases=rows,
        models_loaded=False,
        roles_locked_before_HTTP=True,
        prospective_capture=False,
        scope="Target existing POST/JSON/technical-hard-negative gaps and runtime body-loss; not independent cross-domain evidence",
    )
    plan["plan_sha256"] = digest(plan)
    atomic_json(root / "plan.json", plan)


def run(root):
    plan = json.loads((root / "plan.json").read_text())
    assert plan["collector_sha256"] == file_sha256(
        Path(__file__).with_name("quality-lab-cohort.py")
    )
    if plan["phase"] == "cohort":
        pre = json.loads((root.parent / "preflight/preflight-result.json").read_text())
        assert pre["status"] == "PASS"
    q = collector()
    q.run(root)
    report = json.loads((root / "capture.json").read_text())
    if plan["phase"] == "preflight":
        failures = [r["oracle"] for r in report["observations"] if not r["semantic_oracle_matched"]]
        atomic_json(
            root / "preflight-result.json",
            dict(
                status="FAIL" if failures else "PASS",
                failed_Oracle_rules=failures,
                requests=len(report["observations"]),
                plan_sha256=plan["plan_sha256"],
                capture_sha256=file_sha256(root / "capture.json"),
            ),
        )


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("command", choices=["prepare", "run", "watchdog"])
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--phase", choices=["preflight", "cohort"], default="cohort")
    args = a.parse_args()
    root = args.output.resolve()
    if args.command == "prepare":
        prepare(root, args.phase)
    elif args.command == "run":
        run(root)
    else:
        watchdog(root, collector())

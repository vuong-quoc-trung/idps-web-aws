#!/usr/bin/env python3
"""Finite, isolated two-app cohort using existing P0 receipt/oracle primitives.

No model loads during capture. Oracle labels are internal research evidence;
independent review remains pending. Raw fixture/session evidence is local only.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

import psutil

from idps_ai.common import atomic_json, digest, file_sha256

ROOT = Path(__file__).resolve().parents[2]
RUN = "quality-lab-20261107-v1"
PORT = 15280
PROXY = 15281
JUICE = "docker.io/bkimminich/juice-shop@sha256:318714401c46c3c0a2458b5dccfc84af8e4839181d1a723701f8a6822b19294f"
LABEL = "idps.research-run=" + RUN


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def pm(*args, check=True):
    r = subprocess.run(
        ["podman", *map(str, args)], capture_output=True, text=True, timeout=60, check=False
    )
    if check and r.returncode:
        raise RuntimeError(
            "Owned lab command failed: " + args[0] + "; see private container diagnostics"
        )
    return r.stdout.strip()


def owned():
    return pm("ps", "-aq", "--filter", "label=" + LABEL).split()


def stop_owned():
    for cid in owned():
        info = json.loads(pm("inspect", cid))[0]
        if info.get("Config", {}).get("Labels", {}).get("idps.research-run") != RUN:
            raise RuntimeError("Ownership mismatch")
        pm("kill", cid, check=False)


def remove_finished_container(name, diagnostic):
    removed = subprocess.run(
        ["podman", "rm", "-f", name], capture_output=True, text=True, check=False
    )
    if removed.returncode:
        atomic_json(
            diagnostic,
            {"operation": "rm", "returncode": removed.returncode, "stderr": removed.stderr},
        )
        exists = subprocess.run(
            ["podman", "container", "exists", name], capture_output=True, check=False
        ).returncode
        if exists != 1:
            raise RuntimeError(
                "Named lab cleanup not verified; container exists or existence check failed"
            )


def watchdog(root):
    sensor = module("p0-thermal-run")
    reason = "COMPLETED"
    (root / "watchdog-ready").touch()
    try:
        while not (root / "watchdog-done").exists():
            temp = max(v["celsius"] for v in sensor.cpu_sensors().values())
            stale = time.time() - (root / "heartbeat").stat().st_mtime > 4
            if temp >= 90 or stale or psutil.virtual_memory().available < 3 * 1024**3:
                reason = (
                    "EMERGENCY_TEMPERATURE"
                    if temp >= 90
                    else ("STALE_COLLECTOR" if stale else "RAM_RESERVE")
                )
                stop_owned()
                break
            time.sleep(0.2)
    except BaseException:
        reason = "SENSOR_OR_SUPERVISOR_FAILURE"
        stop_owned()
    finally:
        atomic_json(root / "lab-watchdog-result.json", {"reason": reason, "owner": RUN})


def cases():
    result = []

    def add(env, role, family, intent, method, path, body, oracle, expected=None):
        i = len(result)
        result.append(
            {
                "case_id": f"{env}-{i:03d}",
                "request_id": digest([RUN, env, i])[:32],
                "environment": env,
                "role": role,
                "campaign": env + ":" + role + ":" + oracle,
                "family": family,
                "intent": intent,
                "method": method,
                "path": path,
                "body": body,
                "oracle": oracle,
                "expected": expected,
            }
        )

    notes = [
        "Meeting at noon",
        "Budget 2+2=4",
        "O'Connor is a test name",
        "Rock & roll notes",
        "Use a < b in algebra",
        "C++ class discussion",
        "JSON braces {one:2}",
        "A path like a/b/c",
        "Tea; coffee; water",
        "Pipe symbol | in notes",
        "Search: apple & pear",
        "Question? Answer!",
    ]
    for text in notes:
        add(
            "dvwa",
            "TRAIN",
            "benign",
            "BENIGN",
            "POST",
            "/vulnerabilities/xss_s/",
            urlencode({"txtName": "LabReader", "mtxMessage": text, "btnSign": "Sign Guestbook"}),
            "stored_literal",
            text,
        )
    for payload in [
        "<script>alert(7)</script>",
        "<img src=x onerror=alert(7)>",
        "<svg onload=alert(7)>",
        "<details open ontoggle=alert(7)>x</details>",
        "<input autofocus onfocus=alert(7)>",
        '<a href="javascript:alert(7)">go</a>',
    ]:
        add(
            "dvwa",
            "TRAIN",
            "xss",
            "ATTACK_ATTEMPT",
            "POST",
            "/vulnerabilities/xss_s/",
            urlencode({"txtName": "LabReader", "mtxMessage": payload, "btnSign": "Sign Guestbook"}),
            "unsafe_stored_reflection",
            payload,
        )
    for n in range(1, 6):
        add(
            "dvwa",
            "CALIBRATION",
            "benign",
            "BENIGN",
            "GET",
            "/vulnerabilities/sqli/?" + urlencode({"id": str(n), "Submit": "Submit"}),
            "",
            "user_identity_rows",
            n,
        )
    for file in ["file1.php", "file2.php", "file3.php"]:
        add(
            "dvwa",
            "CALIBRATION",
            "benign",
            "BENIGN",
            "GET",
            "/vulnerabilities/fi/?" + urlencode({"page": file}),
            "",
            "included_public_page",
            file,
        )
    for value in ["99999", "1", "2"]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "benign",
            "BENIGN",
            "GET",
            "/vulnerabilities/sqli_blind/?" + urlencode({"id": value, "Submit": "Submit"}),
            "",
            "blind_identity",
            int(value) < 6,
        )
    for value in [
        "99999' OR 1=1#",
        "99999' OR 'x'='x'#",
        "99999' OR user_id>0#",
        "99999' OR TRUE#",
    ]:
        add(
            "dvwa",
            "PROSPECTIVE_EVALUATION",
            "sqli",
            "ATTACK_ATTEMPT",
            "GET",
            "/vulnerabilities/sqli_blind/?" + urlencode({"id": value, "Submit": "Submit"}),
            "",
            "blind_injection",
            True,
        )
    for value in [
        "Alice",
        "a+b",
        "Notes & plans",
        "O'Connor",
        "<script>alert(8)</script>",
        "<svg onload=alert(8)>",
    ]:
        attack = value.startswith("<")
        add(
            "dvwa",
            "DEVELOPMENT",
            "xss" if attack else "benign",
            "ATTACK_ATTEMPT" if attack else "BENIGN",
            "GET",
            "/vulnerabilities/xss_r/?" + urlencode({"name": value}),
            "",
            "unsafe_reflection_only_no_browser_execution" if attack else "literal_name_reflection",
            value,
        )
    for i, syntax in enumerate(["; printf MARK", "| printf MARK", "&& printf MARK", "; echo MARK"]):
        mark = f"AIDPSN7CMD{i}"
        value = "127.0.0.1 " + syntax.replace("MARK", mark)
        add(
            "dvwa",
            "DEVELOPMENT",
            "cmd_injection",
            "ATTACK_ATTEMPT",
            "POST",
            "/vulnerabilities/exec/",
            urlencode({"ip": value, "Submit": "Submit"}),
            "command_stdout_canary",
            mark,
        )
    for value in [
        "/tmp/ai-idps-p0-canary.txt",
        "../../../../../../tmp/ai-idps-p0-canary.txt",
        "php://filter/convert.base64-encode/resource=/tmp/ai-idps-p0-canary.txt",
    ]:
        add(
            "dvwa",
            "DEVELOPMENT",
            "path_traversal",
            "ATTACK_ATTEMPT",
            "GET",
            "/vulnerabilities/fi/?" + urlencode({"page": value}),
            "",
            "included_private_canary",
            "private canary",
        )
    for word in [
        "apple",
        "orange",
        "banana",
        "carrot",
        "lemon",
        "juice",
        "coffee",
        "tea",
        "shirt",
        "strawberry",
    ]:
        add(
            "juice",
            "TRAIN",
            "benign",
            "BENIGN",
            "GET",
            "/rest/products/search?" + urlencode({"q": word}),
            "",
            "catalog_search",
            word,
        )
    for obj in [
        {"email": "nobody+lab@example.invalid", "password": "not-the-password"},
        {"email": "wrong.person@example.invalid", "password": "a different phrase"},
    ]:
        add(
            "juice",
            "TRAIN",
            "benign",
            "BENIGN",
            "POST",
            "/rest/user/login",
            json.dumps(obj),
            "invalid_login_denied",
        )
    add(
        "juice",
        "TRAIN",
        "sqli",
        "ATTACK_ATTEMPT",
        "POST",
        "/rest/user/login",
        json.dumps({"email": "' or 1=1--", "password": "not-the-password"}),
        "admin_auth_bypass",
    )
    for n in [1, 2, 3, 5, 8, 13]:
        add(
            "juice",
            "CALIBRATION",
            "benign",
            "BENIGN",
            "GET",
            f"/api/Products/{n}",
            "",
            "catalog_identity",
            n,
        )
    for text in [
        "ordinary shopping note",
        "2+2=4 is arithmetic",
        "O'Connor wrote a review",
        "I prefer apples & tea",
    ]:
        # A separate normal account is setup-only; semantic result must verify registration.
        email = f"lab{len(result)}@example.invalid"
        add(
            "juice",
            "TRAIN",
            "benign",
            "BENIGN",
            "POST",
            "/api/Users/",
            json.dumps(
                {
                    "email": email,
                    "password": "Fixture-only!7X",
                    "passwordRepeat": "Fixture-only!7X",
                    "securityQuestion": {"id": 1, "question": "Your eldest siblings middle name?"},
                    "securityAnswer": text,
                }
            ),
            "created_user",
            email,
        )
    for word in [
        "zzn7missingitem",
        "apple juice",
        "banana juice",
        "')) OR 1=1--",
        "')) OR 'a'='a'--",
        "')) OR TRUE--",
    ]:
        attack = word.startswith("'))")
        add(
            "juice",
            "PROSPECTIVE_EVALUATION",
            "sqli" if attack else "benign",
            "ATTACK_ATTEMPT" if attack else "BENIGN",
            "GET",
            "/rest/products/search?" + urlencode({"q": word}),
            "",
            "search_injection" if attack else "catalog_search",
            word,
        )
    return sorted(
        result,
        key=lambda c: (
            c["environment"],
            {"TRAIN": 0, "CALIBRATION": 1, "DEVELOPMENT": 2, "PROSPECTIVE_EVALUATION": 3}[
                c["role"]
            ],
        ),
    )


def prepare(root, environment="both"):
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    plan = {
        "schema_version": "research-cohort-1",
        "run_id": RUN,
        "source_sha256": file_sha256(__file__),
        "helper_sha256": {
            n: file_sha256(Path(__file__).with_name(n + ".py"))
            for n in ["p0-dvwa-capture", "juice-gt-factory", "p0-thermal-run"]
        },
        "cases": [c for c in cases() if environment == "both" or c["environment"] == environment],
        "purpose": "Internal Oracle research; not independent human review or production acceptance",
        "roles_locked_before_capture": True,
        "request_model": "Request-v2 full recorded URI/headers/body research inputs; live body observability not changed",
        "GLU207": "NOT_APPLICABLE_NO_STUDENT_207_CONTRACT",
        "maximum_cohort_requests": 100,
        "independent_review": "PENDING",
        "formal_admission": False,
        "outcome_policy": "Intent/receipt separate from success, failed attempt requires a specific negative Oracle; reflection alone never verified XSS execution",
        "evaluation_protocol": {
            "primary_task": "Attempt detection for meaningful vulnerable surfaces; failed/unknown outcomes remain separate",
            "recall_targets": {
                "sqli": 0.8,
                "xss": 0.8,
                "cmd_injection": 0.8,
                "path_traversal": 0.8,
            },
            "FPR_target": 0.01,
            "confidence": "Exact95% binomial descriptive plus workflow grouping; insufficient samples => INCONCLUSIVE",
            "model_selection": "Frozen threshold vs calibration-only selected only on eligible benign CALIBRATION at1% empirical budget; no prospective threshold fitting",
            "training": "At most one request representation challenger; no launch unless label/role/group/view/privacy/resume gates pass",
            "calibration_support": "Only Oracle-confirmed unique eligible benign groups; no count padding",
            "prospective_limit": "New collection does not establish independence from exposed older templates; overlap is audited before scoring evaluation",
        },
    }
    assert len(plan["cases"]) <= 100
    plan["plan_sha256"] = digest(plan)
    atomic_json(root / "plan.json", plan)


def run(root):
    os.umask(0o077)
    plan = json.loads((root / "plan.json").read_text())
    assert plan["plan_sha256"] == digest(
        {k: v for k, v in plan.items() if k != "plan_sha256"}
    ) and plan["source_sha256"] == file_sha256(__file__)
    assert all(
        file_sha256(Path(__file__).with_name(n + ".py")) == h
        for n, h in plan["helper_sha256"].items()
    )
    assert not (root / "capture.json").exists()
    if owned():
        raise RuntimeError(
            "A labeled lab already exists; verify ownership/cleanup before a new run"
        )
    d = module("p0-dvwa-capture")
    d.PORT = PORT
    d.PROXY_PORT = PROXY
    d.RUN_ID = RUN
    d.APP = RUN + "-dvwa"
    d.DB = RUN + "-db"
    d.NET = RUN + "-net"
    original_session = d.Session

    class PortBoundSession(original_session):
        def call(self, method, path, body="", extra=None, port=PORT):
            return super().call(method, path, body, extra, port)

    d.Session = PortBoundSession
    j = module("juice-gt-factory")
    j.APP_PORT = PORT
    (root / "heartbeat").touch()
    stop = threading.Event()

    def beat():
        while not stop.wait(0.2):
            (root / "heartbeat").touch()

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    unit = "idps-" + RUN + "-" + root.name + "-watchdog.service"
    cmd = [
        "systemd-run",
        "--user",
        "--quiet",
        "--unit",
        unit,
        "--service-type=exec",
        "-p",
        "RuntimeMaxSec=900",
        "-p",
        "CPUQuota=10%",
        "-p",
        "MemoryMax=128M",
        "-p",
        "MemorySwapMax=0",
        "--setenv",
        "PATH=" + os.environ["PATH"],
        sys.executable,
        str(Path(__file__).resolve()),
        "watchdog",
        "--output",
        str(root),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    end = time.monotonic() + 10
    while not (root / "watchdog-ready").exists() and time.monotonic() < end:
        time.sleep(0.1)
    if not (root / "watchdog-ready").exists() or (root / "lab-watchdog-result.json").exists():
        stop.set()
        raise RuntimeError("Independent lab watchdog did not become ready")
    observations = []
    setup_count = 0
    network_created = False
    images = {}
    owned_names = []
    try:
        for image in [d.APP_IMAGE, d.DB_IMAGE, JUICE]:
            info = json.loads(pm("image", "inspect", image))[0]
            images[image] = {"id": info["Id"], "digests": info["RepoDigests"]}
        pm("network", "create", "--internal", "--label", LABEL, d.NET)
        network_created = True
        for env in [
            e for e in ["dvwa", "juice"] if any(c["environment"] == e for c in plan["cases"])
        ]:
            if env == "dvwa":
                pm(
                    "run",
                    "-d",
                    "--name",
                    d.DB,
                    "--label",
                    LABEL,
                    "--network",
                    d.NET,
                    "--network-alias",
                    "db",
                    "--cpus=.5",
                    "--memory=1g",
                    "--memory-swap=1g",
                    "--pids-limit=128",
                    "--security-opt=no-new-privileges",
                    "-e",
                    "MYSQL_ROOT_PASSWORD=dvwa",
                    "-e",
                    "MYSQL_DATABASE=dvwa",
                    "-e",
                    "MYSQL_USER=dvwa",
                    "-e",
                    "MYSQL_PASSWORD=p@ssw0rd",
                    d.DB_IMAGE,
                )
                owned_names.append(d.DB)
                name = d.APP
                image = d.APP_IMAGE
                port = "80"
                extra = ["-e", "DB_SERVER=db"]
            else:
                name = RUN + "-juice"
                image = JUICE
                port = "3000"
                extra = []
            pm(
                "run",
                "-d",
                "--name",
                name,
                "--label",
                LABEL,
                "--network",
                d.NET,
                "--cpus=.5",
                "--memory=2g" if env == "juice" else "--memory=1g",
                "--memory-swap=2g" if env == "juice" else "--memory-swap=1g",
                "--pids-limit=256",
                "--security-opt=no-new-privileges",
                "-p",
                f"127.0.0.1:{PORT}:{port}",
                *extra,
                image,
            )
            owned_names.append(name)
            info = json.loads(pm("inspect", name))[0]
            net = json.loads(pm("network", "inspect", d.NET))[0]
            assert net["internal"] and info["NetworkSettings"]["Ports"][port + "/tcp"] == [
                {"HostIp": "127.0.0.1", "HostPort": str(PORT)}
            ]
            atomic_json(
                root / (env + "-identity.json"),
                {
                    "container_id": info["Id"],
                    "image_id": info["Image"],
                    "network_internal": True,
                    "port": PORT,
                    "labels": info["Config"]["Labels"],
                    "cgroup_parent_containment": "NOT_CLAIMED; per-container CPU/RAM limits and independent named-label watchdog",
                },
            )
            if env == "dvwa":
                session = d.Session(root / "dvwa-setup")
                d.initialize(session)
                setup_count += session.setup_requests
                pm("exec", name, "sh", "-c", "printf %s '" + d.CANARY + "' > " + d.CANARY_PATH)
                rows = pm(
                    "exec",
                    d.DB,
                    "mariadb",
                    "-udvwa",
                    "-pp@ssw0rd",
                    "-N",
                    "dvwa",
                    "-e",
                    "SELECT user_id,first_name,last_name FROM users ORDER BY user_id",
                )
                users = {f[0]: f[1:] for f in [line.split("\t") for line in rows.splitlines()]}
                for source in d.SOURCES + [
                    "vulnerabilities/xss_s/source/low.php",
                    "vulnerabilities/sqli_blind/source/low.php",
                ]:
                    target = root / "application-source" / env / source.replace("/", "__")
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    target.write_text(pm("exec", name, "cat", "/var/www/html/" + source))
            else:
                for _ in range(100):
                    try:
                        status, _, body = d.low_http(PORT, "GET", "/api/Products/")
                        catalog = json.loads(body)["data"]
                        if status == 200:
                            break
                    except (OSError, ValueError, KeyError):
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Juice startup failed")
                initial = j._challenge_snapshot()
                atomic_json(root / "juice-challenge-before.json", initial)
                atomic_json(root / "juice-catalog.json", catalog)
                session = None
            group = root / env
            group.mkdir(mode=0o700)
            d.Gateway.output = group / "receipts"
            d.Gateway.output.mkdir(mode=0o700)
            d.Gateway.receipts = {}
            d.Gateway.allowed_ids = {
                c["request_id"] for c in plan["cases"] if c["environment"] == env
            }
            server = d.ThreadingHTTPServer(("127.0.0.1", PROXY), d.Gateway)
            relay = threading.Thread(target=server.serve_forever, daemon=True)
            relay.start()
            try:
                role_sessions = {}
                for case in [c for c in plan["cases"] if c["environment"] == env]:
                    headers = {
                        "X-Request-Id": case["request_id"],
                        "User-Agent": "Mozilla/5.0 LabResearch",
                        "Accept": "application/json" if env == "juice" else "text/html",
                        "Content-Type": "application/json"
                        if env == "juice"
                        else "application/x-www-form-urlencoded",
                    }
                    if env == "dvwa":
                        if case["role"] not in role_sessions:
                            # Separate PHP session per role; share only predeclared clean fixture DB.
                            ss = d.Session(root / ("session-" + case["role"]))
                            _, _, page, _ = ss.call("GET", "/login.php")
                            token = re.search(
                                rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page
                            )
                            assert token
                            status, _, _, _ = ss.call(
                                "POST",
                                "/login.php",
                                urlencode(
                                    {
                                        "username": "admin",
                                        "password": "password",
                                        "Login": "Login",
                                        "user_token": token[1].decode(),
                                    }
                                ),
                            )
                            assert status == 302
                            ss.cookies["security"] = "low"
                            role_sessions[case["role"]] = ss
                            setup_count += ss.setup_requests
                        headers["Cookie"] = "; ".join(
                            f"{k}={v}" for k, v in role_sessions[case["role"]].cookies.items()
                        )
                    start = time.time()
                    status, returned, response = d.low_http(
                        PROXY, case["method"], case["path"], case["body"].encode(), headers
                    )
                    receipt = d.Gateway.receipts[case["request_id"]]
                    assert (
                        receipt["response_sha256"] == hashlib.sha256(response).hexdigest()
                        and receipt["request_body_sha256"]
                        == hashlib.sha256(case["body"].encode()).hexdigest()
                    )
                    rule = case["oracle"]
                    semantic = False
                    outcome = "UNKNOWN"
                    detail = {}
                    if env == "dvwa":
                        if rule in ["stored_literal", "unsafe_stored_reflection"]:
                            semantic = case["expected"] in response.decode(errors="replace")
                            detail = {
                                "stored_text_reflected": semantic,
                                "browser_execution_tested": False,
                            }
                            # Verify guestbook persistence independently from reflected textarea/input.
                            marker = case["expected"].replace("'", "''")
                            found = pm(
                                "exec",
                                d.DB,
                                "mariadb",
                                "-udvwa",
                                "-pp@ssw0rd",
                                "-N",
                                "dvwa",
                                "-e",
                                "SELECT COUNT(*) FROM guestbook WHERE comment='" + marker + "'",
                            )
                            detail["guestbook_exact_row_count"] = int(found)
                            semantic = semantic and int(found) >= 1
                            if rule == "unsafe_stored_reflection":
                                outcome = "UNSAFE_REFLECTION" if semantic else "UNKNOWN"
                        elif rule in ["blind_identity", "blind_injection"]:
                            text = response.decode(errors="replace")
                            exists = "User ID exists in the database." in text
                            missing = "User ID is MISSING from the database." in text
                            semantic = exists if case["expected"] else missing
                            detail = {
                                "exists_message": exists,
                                "missing_message": missing,
                                "fixture_user_count": len(users),
                            }
                            if rule == "blind_injection" and semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                        else:
                            semantic, detail = d.oracle(case, response, users)
                            if case["intent"] == "ATTACK_ATTEMPT" and semantic:
                                outcome = (
                                    "UNSAFE_REFLECTION"
                                    if case["family"] == "xss"
                                    else "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                                )
                    else:
                        try:
                            parsed = json.loads(response)
                        except ValueError:
                            parsed = None
                        data = parsed.get("data") if isinstance(parsed, dict) else None
                        if rule == "catalog_identity":
                            semantic = (
                                isinstance(data, dict)
                                and data.get("id") == case["expected"]
                                and any(
                                    x["id"] == data["id"] and x["name"] == data["name"]
                                    for x in catalog
                                )
                            )
                        elif rule == "catalog_search":
                            expected = [
                                x["id"]
                                for x in catalog
                                if case["expected"].lower()
                                in (str(x["name"]) + " " + str(x.get("description", ""))).lower()
                            ]
                            semantic = (
                                isinstance(data, list)
                                and all(
                                    isinstance(x, dict)
                                    and x.get("id") in {y["id"] for y in catalog}
                                    for x in data
                                )
                                and (bool(data) if expected else not data)
                            )
                        elif rule == "invalid_login_denied":
                            semantic = status == 401 and response == b"Invalid email or password."
                        elif rule == "created_user":
                            semantic = (
                                isinstance(data, dict)
                                and isinstance(data.get("id"), int)
                                and data.get("email") == case["expected"]
                            )
                            detail = {
                                "created_fixture_user_id": data.get("id")
                                if isinstance(data, dict)
                                else None
                            }
                        elif rule == "admin_auth_bypass":
                            auth = (
                                parsed.get("authentication") if isinstance(parsed, dict) else None
                            )
                            after = j._challenge_snapshot()
                            atomic_json(root / "juice-challenge-after.json", after)
                            semantic = bool(
                                isinstance(auth, dict)
                                and auth.get("umail") == "admin@juice-sh.op"
                                and auth.get("token")
                                and not initial["solved"]
                                and after["solved"]
                                and after["id"] == initial["id"]
                            )
                            if semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                            detail = {
                                "initial_challenge_solved": initial["solved"],
                                "after_challenge_solved": after["solved"],
                            }
                        elif rule == "search_injection":
                            semantic = (
                                isinstance(data, list)
                                and all(isinstance(x, dict) for x in data)
                                and {x["id"] for x in catalog} <= {x.get("id") for x in data}
                                and len(catalog) > 10
                            )
                            if semantic:
                                outcome = "VERIFIED_EXPLOIT_SUCCESS_INTERNAL_ORACLE"
                            detail = {
                                "returned_distinct_ids": len({x.get("id") for x in data})
                                if isinstance(data, list)
                                else None,
                                "fixture_catalog_size": len(catalog),
                            }
                    intent = (
                        case["intent"]
                        if case["intent"] == "ATTACK_ATTEMPT" or semantic
                        else "UNKNOWN"
                    )
                    observations.append(
                        {
                            **case,
                            "intent": intent,
                            "semantic_oracle_matched": semantic,
                            "outcome": outcome,
                            "oracle_detail": detail,
                            "response_status": status,
                            "receipt_matches": True,
                            "receipt_path": str(
                                (
                                    group / "receipts" / case["request_id"] / "receipt.json"
                                ).relative_to(root)
                            ),
                            "response_sha256": hashlib.sha256(response).hexdigest(),
                            "session_group": hashlib.sha256(
                                (
                                    headers.get("Cookie", "")
                                    or "stateless-" + env + "-" + case["role"]
                                ).encode()
                            ).hexdigest(),
                            "session_group_basis": "COOKIE_DIGEST"
                            if headers.get("Cookie")
                            else "STATELESS_ROLE_COHORT_CONSERVATIVE",
                            "review_status": "REVIEW_PENDING",
                            "independent_human_verified": False,
                            "started_at": start,
                            "ended_at": time.time(),
                            "transaction_provenance": "OWNED_PROXY_RECEIPT_NOT_APPLICATION_REQUEST_ID_LOG",
                        }
                    )
                    atomic_json(root / "observations-progress.json", {"observations": observations})
                    atomic_json(
                        root / "progress.json",
                        {"completed": len(observations), "planned": len(plan["cases"])},
                    )
            finally:
                server.shutdown()
                server.server_close()
                relay.join(timeout=3)
            pm("logs", name, check=False)  # Never print container/session logs.
            remove_finished_container(name, root / (env + "-cleanup-diagnostic.json"))
            owned_names.remove(name)
            if env == "dvwa":
                pm("rm", "-f", d.DB, check=False)
                owned_names.remove(d.DB)
        report = {
            "schema_version": "research-capture-1",
            "plan_sha256": plan["plan_sha256"],
            "script_sha256": file_sha256(__file__),
            "requests_sent": len(observations),
            "setup_requests_excluded": setup_count,
            "images": images,
            "observations": observations,
            "intent_counts": dict(Counter(o["intent"] for o in observations)),
            "outcome_counts": dict(Counter(o["outcome"] for o in observations)),
            "independent_review": "PENDING",
            "independently_verified_labels": 0,
            "models_loaded_during_capture": False,
            "GLU207_eligible": 0,
            "formal_admitted": 0,
            "raw_evidence_distribution": "LOCAL_ONLY fixtures/session material; never public",
        }
        atomic_json(root / "capture.json", report)
    finally:
        for name in reversed(owned_names):
            pm("rm", "-f", name, check=False)
        if network_created:
            pm("network", "rm", d.NET, check=False)
        stop.set()
        thread.join(timeout=2)
        (root / "watchdog-done").touch()
        for _ in range(10):
            if (root / "lab-watchdog-result.json").exists():
                break
            time.sleep(0.1)
        subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
        atomic_json(
            root / "cleanup.json",
            {"owned_containers_remaining": len(owned()), "watchdog_unit": unit, "stopped": True},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "run", "watchdog"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--environment", choices=["both", "dvwa", "juice"], default="both")
    a = p.parse_args()
    a.output = a.output.resolve()
    if a.command == "prepare":
        prepare(a.output, a.environment)
    elif a.command == "run":
        run(a.output)
    else:
        watchdog(a.output)

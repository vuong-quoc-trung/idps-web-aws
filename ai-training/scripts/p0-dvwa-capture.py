#!/usr/bin/env python3
"""Prospective, request-bound DVWA P0 lab; no model is loaded during capture.

Uses the existing project's immutable serialization and evidence conventions.
Intent is collector-controlled, Oracle evidence is application/container-side,
and independent semantic review explicitly remains pending.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import random
import re
import subprocess
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import psutil

from idps_ai.common import AI_ROOT, atomic_json, digest, file_sha256

PORT, PROXY_PORT = 14280, 14281
RUN_ID = "p0-dvwa-20261105-1520"
APP, DB, NET = RUN_ID + "-app", RUN_ID + "-db", RUN_ID + "-net"
APP_IMAGE = (
    "ghcr.io/digininja/dvwa@sha256:167b609f577e6d3161bbbfc1189f72549e9ce62cf32eb200050492c3dad3395c"
)
DB_IMAGE = "public.ecr.aws/docker/library/mariadb@sha256:6c65a843396dc6c78dd0da19eccaa0a91d25d9d26a4c2afcb75010ac3f59f5ea"
CANARY_PATH = "/tmp/ai-idps-p0-canary.txt"
CANARY = "AI_IDPS_P0_DVWA_CANARY_20261105_1520"
SOURCES = [
    "vulnerabilities/sqli/source/low.php",
    "vulnerabilities/exec/source/low.php",
    "vulnerabilities/xss_r/source/low.php",
    "vulnerabilities/fi/source/low.php",
    "vulnerabilities/fi/index.php",
    "vulnerabilities/fi/file1.php",
    "vulnerabilities/fi/file2.php",
    "vulnerabilities/fi/file3.php",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def podman(*args, timeout=40):
    return subprocess.check_output(
        ["podman", *args], text=True, stderr=subprocess.PIPE, timeout=timeout
    ).strip()


def low_http(port, method, path, body=b"", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=12)
    try:
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise RuntimeError("Lab response size exceeded")
        return response.status, list(response.getheaders()), data
    finally:
        connection.close()


class Session:
    def __init__(self, output):
        self.cookies = {}
        self.setup_requests = 0
        self.output = output
        self.output.mkdir(mode=0o700)

    def call(self, method, path, body="", extra=None, port=PORT):
        headers = {
            "User-Agent": "Mozilla/5.0 AI-IDPS-P0-Lab",
            "Accept": "text/html",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
            **(extra or {}),
        }
        status, returned, data = low_http(port, method, path, body.encode(), headers)
        for name, value in returned:
            if name.lower() == "set-cookie":
                cookie = SimpleCookie()
                cookie.load(value)
                self.cookies.update({k: v.value for k, v in cookie.items()})
        if port == PORT:
            self.setup_requests += 1
            (self.output / f"{self.setup_requests:03}-response.bin").write_bytes(data)
            atomic_json(
                self.output / f"{self.setup_requests:03}.json",
                {
                    "method": method,
                    "path": path,
                    "status": status,
                    "response_sha256": hashlib.sha256(data).hexdigest(),
                    "response_headers": returned,
                },
            )
        return status, returned, data, headers


def initialize(session):
    for _ in range(50):
        try:
            status, _, _, _ = session.call("GET", "/setup.php")
            if status == 200:
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("DVWA did not become ready")
    for _ in range(30):
        try:
            podman(
                "exec",
                DB,
                "mariadb",
                "-h127.0.0.1",
                "-udvwa",
                "-pp@ssw0rd",
                "-N",
                "dvwa",
                "-e",
                "SELECT 1",
            )
            break
        except subprocess.CalledProcessError:
            time.sleep(1)
    else:
        raise RuntimeError("Disposable lab database did not become ready")
    _, _, page, _ = session.call("GET", "/setup.php")
    token = re.search(rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page)
    if not token:
        raise RuntimeError("DVWA setup CSRF token absent")
    session.call(
        "POST",
        "/setup.php",
        urlencode({"create_db": "Create / Reset Database", "user_token": token[1].decode()}),
    )
    _, _, page, _ = session.call("GET", "/login.php")
    token = re.search(rb"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)", page)
    if not token:
        raise RuntimeError("DVWA login CSRF token absent")
    status, _, _, _ = session.call(
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
    if status != 302:
        raise RuntimeError("DVWA isolated test login failed")
    session.cookies["security"] = "low"
    status, _, page, _ = session.call("GET", "/vulnerabilities/sqli/?id=1&Submit=Submit")
    if status != 200 or b"First name: admin" not in page:
        raise RuntimeError("DVWA authenticated low-security preflight failed")


def make_cases():
    cases = []

    def add(family, intent, method, path, value, oracle, expected, field):
        index = len(cases)
        values = {field: value, "Submit": "Submit"}
        target = path + ("?" + urlencode(values) if method == "GET" else "")
        body = urlencode(values) if method == "POST" else ""
        cases.append(
            {
                "case_id": f"dvwa-{index:03}",
                "request_id": digest([RUN_ID, index])[:32],
                "family": family,
                "planned_intent": intent,
                "method": method,
                "path": target,
                "body": body,
                "oracle": oracle,
                "expected": expected,
                "campaign_id": "dvwa-" + family,
                "role": "prospective_evaluation",
            }
        )

    for value in [str(i) for i in range(15)] + ["99", "100", "101", "999", "9999"]:
        add(
            "sqli",
            "benign",
            "GET",
            "/vulnerabilities/sqli/",
            value,
            "user_identity_rows",
            int(value),
            "id",
        )
    sql = [
        "1' OR '1'='1",
        "0' OR 1=1#",
        "1' OR 1=1-- -",
        "0' OR 'a'='a' #",
        "0' UNION SELECT 'AIP0_SQL_04','canary'-- -",
        "0' UNION ALL SELECT 'AIP0_SQL_05','canary'#",
        "0' UnIoN SeLeCt 'AIP0_SQL_06','canary'-- -",
        "0' UNION/**/SELECT 'AIP0_SQL_07','canary'#",
        "0' OR user_id>0#",
        "0' OR TRUE#",
        "0' OR 2>1#",
        "0' OR 'x' LIKE 'x'#",
    ]
    for i, value in enumerate(sql):
        add(
            "sqli",
            "attack",
            "GET",
            "/vulnerabilities/sqli/",
            value,
            "injected_sql_rows",
            f"AIP0_SQL_{i:02}" if 4 <= i <= 7 else None,
            "id",
        )
    names = [
        "Alice",
        "Bob",
        "O'Connor",
        "D'Angelo",
        "Nguyen Van An",
        "Trần Minh",
        "C++ programming",
        "rock & roll",
        "2 < 3",
        "a > b",
        "hello@example.invalid",
        "union select from where",
        "SELECT name FROM products",
        "script tutorial",
        "JavaScript basics",
        "alert fatigue",
        "document window",
        "onload example",
        "price=10; count=2",
        "whoami",
        "cat pictures",
        "bash tutorial",
        "curl examples",
        "HTTP headers",
        "../../ in documentation",
        "file inclusion lesson",
        "10% discount",
        "a+b=c",
        "{name: Alice}",
        "[1,2,3]",
        "line one\nline two",
        "résumé",
        "Xin chào",
        "x && y",
        "x || y",
        'quote "example"',
    ]
    for name in names:
        add(
            "xss",
            "benign",
            "GET",
            "/vulnerabilities/xss_r/",
            name,
            "literal_name_reflection",
            name,
            "name",
        )
    xss = [
        "<script>void(101)</script>",
        "<ScRiPt>void(102)</ScRiPt>",
        "<img src=x onerror=void(103)>",
        "<svg onload=void(104)>",
        "<iframe onload=void(105)></iframe>",
        "<details open ontoggle=void(106)>x</details>",
        "<input autofocus onfocus=void(107)>",
        "<body onload=void(108)>",
        "<script>/*lab*/void(109)</script>",
        "<svg/onload=void(110)>",
        "<img src=x\nonerror=void(111)>",
        "<script>void('AIP0_XSS_112')</script>",
    ]
    for value in xss:
        add(
            "xss",
            "attack",
            "GET",
            "/vulnerabilities/xss_r/",
            value,
            "unsafe_reflection_only_no_browser_execution",
            value,
            "name",
        )
    for value in ["127.0.0.1", "127.0.0.2", "127.0.0.3", "127.0.0.4"]:
        add(
            "cmd_injection",
            "benign",
            "POST",
            "/vulnerabilities/exec/",
            value,
            "loopback_ping_result",
            value,
            "ip",
        )
    for i, separator in enumerate(
        [";", "&&", "|", "\n", "; ", "&& ", "| ", "\n ", ";\t", "&&\t", "|\t", "\n\t"]
    ):
        marker = f"AIP0_CMD_{i:02}_CANARY"
        value = "127.0.0.1 -c 1" + separator + "printf '" + marker + "'"
        add(
            "cmd_injection",
            "attack",
            "POST",
            "/vulnerabilities/exec/",
            value,
            "command_stdout_canary",
            marker,
            "ip",
        )
    for value in ["file1.php", "file2.php", "file3.php"]:
        add(
            "path_traversal",
            "benign",
            "GET",
            "/vulnerabilities/fi/",
            value,
            "included_public_page",
            value,
            "page",
        )
    for value in [
        CANARY_PATH,
        "../../../../../../tmp/ai-idps-p0-canary.txt",
        "../" * 8 + "tmp/ai-idps-p0-canary.txt",
        "/tmp/./ai-idps-p0-canary.txt",
        "/tmp//ai-idps-p0-canary.txt",
        "../../../../../../tmp/./ai-idps-p0-canary.txt",
        "php://filter/convert.base64-encode/resource=" + CANARY_PATH,
        "php://filter/read=convert.base64-encode/resource=" + CANARY_PATH,
        "php://filter/resource=" + CANARY_PATH,
        "/tmp/../tmp/ai-idps-p0-canary.txt",
        "../" * 10 + "tmp/ai-idps-p0-canary.txt",
        "../../../../../../tmp//ai-idps-p0-canary.txt",
    ]:
        add(
            "path_traversal",
            "attack",
            "GET",
            "/vulnerabilities/fi/",
            value,
            "included_private_canary",
            CANARY,
            "page",
        )
    random.Random(20261105).shuffle(cases)
    return cases


class Gateway(BaseHTTPRequestHandler):
    receipts = {}
    output = None
    allowed_ids = set()

    def relay(self):
        rid = self.headers.get("X-Request-Id")
        if rid not in self.allowed_ids or rid in self.receipts:
            self.send_error(400)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        headers = dict(self.headers.items())
        status, returned, data = low_http(PORT, self.command, self.path, body, headers)
        receipt = {
            "request_id": rid,
            "method": self.command,
            "path": self.path,
            "request_body_sha256": hashlib.sha256(body).hexdigest(),
            "request_headers_sha256": digest(headers),
            "status": status,
            "response_sha256": hashlib.sha256(data).hexdigest(),
            "response_headers_sha256": digest(returned),
            "captured_at": now(),
        }
        directory = self.output / rid
        directory.mkdir(mode=0o700)
        (directory / "request-body.bin").write_bytes(body)
        (directory / "response-body.bin").write_bytes(data)
        atomic_json(directory / "request-headers.json", headers)
        atomic_json(directory / "response-headers.json", returned)
        atomic_json(directory / "receipt.json", receipt)
        self.receipts[rid] = receipt
        self.send_response(status)
        for name, value in returned:
            if name.lower() in {"content-type", "set-cookie"}:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Request-Id", rid)
        self.end_headers()
        self.wfile.write(data)

    do_GET = relay
    do_POST = relay

    def log_message(self, *_):
        pass


def oracle(case, data, users):
    text = data.decode(errors="replace")
    # All tests inspect the response content region, never the reflected form
    # input value. An echoed attack payload alone is not an execution Oracle.
    region = re.search(r'<div class="vulnerable_code_area">(.*?)</div>', text, re.S)
    content = region[1] if region else ""
    pre = "\n".join(re.findall(r"<pre>(.*?)</pre>", content, re.S))
    row_names = re.findall(r"First name: ([^<]+)<br\s*/?>Surname: ([^<]+)", pre)
    rule, expected = case["oracle"], case["expected"]
    success, detail = False, {}
    if rule == "user_identity_rows":
        target = users.get(str(expected))
        success = bool(region) and (row_names == [tuple(target)] if target else not row_names)
        detail = {"returned_names": row_names, "expected_user_id": expected}
    elif rule == "injected_sql_rows":
        success = (
            any(a == expected for a, _ in row_names) if expected else len(row_names) == len(users)
        )
        detail = {"returned_names": row_names, "expected_injected_marker": expected}
    elif rule in {"literal_name_reflection", "unsafe_reflection_only_no_browser_execution"}:
        success = bool(region) and "Hello " + expected in pre
        detail = {"literal_response_reflection": success, "browser_execution_tested": False}
    elif rule == "loopback_ping_result":
        success = bool(region) and expected in pre and "packets transmitted" in pre
        detail = {"ping_output_observed": success}
    elif rule == "command_stdout_canary":
        success = bool(region) and expected in pre
        detail = {"stdout_marker_present": success}
    elif rule == "included_public_page":
        success = bool(region) and ("<h3>File " + expected[4] + "</h3>") in content
        detail = {"public_file_heading_observed": success}
    elif rule == "included_private_canary":
        # FI output can be outside the vulnerable_code_area wrapper.
        success = CANARY in text or base64.b64encode(CANARY.encode()).decode() in text
        detail = {"private_canary_observed": success}
    return success, detail


def capture(root):
    root = Path(root).resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    os.umask(0o077)
    resources, server, worker, packet_process = [], None, None, None
    session = Session(root / "setup-evidence")
    started = now()
    try:
        for name in [APP, DB]:
            if subprocess.run(["podman", "container", "exists", name]).returncode == 0:
                raise RuntimeError("P0 named container already exists")
        podman("network", "create", "--internal", NET)
        resources.append(("network", NET))
        podman(
            "run",
            "-d",
            "--name",
            DB,
            "--network",
            NET,
            "--network-alias",
            "db",
            "--cpus=2",
            "--memory=1g",
            "--memory-swap=1g",
            "--pids-limit=256",
            "--security-opt=no-new-privileges",
            "-e",
            "MYSQL_ROOT_PASSWORD=dvwa",
            "-e",
            "MYSQL_DATABASE=dvwa",
            "-e",
            "MYSQL_USER=dvwa",
            "-e",
            "MYSQL_PASSWORD=p@ssw0rd",
            DB_IMAGE,
        )
        resources.append(("container", DB))
        podman(
            "run",
            "-d",
            "--name",
            APP,
            "--network",
            NET,
            "--cpus=2",
            "--memory=1g",
            "--memory-swap=1g",
            "--pids-limit=256",
            "--security-opt=no-new-privileges",
            "-p",
            f"127.0.0.1:{PORT}:80",
            "-e",
            "DB_SERVER=db",
            APP_IMAGE,
        )
        resources.append(("container", APP))
        initialize(session)
        podman("exec", APP, "sh", "-c", "printf %s '" + CANARY + "' > " + CANARY_PATH)
        source_root = root / "application-source"
        source_root.mkdir(mode=0o700)
        for name in SOURCES:
            data = podman("exec", APP, "cat", "/var/www/html/" + name)
            (source_root / name.replace("/", "__")).write_text(data + "\n")
        rows = podman(
            "exec",
            DB,
            "mariadb",
            "-udvwa",
            "-pp@ssw0rd",
            "-N",
            "dvwa",
            "-e",
            "SELECT user_id,first_name,last_name FROM users ORDER BY user_id",
        )
        users = {
            fields[0]: fields[1:] for fields in (line.split("\t") for line in rows.splitlines())
        }
        if len(users) != 5:
            raise RuntimeError("Unexpected DVWA fixture users")
        app_info = json.loads(podman("inspect", APP))[0]
        net_info = json.loads(podman("network", "inspect", NET))[0]
        if not net_info["internal"] or app_info["NetworkSettings"]["Ports"]["80/tcp"] != [
            {"HostIp": "127.0.0.1", "HostPort": str(PORT)}
        ]:
            raise RuntimeError("P0 isolation verification failed")
        cases = make_cases()
        plan = {
            "format_version": 1,
            "run_id": RUN_ID,
            "created_at": now(),
            "capture_script_sha256": file_sha256(__file__),
            "seed": 20261105,
            "role": "prospective_evaluation_no_training_or_threshold_tuning",
            "cases": cases,
            "users_oracle": users,
            "canary": CANARY,
            "application_source_sha256": {p.name: file_sha256(p) for p in source_root.iterdir()},
            "app_image": json.loads(podman("image", "inspect", APP_IMAGE))[0]["RepoDigests"],
            "db_image": json.loads(podman("image", "inspect", DB_IMAGE))[0]["RepoDigests"],
            "container_ids": {APP: app_info["Id"], DB: json.loads(podman("inspect", DB))[0]["Id"]},
            "isolation": {"network_internal": True, "loopback_port": PORT},
            "independent_review": "PENDING_NOT_PERFORMED",
            "independent_reviewer": None,
            "label_rules": {
                "intent": "precommitted lab intent plus matching request/response receipt; collector-controlled",
                "benign": "precommitted permitted workflow AND matching application semantic Oracle",
                "attack": "precommitted exploit attempt AND matching receipt; success separately supported by Oracle",
                "unknown": "receipt mismatch or absent benign Oracle; never inferred from score/status alone",
            },
            "outcome_rules": {
                "sqli": "injected constant row or all five DB identities returned",
                "cmd_injection": "unique printf canary in command stdout region",
                "path_traversal": "private non-public container canary returned",
                "xss": "unsafe reflection only; browser execution remains UNKNOWN",
            },
            "frozen_baseline_manifest_sha256": file_sha256(
                AI_ROOT / "RESEARCH_MVP_V1_0_FROZEN.json"
            ),
        }
        plan["plan_sha256"] = digest(plan)
        atomic_json(root / "plan.json", plan)
        # Rootless namespace capture is optional. Failure is recorded and never
        # replaced with synthetic PCAP or purported Suricata results.
        packet_log = (root / "packet-capture.log").open("wb")
        pid = app_info["State"]["Pid"]
        packet_command = [
            "podman",
            "unshare",
            "nsenter",
            "--target",
            str(pid),
            "--net",
            "tcpdump",
            "-i",
            "any",
            "-U",
            "-s",
            "0",
            "-Z",
            "root",
            "-w",
            str(root / "traffic.pcap"),
            "tcp port 80",
        ]
        packet_process = subprocess.Popen(packet_command, stdout=packet_log, stderr=packet_log)
        time.sleep(1)
        packet_available = packet_process.poll() is None
        Gateway.output = root / "receipts"
        Gateway.output.mkdir(mode=0o700)
        Gateway.allowed_ids = {case["request_id"] for case in cases}
        Gateway.receipts = {}
        server = ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), Gateway)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        observations = []
        for case in cases:
            status, _, data, _ = session.call(
                case["method"],
                case["path"],
                case["body"],
                {"X-Request-Id": case["request_id"]},
                PROXY_PORT,
            )
            receipt = Gateway.receipts.get(case["request_id"])
            consistent = (
                bool(receipt)
                and receipt["method"] == case["method"]
                and receipt["path"] == case["path"]
                and receipt["request_body_sha256"]
                == hashlib.sha256(case["body"].encode()).hexdigest()
                and receipt["response_sha256"] == hashlib.sha256(data).hexdigest()
            )
            semantic, detail = oracle(case, data, users)
            intent = (
                case["planned_intent"]
                if consistent and (case["planned_intent"] == "attack" or semantic)
                else "unknown"
            )
            outcome = (
                "succeeded"
                if intent == "attack" and semantic and case["family"] != "xss"
                else "unknown"
            )
            observations.append(
                {
                    "case_id": case["case_id"],
                    "request_id": case["request_id"],
                    "family": case["family"],
                    "lab_intent": intent,
                    "receipt_matches": consistent,
                    "semantic_oracle_matched": semantic,
                    "oracle_detail": detail,
                    "exploit_outcome": outcome,
                    "review_status": "pending_independent_review",
                    "status": status,
                    "response_sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            atomic_json(
                root / "capture-progress.json",
                {"completed": len(observations), "total": len(cases)},
            )
        atomic_json(
            root / "capture-report.json",
            {
                "run_id": RUN_ID,
                "started_at": started,
                "finished_at": now(),
                "plan_sha256": plan["plan_sha256"],
                "plan_file_sha256": file_sha256(root / "plan.json"),
                "requests_sent": len(cases),
                "physical_unique_request_ids": len(Gateway.receipts),
                "setup_requests_excluded": session.setup_requests,
                "lab_intent_counts": dict(Counter(x["lab_intent"] for x in observations)),
                "independently_verified_labels": 0,
                "independent_review": "PENDING",
                "oracle_successes": dict(
                    Counter(
                        x["family"] for x in observations if x["exploit_outcome"] == "succeeded"
                    )
                ),
                "packet_capture_started": packet_available,
                "observations": observations,
                "formal_admitted": 0,
                "models_loaded_or_fitted_during_capture": False,
            },
        )
        for name in [APP, DB]:
            (root / (name + ".log")).write_text(podman("logs", name))
            atomic_json(root / (name + "-inspect.json"), json.loads(podman("inspect", name))[0])
    finally:
        if server:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
        if packet_process and packet_process.poll() is None:
            packet_process.send_signal(2)
            try:
                packet_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                packet_process.terminate()
                packet_process.wait(timeout=5)
        # Rootless namespace launchers may exit before tcpdump. Match the exact
        # private PCAP argument, never stop unrelated capture processes.
        owned_pcap = str(root / "traffic.pcap")
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                if process.info["name"] == "tcpdump" and owned_pcap in (
                    process.info["cmdline"] or []
                ):
                    process.send_signal(2)
                    try:
                        process.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        process.terminate()
            except psutil.Error:
                pass
        cleanup = []
        for kind, name in reversed(resources):
            command = (
                ["podman", "rm", "-f", name]
                if kind == "container"
                else ["podman", "network", "rm", name]
            )
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            cleanup.append(
                {
                    "kind": kind,
                    "name": name,
                    "returncode": result.returncode,
                    "stderr": result.stderr[-2000:],
                }
            )
        absent = all(
            subprocess.run(["podman", "container", "exists", name], capture_output=True).returncode
            != 0
            for kind, name in resources
            if kind == "container"
        )
        absent &= (
            subprocess.run(["podman", "network", "exists", NET], capture_output=True).returncode
            != 0
        )
        atomic_json(
            root / "cleanup.json",
            {"resources": cleanup, "all_removed": absent},
        )
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
    print(
        json.dumps(
            {"output": str(root), "capture_complete": (root / "capture-report.json").exists()}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args()
    if not re.fullmatch(r"p0-dvwa-[a-z0-9-]+", args.run_id):
        raise SystemExit("Invalid lab run ID")
    RUN_ID = args.run_id
    APP, DB, NET = RUN_ID + "-app", RUN_ID + "-db", RUN_ID + "-net"
    capture(args.output)

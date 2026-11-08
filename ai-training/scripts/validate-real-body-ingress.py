#!/usr/bin/env python3
"""Finite opt-in Nginx/application/privacy acceptance on a dedicated existing lab stack.

No training, no raw HTTP receipts, no modification of Web/Rules/frozen inference.
The stack must be separate from the normal demo. Default candidate is OFF.
"""

import argparse
import base64
import gzip
import hashlib
import http.cookiejar
import importlib.util
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from collections import Counter
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import numpy as np

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.features import body_syntax_v1 as syntax
from idps_ai.features.body_syntax_ingress_lab import Gate, LabIngress, TempMonitor
from idps_ai.features.body_syntax_transport import SyntaxWorker

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"
TEMP_NAMES = ("body", "proxy", "fastcgi", "scgi", "uwsgi", "self-test")


def nginx_config(output, runtime, ingress_path, frozen_socket):
    """Deterministic lab config; never inherit compiled-in system temp paths."""
    maps = (ROOT / "security-web/nginx/pbl4-proxy.conf").read_text().split("# Local services")[0]
    shadow_format = """log_format body_frozen escape=json '{"schema_version":"nginx-ai-1","request_id":"$request_id","timestamp":"$time_iso8601","method":"$request_method","url":"$request_uri","headers":{"User-Agent":"$http_user_agent","Accept":"$http_accept","Content-Type":"$http_content_type"}}';"""
    settings = f"""proxy_http_version 1.1;
proxy_request_buffering off; proxy_buffering off; proxy_max_temp_file_size 0;
client_body_buffer_size 8k; client_body_in_file_only off; client_max_body_size 1m;
client_body_temp_path {output / "body"}; proxy_temp_path {output / "proxy"};
fastcgi_temp_path {output / "fastcgi"}; scgi_temp_path {output / "scgi"};
uwsgi_temp_path {output / "uwsgi"};
proxy_set_header Host $host; proxy_set_header X-Request-Id $request_id;
proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header Connection close;
proxy_set_header X-Body-Original-Transfer $http_transfer_encoding;
proxy_hide_header X-Request-Id; add_header X-Request-Id $request_id always;
proxy_connect_timeout 3s; proxy_read_timeout 15s; proxy_send_timeout 15s;
"""
    pass_to = f"proxy_pass http://unix:{ingress_path}:;"
    return f"""worker_processes 1; daemon off; master_process off;
pid {output / "nginx.pid"}; error_log {output / "nginx-error.log"} error;
events {{ worker_connections 64; }}
http {{ {maps} {shadow_format} {settings}
server {{ listen 127.0.0.1:18890;
access_log {runtime / "nginx-access.jsonl"} idps_json;
location /api/ {{ access_log {runtime / "nginx-access.jsonl"} idps_json; access_log syslog:server=unix:{frozen_socket},tag=ai_shadow,nohostname body_frozen; {pass_to} }}
location / {{ {pass_to} }} }} }}"""


def safe_nginx_diagnostic(value):
    # Config generation uses fixed directives/paths, no request or environment
    # values. Still suppress credential-bearing lines if a future edit adds one.
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
    lines = []
    for line in text[:65536].splitlines():
        if re.search(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie|session)\b"
            r"|[a-z]+://[^/\s]*@",
            line,
        ):
            line = "[REDACTED credential-bearing diagnostic line]"
        lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def nginx_preflight(output, *, binary=NGINX):
    """Run only nginx -t, saving bounded safe diagnostics before raising on FAIL."""
    output = output.resolve()
    config = output / "nginx.conf"
    run_id = f"nginx-preflight-{time.time_ns()}"
    diagnostic = output / run_id
    diagnostic.mkdir(mode=0o700)
    command = [str(binary), "-p", str(output), "-c", str(config), "-t"]
    exit_code, failure = None, None
    try:
        result = subprocess.run(command, cwd=output, capture_output=True, timeout=10)
        exit_code = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout, exc.stderr
        failure = "NGINX_PREFLIGHT_TIMEOUT"
    except OSError as exc:
        stdout, stderr = b"", type(exc).__name__.encode()
        failure = "NGINX_BINARY_EXECUTION_FAILED"
    stdout, stderr = safe_nginx_diagnostic(stdout), safe_nginx_diagnostic(stderr)
    if exit_code != 0 and failure is None:
        failure = (
            "COMPILED_SYSTEM_TEMP_PATH_UNAVAILABLE"
            if re.search(r'mkdir\(\) "/var/lib/nginx/(fastcgi|scgi|uwsgi)" failed', stderr)
            else "NGINX_CONFIGURATION_REJECTED_SEE_STDERR"
        )
    (diagnostic / "stdout.txt").write_text(stdout)
    (diagnostic / "stderr.txt").write_text(stderr)
    report = {
        "run_id": run_id,
        "status": "PASS" if exit_code == 0 else "FAIL",
        "command": command,
        "cwd": str(output),
        "exit_code": exit_code,
        "config": str(config),
        "config_sha256": file_sha256(config),
        "binary_sha256": file_sha256(binary) if binary.is_file() else None,
        "root_cause": failure,
        "stdout": str(diagnostic / "stdout.txt"),
        "stderr": str(diagnostic / "stderr.txt"),
        "diagnostic_directory": str(diagnostic),
        "streams_limit_characters": 65536,
        "credential_lines_redacted": True,
        "http_traffic_started": False,
    }
    atomic_json(diagnostic / "diagnostic.json", report)
    if exit_code != 0:
        raise RuntimeError(f"Nginx preflight FAIL ({failure}); diagnostics: {diagnostic}")
    return report


def preflight_only(output):
    """No stack, workers, sockets, credentials, containers or HTTP requests."""
    os.umask(0o077)
    output = output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name in TEMP_NAMES:
        (output / name).mkdir(mode=0o700)
    Gate(output / "gate.json")
    # Short non-listening paths also keep the syslog sockaddr within AF_UNIX's limit.
    with tempfile.TemporaryDirectory(prefix="idps-nginx-check-") as short:
        config = nginx_config(
            output, output, Path(short) / "body.sock", Path(short) / "frozen.sock"
        )
        (output / "nginx.conf").write_text(config)
        return nginx_preflight(output)


def load(p):
    return json.loads(p.read_text())


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def protected_snapshot(previous):
    protected = dict(previous["protected_sha256"])
    updates = {}
    for path, expected in protected.items():
        actual = file_sha256(ROOT / path)
        if actual != expected:
            # The reviewed upstream change only adds startup status/socket-mode.
            # Admit this exact source revision, never a changed model/artifact.
            assert path == "scripts/ai-shadow-worker.py", f"Protected artifact changed: {path}"
            for revision, sha in [("391d34c", expected), ("c71f002", actual)]:
                blob = subprocess.run(
                    ["git", "show", f"{revision}:{path}"],
                    cwd=ROOT,
                    capture_output=True,
                    check=True,
                    timeout=5,
                ).stdout
                assert hashlib.sha256(blob).hexdigest() == sha, "Unreviewed worker source"
            updates[path] = {"historical_sha256": expected, "reviewed_sha256": actual}
            protected[path] = actual
    protected["ai-training/src/idps_ai/features/body_syntax_v1.py"] = file_sha256(
        ROOT / "ai-training/src/idps_ai/features/body_syntax_v1.py"
    )
    return protected, updates


def wait(predicate, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise RuntimeError("Bounded lab acceptance timeout; inspect private metadata")


def check_application_status(output, label, candidate_on, actual, expected):
    if expected is not None and actual != expected:
        atomic_json(
            output / "application-failure.json",
            {
                "case": label,
                "candidate": "ON" if candidate_on else "OFF",
                "actual_status": actual,
                "expected_status": expected,
                "raw_response_saved": False,
            },
        )
        raise RuntimeError(
            f"Application baseline mismatch: {label}, actual={actual}, expected={expected}; "
            f"diagnostics: {output / 'application-failure.json'}"
        )


def audit_status_differences(request_rows, audit_rows):
    audit = {r["request_id"]: r for r in audit_rows}
    assert len({r["request_id"] for r in request_rows}) == len(request_rows)
    assert all(r["request_id"] in audit for r in request_rows), "Missing Student audit correlation"
    return [
        {
            "case": r["label"],
            "wire_status": r["status"],
            "audit_status": audit[r["request_id"]]["status_code"],
        }
        for r in request_rows
        if r["status"] != audit[r["request_id"]]["status_code"]
    ]


class Client:
    def __init__(self, port):
        self.port = port
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def call(self, method, path, body=None, headers=None):
        request = Request(
            f"http://127.0.0.1:{self.port}" + path,
            data=body,
            method=method,
            headers={"User-Agent": "BodySyntaxLab", **(headers or {})},
        )
        start = time.perf_counter()
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as e:
            response = e
        with response:
            return (
                response.status,
                dict(response.headers),
                response.read(),
                (time.perf_counter() - start) * 1000,
            )


def run(runtime, output, *, opt_in, off_only=False, student_only=False):
    if off_only and opt_in:
        raise ValueError("OFF-only acceptance cannot enable the candidate")
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    ready = load(runtime / "ready.json")
    infra = load(runtime / "secrets.json")
    assert ready["state"] == "READY" and not (runtime / "cleanup.json").exists()
    previous = load(ROOT / "ai-training/.artifacts/body_syntax_20261107/plan.json")
    protected, source_updates = protected_snapshot(previous)
    for p, sha in protected.items():
        assert file_sha256(ROOT / p) == sha
    protocol = {
        "baseline": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "reviewed_source_updates": source_updates,
        "mode": "STUDENT_OFF_ONLY"
        if off_only
        else "STUDENT_OFF_ON"
        if student_only
        else "FULL_OFF_ON",
        "candidate_contract_sha256": syntax.CONTRACT_SHA256,
        "default": "BODY_SYNTAX_EXPERIMENT=OFF",
        "opt_in_requested": opt_in,
        "training": False,
        "new_dataset_capture": False,
        "workflow_pairs": [
            "Student form login/me",
            "Student JSON logout",
            "Student malformed/unsupported/gzip/oversize",
            "Student empty body and malformed form",
            "Student chunked",
            "DVWA stored-XSS",
            "DVWA command stdout",
        ],
        "privacy": "Canary content/encoded/digest scan all relevant lab files, DB tables, real Rust/API plus protected-value feature invariance; no raw bodies are exported to any journal",
        "Rust_candidate_contract": "Existing strict AI_SHADOW ingress rejects numeric body-v1 events; assert rejection and no candidate scores in DB/API, do not change Rust/Policy",
        "bounded_failure_cases": [
            "parser exception",
            "absent worker socket",
            "non-socket datagram target",
        ],
        "malformed_form_contract": "Direct Tomcat InvalidParameterException declares400; complete parser failure in original filter dispatch, not synthetic audit500 or ERROR-auth401/403",
        "truncation": "Over8KiB bodies withheld entirely and marked OVERSIZE, never partial-parse. TRUNCATED state exists in offline contract; incomplete HTTP is not claimed here.",
        "sources": {
            p: file_sha256(ROOT / p)
            for p in [
                "ai-training/scripts/validate-real-body-ingress.py",
                "ai-training/src/idps_ai/features/body_syntax_ingress_lab.py",
            ]
        },
        "protected_sha256": protected,
    }
    if off_only or student_only:
        protocol["workflow_pairs"] = [
            v for v in protocol["workflow_pairs"] if not v.startswith("DVWA")
        ]
    if off_only:
        protocol["privacy"] = (
            "NOT_TESTED in OFF-only status recovery; no final privacy scans or candidate activation"
        )
        protocol["bounded_failure_cases"] = []
    if student_only:
        protocol["Rust_candidate_contract"] += (
            "; separate opt-in Rust lab example validates and stores numeric events in dedicated schema, authenticated loopback read API"
        )
    protocol["fingerprint"] = digest(protocol)
    atomic_json(output / "protocol.json", protocol)
    gate = Gate(output / "gate.json")
    children = []
    threads_stop = threading.Event()
    request_rows = []
    features = []
    failure_checks = []
    frozen_checks = {}
    rss_by_mode = {}
    canaries = [
        "FakePassword-" + secrets.token_hex(20),
        "FakeApiKey-" + secrets.token_hex(20),
        "FakeSession-" + secrets.token_hex(20),
        secrets.token_hex(32),
        "person-" + secrets.token_hex(8) + "@example.invalid",
        "+849" + str(secrets.randbelow(10**8)).zfill(8),
    ]
    needles = {
        v.encode()
        for c in canaries
        for v in [
            c,
            quote(c),
            base64.b64encode(c.encode()).decode(),
            c.encode().hex(),
            hashlib.sha256(c.encode()).hexdigest(),
            hashlib.sha1(c.encode()).hexdigest(),
            json.dumps(c)[1:-1],
        ]
    }
    psql = ROOT / ".local-dev/real-ingress-20261107/pgclient/runtime/usr/lib/postgresql/18/bin/psql"
    module_from_path = importlib.util.spec_from_file_location(
        "live_frozen_contract", ROOT / "scripts/ai-shadow-worker.py"
    )
    frozen_module = importlib.util.module_from_spec(module_from_path)
    module_from_path.loader.exec_module(frozen_module)
    predictor = frozen_module.module(
        frozen_module.BUNDLE / "infer.py", "live_frozen_predictor"
    ).RequestPredictor(frozen_module.BUNDLE)

    def sql(db, text):
        p = subprocess.run(
            [
                str(psql),
                "-h",
                "127.0.0.1",
                "-p",
                str(ready["pg_port"]),
                "-U",
                "postgres",
                "-d",
                db,
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                text,
            ],
            env=os.environ | {"PGPASSWORD": infra["pg"], "PGCONNECT_TIMEOUT": "3"},
            capture_output=True,
            timeout=15,
        )
        if p.returncode:
            raise RuntimeError("Private SQL validation failed")
        return p.stdout

    def spawn(name, args):
        file = (output / (name + ".log")).open("ab")
        p = subprocess.Popen(
            args,
            cwd=ROOT,
            env=os.environ | {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            stdout=file,
            stderr=file,
        )
        children.append((p, file))
        return p

    def safe_scan():
        counts = {}
        for folder in [output, runtime]:
            n = 0
            for path in folder.rglob("*"):
                if path.is_file():
                    with path.open("rb") as stream:
                        carry = b""
                        while block := stream.read(1024 * 1024):
                            if any(s in carry + block for s in needles):
                                gate.trip("PRIVACY_CANARY_FILE_FAILURE")
                                raise RuntimeError("Privacy canary file violation; candidate OFF")
                            carry = block[-max(map(len, needles)) :]
                    n += 1
            counts[folder.name] = n
        for db in ["student_db", "security_db"]:
            tables = (
                sql(
                    db,
                    "SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname !~ '^pg_' AND schemaname<>'information_schema'",
                )
                .decode()
                .splitlines()
            )
            for table in tables:
                assert re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+", table)
                schema, name = table.split(".")
                blob = sql(db, f'COPY "{schema}"."{name}" TO STDOUT')
                if any(s in blob for s in needles):
                    gate.trip("PRIVACY_CANARY_DATABASE_FAILURE")
                    raise RuntimeError("Privacy canary DB violation; candidate OFF")
            counts[db + "_tables"] = len(tables)
        return counts

    worker = SyntaxWorker(output / "candidate-worker")
    ingress = monitor = None
    lab_containers = []
    lab_network = None
    q = module("quality-lab-cohort")
    d = module("p0-dvwa-capture")

    def lab_pm(*args, check=True):
        result = subprocess.run(
            ["podman", *map(str, args)],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ | {"GOMAXPROCS": "1"},
        )
        if check and result.returncode:
            safe = result.stderr
            for private in list(infra.values()) + canaries:
                safe = safe.replace(private, "[REDACTED]")
            evidence = output / f"container-failure-{time.time_ns()}.json"
            pid_state = {}
            group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split(
                "::", 1
            )[1].lstrip("/")
            for field in ["pids.current", "pids.max", "pids.events"]:
                if (group / field).is_file():
                    pid_state[field] = (group / field).read_text().strip()
            atomic_json(
                evidence,
                {
                    "operation": args[0],
                    "exit_code": result.returncode,
                    "stderr": safe_nginx_diagnostic(safe),
                    "pid_state": pid_state,
                },
            )
            raise RuntimeError(f"Owned lab container command failed; diagnostics: {evidence}")
        return result.stdout.strip()

    q.pm = lab_pm
    d.APP = "real-ingress-20261108-v1-dvwa"
    d.DB = "real-ingress-20261108-v1-maria"
    d.NET = "real-ingress-20261108-v1-net"
    d.PORT = 18290
    d.podman = q.pm
    work = tempfile.TemporaryDirectory(prefix="idps-real-ingress-")
    try:
        sockroot = Path(work.name)
        ingress = LabIngress(
            sockroot / "body.sock",
            [
                ("/vulnerabilities/", 18290),
                ("/login.php", 18290),
                ("/setup.php", 18290),
                ("/", ready["student_port"]),
            ],
            worker.socket_path,
            gate,
        )
        for name in TEMP_NAMES:
            (output / name).mkdir(mode=0o700)
        monitor = TempMonitor(
            {
                "NGINX_BODY": output / "body",
                "NGINX_PROXY": output / "proxy",
                "NGINX_FASTCGI": output / "fastcgi",
                "NGINX_SCGI": output / "scgi",
                "NGINX_UWSGI": output / "uwsgi",
                "STUDENT_TMP": runtime / "student-tmp",
                "SELF_TEST": output / "self-test",
            },
            gate,
        )
        probe = output / "self-test" / "probe"
        probe.write_text("nonsecret observer proof")
        probe.unlink()
        wait(lambda: monitor.counts["SELF_TEST"])
        assert monitor.healthy and not gate.latched
        frozen_socket = sockroot / "frozen.sock"
        frozen_journal = output / "frozen-source.jsonl"
        spawn(
            "frozen-worker",
            [
                str(ROOT / "ai-training/.venv/bin/python"),
                str(ROOT / "scripts/ai-shadow-worker.py"),
                "--socket",
                str(frozen_socket),
                "--output",
                str(frozen_journal),
            ],
        )
        wait(lambda: frozen_socket.exists(), 60)

        def bridge():
            offsets = {}
            while not threads_stop.wait(0.03):
                for source in [frozen_journal, worker.directory / "candidate.jsonl"]:
                    if not source.exists():
                        continue
                    with source.open() as stream:
                        stream.seek(offsets.get(source, 0))
                        lines = stream.readlines()
                        offsets[source] = stream.tell()
                    with (runtime / "rust-input.jsonl").open("a") as target:
                        for line in lines:
                            value = json.loads(line)
                            if source.name == "candidate.jsonl":
                                syntax.validate_event(value)
                                if student_only:
                                    with (runtime / "body-research-input.jsonl").open(
                                        "a"
                                    ) as body_target:
                                        body_target.write(
                                            json.dumps(value, separators=(",", ":")) + "\n"
                                        )
                            target.write(json.dumps(value, separators=(",", ":")) + "\n")

        bridge_thread = threading.Thread(target=bridge, daemon=True)
        bridge_thread.start()
        config = nginx_config(output, runtime, ingress.path, frozen_socket)
        (output / "nginx.conf").write_text(config)
        nginx_bin = NGINX
        nginx_preflight(output)
        spawn(
            "nginx",
            [
                "strace",
                "-f",
                "-e",
                "trace=%file",
                "-o",
                str(output / "nginx-files.trace"),
                str(nginx_bin),
                "-p",
                str(output),
                "-c",
                str(output / "nginx.conf"),
            ],
        )
        wait(lambda: (output / "nginx.pid").read_text().strip())
        if not (off_only or student_only):
            # Fresh pinned DVWA lab. Its Session helper is replaced with RAM-only IO;
            # the historical collector would write receipts and is not used here.
            q.pm(
                "network",
                "create",
                "--internal",
                "--label",
                "idps.research-run=real-ingress-20261108-v1",
                d.NET,
            )
            lab_network = d.NET
            for name, image, extra in [
                (
                    d.DB,
                    d.DB_IMAGE,
                    [
                        "--network-alias",
                        "db",
                        "-e",
                        "MYSQL_ROOT_PASSWORD=dvwa",
                        "-e",
                        "MYSQL_DATABASE=dvwa",
                        "-e",
                        "MYSQL_USER=dvwa",
                        "-e",
                        "MYSQL_PASSWORD=p@ssw0rd",
                    ],
                ),
                (d.APP, d.APP_IMAGE, ["-p", "127.0.0.1:18290:80", "-e", "DB_SERVER=db"]),
            ]:
                q.pm("image", "inspect", image)
                q.pm(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--label",
                    "idps.research-run=real-ingress-20261108-v1",
                    "--network",
                    d.NET,
                    "--cpus=.25",
                    "--memory=512m",
                    "--memory-swap=512m",
                    "--pids-limit=128",
                    "--log-driver=none",
                    "--security-opt=no-new-privileges",
                    *extra,
                    image,
                )
                lab_containers.append(name)

            class MemorySession:
                cookies = {}

                def call(self, method, path, body="", extra=None):
                    headers = {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items()),
                        **(extra or {}),
                    }
                    status, rh, response = d.low_http(18290, method, path, body.encode(), headers)
                    for k, v in rh:
                        if k.lower() == "set-cookie":
                            jar = SimpleCookie()
                            jar.load(v)
                            self.cookies.update({key: val.value for key, val in jar.items()})
                    return status, rh, response, headers

            dvwa = MemorySession()
            wait(
                lambda: (
                    q.pm(
                        "exec",
                        d.DB,
                        "mariadb",
                        "-udvwa",
                        "-pp@ssw0rd",
                        "-N",
                        "dvwa",
                        "-e",
                        "SELECT 1",
                        check=False,
                    )
                    == "1"
                ),
                60,
            )
            d.initialize(dvwa)
            info = json.loads(q.pm("inspect", d.APP))[0]
            merged = Path(info["GraphDriver"]["Data"]["MergedDir"])
            monitor.counts["DVWA_TMP"] = 0
            monitor._watch(merged / "tmp", "DVWA_TMP")

        def call(client, label, method, path, body=None, headers=None, expected=None):
            atomic_json(
                output / "progress.json", {"phase": "ON" if gate.enabled else "OFF", "case": label}
            )
            was_on = gate.enabled
            status, rh, response, ms = client.call(method, path, body, headers)
            check_application_status(output, label, was_on, status, expected)
            rid = rh.get("X-Request-Id")
            assert rid and re.fullmatch(r"[a-f0-9]{32}", rid)
            if was_on:
                event = wait(lambda: worker.events.get(rid))
                h = {k.lower(): v for k, v in (headers or {}).items()}
                expected_vector = syntax.extract(
                    b"" if h.get("transfer-encoding") == "chunked" else body,
                    h.get("content-type"),
                    content_encoding=h.get("content-encoding"),
                    transfer_encoding=h.get("transfer-encoding"),
                )
                assert event["features"] == expected_vector, "Offline/live candidate parity failed"
                features.append(event["features"])
            if path.startswith("/api/"):
                h = {k.lower(): v for k, v in (headers or {}).items()}
                result = predictor.predict(
                    frozen_module.model_record(
                        {
                            "request_id": rid,
                            "method": method,
                            "url": path,
                            "headers": {
                                "User-Agent": "BodySyntaxLab",
                                "Accept": "",
                                "Content-Type": h.get("content-type", ""),
                            },
                        }
                    )
                )
                frozen_checks[rid] = result["score"]
            request_rows.append(
                {
                    "label": label,
                    "candidate_on": was_on,
                    "status": status,
                    "request_id": rid,
                    "latency_ms": ms,
                    "parity": True if was_on else None,
                }
            )
            atomic_json(output / "request-metadata.json", request_rows)
            return response, rid

        def csrf(client):
            page, _ = call(client, "csrf", "GET", "/api/auth/csrf", expected=200)
            value = json.loads(page)
            return {value["headerName"]: value["token"]}

        def frozen_parity():
            rows = [json.loads(line) for line in frozen_journal.read_text().splitlines()]
            scored = {r["request_id"]: r["score"] for r in rows if r.get("status") == "SCORED"}
            if not set(frozen_checks) <= set(scored):
                return False
            assert all(abs(scored[k] - v) <= 1e-7 for k, v in frozen_checks.items()), (
                "Frozen offline/live score regression"
            )
            return True

        # Actual application baseline OFF, then the same workflows ON.
        for phase in [False] if off_only else [False, True]:
            if phase:
                assert ingress.sent == 0 and worker.accepted == 0, "OFF emitted numeric events"
                safe_scan()
                assert monitor.healthy and gate.enable(opt_in=opt_in, privacy_preflight=True)
            else:
                assert not gate.enabled
            import psutil

            rss_by_mode[str(phase)] = {"start": psutil.Process().memory_info().rss}
            c = Client(18890)
            h = csrf(c) | {"Content-Type": "application/x-www-form-urlencoded"}
            call(
                c,
                "form-login",
                "POST",
                "/api/auth/login",
                urlencode({"username": "ingress-admin", "password": infra["admin"]}).encode(),
                h,
                204,
            )
            page, _ = call(c, "authenticated-me", "GET", "/api/auth/me", expected=200)
            assert json.loads(page)["username"] == "ingress-admin"
            h = csrf(c) | {"Content-Type": "application/json"}
            call(
                c,
                "JSON-logout",
                "POST",
                "/api/auth/logout",
                json.dumps(
                    {
                        "message": "ordinary quoted notes < b && c",
                        "password": canaries[0],
                        "token": canaries[2],
                        "email": canaries[4],
                    }
                ).encode(),
                h,
                204,
            )
            call(c, "logout-state", "GET", "/api/auth/me", expected=401)
            # Every canary reaches real HTTP and an application auth-denial path.
            vectors = []
            for canary in canaries:
                h = csrf(c) | {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": "Bearer " + canary,
                    "Cookie": "; ".join(f"{v.name}={v.value}" for v in c.cookies)
                    + "; lab_canary="
                    + canary,
                }
                body = urlencode(
                    {
                        "username": "nonexistent-user",
                        "password": canary,
                        "api_key": canary,
                        "session_token": canary,
                        "phone": canaries[-1],
                    }
                ).encode()
                _, rid = call(c, "canary-auth-denial", "POST", "/api/auth/login", body, h, 401)
                if phase:
                    vectors.append(worker.events[rid]["features"])
            if phase:
                assert all(v == vectors[0] for v in vectors), (
                    "Protected values influenced candidate features"
                )
            format_cases = [
                ("empty", b"", {"Content-Type": "application/json"}, 400),
                ("malformed", b'{"token":', {"Content-Type": "application/json"}, 400),
                (
                    "unsupported",
                    canaries[1].encode(),
                    {"Content-Type": "application/octet-stream"},
                    415,
                ),
                (
                    "gzip",
                    gzip.compress(
                        json.dumps({"token": canaries[2], "password": canaries[0]}).encode()
                    ),
                    {"Content-Type": "application/json", "Content-Encoding": "gzip"},
                    400,
                ),
                (
                    "oversize",
                    json.dumps({"token": canaries[2], "password": canaries[0] * 180}).encode(),
                    {"Content-Type": "application/json"},
                    400,
                ),
            ]
            for label, body, headers, expected in format_cases:
                call(c, label, "POST", "/api/auth/activate", body, csrf(c) | headers, expected)
            call(
                c,
                "malformed-form",
                "POST",
                "/api/auth/login",
                b"message=%FF",
                csrf(c) | {"Content-Type": "application/x-www-form-urlencoded"},
                400,
            )
            # Real client chunking, kept unsupported by unchanged v1 contract.
            body = json.dumps({"token": canaries[2], "password": "short"}).encode()
            call(
                c,
                "chunked",
                "POST",
                "/api/auth/activate",
                iter([body[:10], body[10:]]),
                csrf(c) | {"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
                400,
            )
            rss_by_mode[str(phase)]["end"] = psutil.Process().memory_info().rss
            if off_only or student_only:
                continue
            q.pm(
                "exec",
                d.DB,
                "mariadb",
                "-udvwa",
                "-pp@ssw0rd",
                "-N",
                "dvwa",
                "-e",
                "TRUNCATE guestbook",
            )
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "; ".join(f"{k}={v}" for k, v in dvwa.cookies.items()),
            }
            markup = "<svg onload=alert(31)>"
            response, _ = call(
                c,
                "DVWA-XSS-unsafe-reflection",
                "POST",
                "/vulnerabilities/xss_s/",
                urlencode(
                    {
                        "txtName": "LabReader",
                        "mtxMessage": markup,
                        "btnSign": "Sign Guestbook",
                        "api_key": canaries[1],
                    }
                ).encode(),
                headers,
                200,
            )
            assert ("Name: LabReader<br />Message: " + markup + "<br />").encode() in response
            count = q.pm(
                "exec",
                d.DB,
                "mariadb",
                "-udvwa",
                "-pp@ssw0rd",
                "-N",
                "dvwa",
                "-e",
                "SELECT COUNT(*) FROM guestbook WHERE comment='<svg onload=alert(31)>'",
            )
            assert count == "1"
            response, _ = call(
                c,
                "DVWA-command-stdout",
                "POST",
                "/vulnerabilities/exec/",
                urlencode(
                    {
                        "ip": "127.0.0.1; printf '%s' AI_INTENT_PIPE | cat",
                        "Submit": "Submit",
                        "api_key": canaries[1],
                    }
                ).encode(),
                headers,
                200,
            )
            region = re.search(rb'<div class="vulnerable_code_area">(.*?)</div>', response, re.S)
            assert region and b"AI_INTENT_PIPE" in b"\n".join(
                re.findall(rb"<pre>(.*?)</pre>", region[1], re.S)
            )
        if off_only:
            wait(frozen_parity, 30)
            assert not gate.enabled and ingress.sent == 0 and worker.accepted == 0
            audit_rows = [
                json.loads(line)
                for line in (runtime / "student-audit.jsonl").read_text().splitlines()
            ]
            conflicts = audit_status_differences(request_rows, audit_rows)
            for path, sha in protected.items():
                assert file_sha256(ROOT / path) == sha
            result = {
                "case": "STUDENT_BOUNDED_OFF_PARTIAL" if conflicts else "STUDENT_BOUNDED_OFF_PASS",
                "REAL_INGRESS_OFF": "PARTIAL" if conflicts else "PASS",
                "scope": "Student workflows only; no DVWA or ON/privacy experiment",
                "candidate_default": "OFF",
                "candidate_final": "OFF",
                "ON_requests": 0,
                "candidate_events": 0,
                "request_count": len(request_rows),
                "audit_request_ids_matched": len(request_rows),
                "audit_wire_status_conflicts": conflicts,
                "statuses": {r["label"]: r["status"] for r in request_rows},
                "frozen_request_offline_live_parity": len(frozen_checks),
                "frozen_body_observed": False,
                "privacy_acceptance": "NOT_TESTED",
                "GLU207_live_score": "NOT_TESTED_NO_SENSOR_FEATURES",
                "sealed_opened": False,
                "training": "NOT_RUNNING",
                "protocol_fingerprint": protocol["fingerprint"],
            }
            atomic_json(output / "report.json", result)
            if conflicts:
                raise RuntimeError(
                    f"OFF audit/wire status conflict; diagnostics: {output / 'report.json'}"
                )
            print(json.dumps(result, indent=2))
            return result
        # Inspect actual Rust ingestion/database/API, not a mock serializer.
        wait(
            lambda: (
                int(
                    sql(
                        "security_db",
                        "SELECT count(*) FROM ingestion_errors WHERE source='AI_SHADOW'",
                    ).strip()
                )
                >= ingress.sent
            )
        )
        security = Client(ready["security_port"])
        status, _, page, _ = security.call(
            "POST",
            "/api/auth/login",
            json.dumps({"username": "admin", "password": infra["security_admin"]}).encode(),
            {"Content-Type": "application/json"},
        )
        assert status == 200
        token = json.loads(page)["token"]
        status, _, page, _ = security.call(
            "GET", "/api/ai-shadow?limit=200", headers={"Authorization": "Bearer " + token}
        )
        assert status == 200 and not any(n in page for n in needles)
        api_page = json.loads(page)
        assert any(r.get("request_ai") for r in api_page["detectors"])
        research_persistence = None
        if student_only:
            observer = Client(18291)
            status, _, _, _ = observer.call("GET", "/observations")
            assert status == 401, "Research API must require private authentication"

            def persisted_candidate():
                status, _, body, _ = observer.call(
                    "GET", "/observations", headers={"Authorization": "Bearer " + infra["body_api"]}
                )
                assert status == 200 and not any(n in body for n in needles)
                result = json.loads(body)
                by_id = {v["request_id"]: v for v in result["items"]}
                if not set(worker.events) <= set(by_id):
                    return False
                for rid, event in worker.events.items():
                    syntax.validate_event(by_id[rid])
                    assert event == by_id[rid], "Rust/DB/API numeric parity failed"
                assert result["rejected"] == 0 and result["accepted"] == len(worker.events)
                return {
                    "accepted_current_run": result["accepted"],
                    "numeric_DB_API_parity": len(worker.events),
                    "unauthenticated": 401,
                    "authenticated": 200,
                    "scope": "ISOLATED_RESEARCH_SCHEMA_AND_API; no production endpoint",
                }

            research_persistence = wait(persisted_candidate, 30)
            assert (
                worker.thread.is_alive()
                and worker.accepted == ingress.sent
                and worker.rejected == 0
            )
        wait(
            lambda: all(
                int(
                    sql(
                        "security_db",
                        f"SELECT count(DISTINCT source) FROM normalized_events WHERE request_id='{r['request_id']}' AND source IN ('NGINX','STUDENT_AUDIT')",
                    ).strip()
                )
                == 2
                for r in request_rows
                if r["label"] in {"form-login", "authenticated-me", "JSON-logout"}
            ),
            30,
        )

        # Compare real frozen-worker inference with the unchanged offline predictor.
        wait(frozen_parity, 30)

        # Real failures before legitimate Student login. No re-arming a latched gate;
        # each case uses a fresh OFF gate with explicit lab-only activation.
        def broken(*_, **__):
            raise ValueError(canaries[0])

        for failure in protocol["bounded_failure_cases"]:
            gate.off()
            c = Client(18890)
            h = csrf(c) | {"Content-Type": "application/x-www-form-urlencoded"}
            gate = Gate(output / f"failure-{len(failure_checks)}-gate.json")
            ingress.gate = gate
            monitor.gate = gate
            ingress.extractor = broken if failure == "parser exception" else syntax.extract
            if failure == "absent worker socket":
                worker.close()
                ingress.worker_path = worker.socket_path
            elif failure == "non-socket datagram target":
                wrong_target = sockroot / "not-a-socket"
                wrong_target.touch(mode=0o600)
                ingress.worker_path = str(wrong_target)
            assert gate.enable(opt_in=opt_in, privacy_preflight=True)
            status, rh, _, _ = c.call(
                "POST",
                "/api/auth/login",
                urlencode({"username": "ingress-admin", "password": infra["admin"]}).encode(),
                h,
            )
            assert status == 204 and gate.latched and not gate.enabled
            status, _, response, _ = c.call("GET", "/api/auth/me")
            assert status == 200 and json.loads(response)["username"] == "ingress-admin"
            failure_checks.append(
                {"case": failure, "login": 204, "session": 200, "candidate": "OFF_LATCHED"}
            )
            atomic_json(output / "failure-checks.json", failure_checks)
        wait(frozen_parity, 30)
        np.savez(output / "candidate-feature-artifact.npz", features=np.array(features, np.uint8))
        scan = safe_scan()
        if not student_only:
            maria_tables = q.pm(
                "exec", d.DB, "mariadb", "-udvwa", "-pp@ssw0rd", "-N", "dvwa", "-e", "SHOW TABLES"
            ).splitlines()
            for table in maria_tables:
                assert re.fullmatch(r"[A-Za-z0-9_]+", table)
                contents = q.pm(
                    "exec",
                    d.DB,
                    "mariadb",
                    "-udvwa",
                    "-pp@ssw0rd",
                    "-N",
                    "dvwa",
                    "-e",
                    "SELECT * FROM " + table,
                ).encode()
                if any(n in contents for n in needles):
                    gate.trip("PRIVACY_CANARY_DVWA_DATABASE_FAILURE")
                    raise RuntimeError("Privacy canary lab database violation; candidate OFF")
            scan["DVWA_MariaDB_tables"] = len(maria_tables)
        assert monitor.healthy and all(
            n == 0 for key, n in monitor.counts.items() if key != "SELF_TEST"
        )
        rows_by_mode = [
            {r["label"]: r["status"] for r in request_rows if r["candidate_on"] == mode}
            for mode in [False, True]
        ]
        assert rows_by_mode[0] == rows_by_mode[1]
        audit_rows = [
            json.loads(line) for line in (runtime / "student-audit.jsonl").read_text().splitlines()
        ]
        assert not audit_status_differences(request_rows, audit_rows)
        assert ingress.dropped == len(failure_checks), "Unexpected nominal telemetry drop"
        assert set(worker.events) == {r["request_id"] for r in request_rows if r["candidate_on"]}
        assert {
            "MISSING",
            "EMPTY",
            "OK",
            "MALFORMED",
            "OVERSIZE",
            "UNSUPPORTED_TYPE",
            "UNSUPPORTED_ENCODING",
            "UNSUPPORTED_TRANSFER",
        } <= {syntax.state_of(v) for v in features}
        rust_errors = int(
            sql(
                "security_db", "SELECT count(*) FROM ingestion_errors WHERE source='AI_SHADOW'"
            ).strip()
        )
        frozen_count = int(sql("security_db", "SELECT count(*) FROM ai_shadow_results").strip())
        assert int(sql("security_db", "SELECT count(*) FROM firewall_actions").strip()) == 0
        result = {
            "case": "CASE_A_VERIFIED_FOR_LAB",
            "LIVE_OBSERVABILITY": "VERIFIED_FOR_LAB",
            "PRODUCTION_PRIVACY": "NOT_VERIFIED",
            "candidate_default": "OFF",
            "candidate_final": "OFF",
            "contract_sha256": syntax.CONTRACT_SHA256,
            "candidate_redesigned": False,
            "application_workflows": rows_by_mode,
            "HTTP_request_count": len(request_rows),
            "candidate_events": ingress.sent,
            "parity_pass": len(features),
            "body_states": dict(Counter(syntax.state_of(v) for v in features)),
            "temp_monitor": {
                "healthy": monitor.healthy,
                "counts": monitor.counts,
                "deleted_file_detection_self_test": True,
            },
            "privacy_scan": scan,
            "Rust_ingestion": {
                "numeric_candidate_records_rejected_as_wrong_version": rust_errors,
                "frozen_metadata_records_accepted": frozen_count,
                "raw_rejection_reason_suppressed": True,
                "candidate_features_in_existing_AI_model_tables": False,
                "isolated_valid_candidate_persistence": research_persistence,
            },
            "dashboard_API": "REAL_AUTHENTICATED_API_READ_SCAN_PASS",
            "failure_open_checks": failure_checks,
            "frozen_request_offline_live_parity": len(frozen_checks),
            "audit_request_ids_matched": len(request_rows),
            "audit_wire_status_conflicts": 0,
            "firewall_actions": 0,
            "protected_value_feature_invariance": True,
            "raw_body_or_secret_hash_exported": False,
            "nominal_drops": ingress.dropped - len(failure_checks),
            "deliberate_failure_drops": len(failure_checks),
            "max_buffer_prefix_bytes": ingress.max_prefix,
            "max_numeric_datagram_bytes": ingress.max_payload_bytes,
            "extractor_latency_ms_p50_p95_max": np.quantile(
                ingress.extraction_ms[: len(features)], [0.5, 0.95, 1.0]
            ).tolist(),
            "acceptance_process_RSS_bytes_by_mode": rss_by_mode,
            "performance_scope": "Sequential small control; harness includes reference predictor, scanners and workers. Not a production overhead benchmark.",
            "latency_ms_OFF_ON_p50_p95": {
                str(mode): np.quantile(
                    [r["latency_ms"] for r in request_rows if r["candidate_on"] == mode],
                    [0.5, 0.95],
                ).tolist()
                for mode in [False, True]
            },
            "new_training_steps": 0,
            "new_checkpoints": 0,
            "sealed_opened": False,
            "limits": [
                "Local HTTP only, production TLS/LAN/other host paths not qualified",
                "Existing Rust contract rejects candidate features, intentionally no score/schema/policy change",
                "Per-request size/timing and coarse-syntax side channels remain; no absolute privacy/DP claim",
                "No real Suricata capture/GLU207 score in this request-only run; GLU contract compatibility and frozen checksums tested separately, never synthesize missing sensor features",
                "Incomplete HTTP truncation, valid multipart file upload and socket queue saturation not exercised",
            ],
            "next_task": "Re-audit the fixed attack-intent release's candidate views and group splits using only this verified-for-lab numeric contract; no automatic training.",
        }
        for path, sha in protected.items():
            assert file_sha256(ROOT / path) == sha
        atomic_json(output / "request-metadata.json", request_rows)
        atomic_json(output / "report.json", result)
        atomic_json(ROOT / "ai-training/reports/BODY_SYNTAX_LIVE_20261108.json", result)
        print(json.dumps(result, indent=2))
    finally:
        gate.off()
        atomic_json(
            output / "gate.json",
            {"BODY_SYNTAX_EXPERIMENT": "OFF", "latched": gate.latched, "reason": gate.reason},
        )
        threads_stop.set()
        if ingress:
            ingress.close()
        worker.close()
        if monitor:
            monitor.close()
        for p, f in reversed(children):
            p.terminate()
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
            f.close()
        for name in reversed(lab_containers):
            q.pm("rm", "-f", name, check=False)
        if lab_network:
            q.pm("network", "rm", lab_network, check=False)
        work.cleanup()
        atomic_json(
            output / "cleanup.json",
            {"candidate": "OFF", "own_servers_closed": True, "normal_demo_modified": False},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--enable-body-syntax", action="store_true")
    p.add_argument("--nginx-preflight-only", action="store_true")
    p.add_argument(
        "--off-only",
        action="store_true",
        help="Bounded Student OFF checks; never enable candidate or run privacy acceptance",
    )
    p.add_argument(
        "--student-only",
        action="store_true",
        help="Use verified Student fixtures only, no DVWA probes",
    )
    a = p.parse_args()
    if a.nginx_preflight_only:
        if a.enable_body_syntax or a.off_only:
            p.error("--nginx-preflight-only cannot be combined with an acceptance mode")
        print(json.dumps(preflight_only(a.output), indent=2))
    elif a.off_only:
        if a.enable_body_syntax:
            p.error("--off-only cannot be combined with --enable-body-syntax")
        if a.runtime is None:
            p.error("--runtime is required for OFF-only acceptance")
        run(a.runtime.resolve(), a.output.resolve(), opt_in=False, off_only=True)
    elif not a.enable_body_syntax:
        print(json.dumps({"BODY_SYNTAX_EXPERIMENT": "OFF", "lab_started": False}))
    else:
        if a.runtime is None:
            p.error("--runtime is required for opt-in full acceptance")
        run(a.runtime.resolve(), a.output.resolve(), opt_in=True, student_only=a.student_only)

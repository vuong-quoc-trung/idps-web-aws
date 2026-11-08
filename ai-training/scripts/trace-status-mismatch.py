#!/usr/bin/env python3
"""Finite harmless direct/edge status diagnostic; candidate is unconditionally OFF.

Requires a separately owned lab runtime. Records metadata only, not CSRF/cookie/body
values. FilterChainProxy DEBUG may be enabled in that lab for dispatch evidence.
"""

import argparse
import importlib.util
import json
import os
import re
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path

from idps_ai.common import atomic_json
from idps_ai.features.body_syntax_ingress_lab import Gate, LabIngress

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "status_ingress_harness", Path(__file__).with_name("validate-real-body-ingress.py")
)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def dispatch_events(lines):
    events = []
    for line in lines:
        if "Securing POST /api/auth/activate" in line:
            events.append("REQUEST_SECURITY_CHAIN")
        if "HttpMediaTypeNotSupportedException" in line:
            events.append("MVC_UNSUPPORTED_MEDIA")
        if re.search(r"Securing (?:GET|POST) /error(?:\s|$)", line):
            events.append("ERROR_SECURITY_CHAIN")
    return events


def run(runtime, output):
    os.umask(0o077)
    assert output.is_relative_to(ROOT / ".local-dev"), "Diagnostics must remain local-only"
    ready = h.load(runtime / "ready.json")
    assert ready["state"] == "READY" and not (runtime / "cleanup.json").exists()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name in h.TEMP_NAMES:
        (output / name).mkdir(mode=0o700)
    gate = Gate(output / "gate.json")
    children = []
    rows = []
    with tempfile.TemporaryDirectory(prefix="idps-status-") as short:
        base = Path(short)
        sink = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sink.bind(str(base / "frozen.sock"))
        # This trace uses no inference. Disable only its frozen syslog access log;
        # full OFF acceptance separately verifies the actual frozen worker.
        ingress = LabIngress(
            base / "body.sock", [("/", ready["student_port"])], base / "no-candidate.sock", gate
        )
        try:
            config = h.nginx_config(output, runtime, ingress.path, base / "frozen.sock")
            syslog = f"access_log syslog:server=unix:{base / 'frozen.sock'},tag=ai_shadow,nohostname body_frozen;"
            assert config.count(syslog) == 1
            config = config.replace(syslog, "")
            diag = """log_format status_diag escape=json '{"request_id":"$request_id","status":$status,"upstream_status":"$upstream_status"}'; """
            config = config.replace("log_format body_frozen", diag + "log_format body_frozen")
            config = config.replace(
                "location /api/ {",
                f"location /api/ {{ access_log {output / 'edge-status.jsonl'} status_diag;",
            )
            config = config.replace(
                "location / {",
                f"location / {{ access_log {output / 'edge-status.jsonl'} status_diag;",
            )
            assert not any(
                x in config for x in ["proxy_intercept_errors", "error_page", "auth_request"]
            )
            (output / "nginx.conf").write_text(config)
            h.nginx_preflight(output)
            with (output / "nginx-process.log").open("ab") as log:
                proc = subprocess.Popen(
                    [str(h.NGINX), "-p", str(output), "-c", str(output / "nginx.conf")],
                    stdout=log,
                    stderr=log,
                )
                children.append(proc)
                h.wait(lambda: (output / "nginx.pid").read_text().strip())
                for route, port in [("direct", ready["student_port"]), ("nginx", 18890)]:
                    client = h.Client(port)

                    def call(label, method, path, body=None, headers=None):
                        supplied = secrets.token_hex(16)
                        common = {
                            "Host": "127.0.0.1",
                            "X-Request-Id": supplied,
                            "X-Real-IP": "127.0.0.1",
                            "X-Forwarded-For": "127.0.0.1",
                            "X-Forwarded-Proto": "http",
                            "Forwarded": "",
                        }
                        logpath = runtime / "student.log"
                        offset = logpath.stat().st_size
                        status, rh, response, _ = client.call(
                            method, path, body, common | (headers or {})
                        )
                        rid = rh.get("X-Request-Id")
                        assert rid and (route != "direct" or rid == supplied)
                        audit = None
                        if path.startswith("/api/"):

                            def find_audit():
                                for line in (
                                    (runtime / "student-audit.jsonl").read_text().splitlines()
                                ):
                                    value = json.loads(line)
                                    if value.get("request_id") == rid:
                                        return value

                            audit = h.wait(find_audit)
                        with logpath.open("rb") as stream:
                            stream.seek(offset)
                            lines = stream.read().decode(errors="replace").splitlines()
                        events = dispatch_events(lines)
                        upstream = None
                        if route == "nginx":

                            def find_edge():
                                for line in (output / "edge-status.jsonl").read_text().splitlines():
                                    v = json.loads(line)
                                    if v["request_id"] == rid:
                                        return v

                            edge = h.wait(find_edge)
                            assert edge["status"] == status
                            upstream = int(edge["upstream_status"])
                        rows.append(
                            {
                                "route": route,
                                "case": label,
                                "request_id": rid,
                                "client_status": status,
                                "application_audit_status": audit.get("status_code")
                                if audit
                                else None,
                                "nginx_upstream_status": upstream,
                                "dispatch_trace": events,
                                "response_content_type": rh.get("Content-Type"),
                                "candidate": "OFF",
                            }
                        )
                        atomic_json(output / "observations.json", rows)
                        assert not gate.enabled and ingress.sent == 0
                        return response

                    csrf = json.loads(call("success-csrf", "GET", "/api/auth/csrf"))
                    csrf_header = {csrf["headerName"]: csrf["token"]}
                    call(
                        "unsupported-media",
                        "POST",
                        "/api/auth/activate",
                        b"status-probe",
                        csrf_header | {"Content-Type": "application/octet-stream"},
                    )
                    call(
                        "malformed-json",
                        "POST",
                        "/api/auth/activate",
                        b'{"token":',
                        csrf_header | {"Content-Type": "application/json"},
                    )
                    call(
                        "missing-csrf",
                        "POST",
                        "/api/auth/activate",
                        b"status-probe",
                        {"Content-Type": "application/octet-stream"},
                    )
                    call("protected-anonymous", "GET", "/api/auth/me")
                    call("error-remains-protected", "GET", "/error")
                assert len({r["request_id"] for r in rows}) == len(rows)
                atomic_json(
                    output / "report.json",
                    {
                        "candidate": "OFF",
                        "observations": rows,
                        "request_equivalence": "Same fixed harmless body/method/path/media; same UA/Host127.0.0.1/XFF127.0.0.1/protohttp. Fresh anonymous cookie/CSRF session per route; token/cookie values remain RAM-only. IDs unique per call; edge overwrites supplied ID.",
                        "proxy_error_interception": False,
                        "frozen_inference": "NOT_RUN_IN_TRACE",
                    },
                )
        finally:
            gate.off()
            ingress.close()
            sink.close()
            for proc in children:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            atomic_json(
                output / "cleanup.json",
                {"candidate": "OFF", "owned_nginx_stopped": True, "sockets_closed": True},
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.runtime.resolve(), args.output.resolve())

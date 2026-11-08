"""Opt-in, transient-write detection and real upstream response framing."""

import http.client
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from idps_ai.features.body_syntax_ingress_lab import Gate, LabIngress, TempMonitor
from idps_ai.features.body_syntax_transport import QuietServer, SyntaxWorker


@pytest.fixture
def harness():
    path = Path(__file__).resolve().parents[1] / "scripts/validate-real-body-ingress.py"
    spec = importlib.util.spec_from_file_location("real_body_ingress_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nginx_config_is_deterministic_and_all_temp_paths_are_local(tmp_path, harness):
    args = (tmp_path, tmp_path, Path("/tmp/lab/body.sock"), Path("/tmp/lab/frozen.sock"))
    config = harness.nginx_config(*args)
    assert config == harness.nginx_config(*args)
    for directive, name in [
        ("client_body", "body"),
        ("proxy", "proxy"),
        ("fastcgi", "fastcgi"),
        ("scgi", "scgi"),
        ("uwsgi", "uwsgi"),
    ]:
        assert f"{directive}_temp_path {tmp_path / name};" in config
    assert "listen 127.0.0.1:18890;" in config
    assert "include " not in config.replace("# Include ", "# ")
    for path in ["/var/lib/nginx", "/var/log/nginx", "/etc/nginx", "/run/nginx"]:
        assert path not in config


def test_real_nginx_preflight_success_and_failure_keep_diagnostics(tmp_path, harness):
    if not harness.NGINX.is_file():
        pytest.skip("Isolated lab Nginx binary is not installed")
    output = tmp_path / "lab"
    report = harness.preflight_only(output)
    assert report["exit_code"] == 0 and report["status"] == "PASS"
    assert not report["http_traffic_started"]
    assert json.loads((output / "gate.json").read_text())["BODY_SYNTAX_EXPERIMENT"] == "OFF"
    assert "test is successful" in Path(report["stderr"]).read_text()
    config = output / "nginx.conf"
    config.write_text(config.read_text() + "\ninvalid_preflight_directive;\n")
    with pytest.raises(RuntimeError, match="Nginx preflight FAIL.*diagnostics:"):
        harness.nginx_preflight(output)
    reports = [json.loads(p.read_text()) for p in output.glob("nginx-preflight-*/diagnostic.json")]
    failure = next(r for r in reports if r["status"] == "FAIL")
    assert failure["exit_code"] == 1 and not failure["http_traffic_started"]
    stderr = Path(failure["stderr"]).read_text()
    assert 'unknown directive "invalid_preflight_directive"' in stderr
    assert str(config) + ":" in stderr
    assert failure["config_sha256"] != report["config_sha256"]
    assert Path(report["stderr"]).is_file()  # Failed retry preserves the earlier evidence.


def test_preflight_timeout_is_saved_and_credential_lines_are_redacted(
    tmp_path, harness, monkeypatch
):
    (tmp_path / "nginx.conf").write_text("events {} http {}")

    def timeout(*_, **__):
        raise subprocess.TimeoutExpired(
            "nginx", 10, stderr=b"password=FAKE_PRIVATE_VALUE\nCookie: FAKE_SESSION_VALUE\n"
        )

    monkeypatch.setattr(harness.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="NGINX_PREFLIGHT_TIMEOUT"):
        harness.nginx_preflight(tmp_path)
    report = json.loads(next(tmp_path.glob("nginx-preflight-*/diagnostic.json")).read_text())
    assert report["exit_code"] is None and report["status"] == "FAIL"
    text = Path(report["stderr"]).read_text()
    assert (
        "REDACTED" in text and "FAKE_PRIVATE_VALUE" not in text and "FAKE_SESSION_VALUE" not in text
    )


def test_cli_without_opt_in_stays_off_and_creates_no_lab(tmp_path, harness):
    output = tmp_path / "not-created"
    result = subprocess.run(
        [sys.executable, harness.__file__, "--output", str(output)],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert json.loads(result.stdout) == {"BODY_SYNTAX_EXPERIMENT": "OFF", "lab_started": False}
    assert not output.exists()


def test_changed_research_artifact_is_never_admitted_as_source_update(tmp_path, harness):
    artifact = tmp_path / "evidence.json"
    artifact.write_text("preserved evidence")
    with pytest.raises(AssertionError, match="Protected artifact changed"):
        harness.protected_snapshot({"protected_sha256": {str(artifact): "0" * 64}})


def test_application_status_failure_preserves_observed_and_locked_status(tmp_path, harness):
    with pytest.raises(RuntimeError, match="actual=401, expected=415"):
        harness.check_application_status(tmp_path, "unsupported", False, 401, 415)
    assert json.loads((tmp_path / "application-failure.json").read_text()) == {
        "case": "unsupported",
        "candidate": "OFF",
        "actual_status": 401,
        "expected_status": 415,
        "raw_response_saved": False,
    }


def test_reviewed_worker_update_preserves_historical_provenance(harness):
    old = subprocess.run(
        ["git", "show", "391d34c:scripts/ai-shadow-worker.py"],
        cwd=harness.ROOT,
        capture_output=True,
        check=True,
    ).stdout
    sha = harness.hashlib.sha256(old).hexdigest()
    protected, updates = harness.protected_snapshot(
        {"protected_sha256": {"scripts/ai-shadow-worker.py": sha}}
    )
    current = harness.file_sha256(harness.ROOT / "scripts/ai-shadow-worker.py")
    assert protected["scripts/ai-shadow-worker.py"] == current
    assert updates["scripts/ai-shadow-worker.py"] == {
        "historical_sha256": sha,
        "reviewed_sha256": current,
    }


@pytest.mark.parametrize("limit", [0, 63, 257, True, 128.0])
def test_invalid_task_budget_rejected_before_starting_workload(tmp_path, harness, limit):
    spec = importlib.util.spec_from_file_location(
        "ingress_guard", Path(harness.__file__).with_name("integration-guard.py")
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    output = tmp_path / "not-started"
    with pytest.raises(ValueError, match="task limit"):
        guard.run(["never-start"], output, tasks_max=limit)
    assert not output.exists()


def test_gate_defaults_off_requires_preflight_and_latches_failures(tmp_path):
    gate = Gate(tmp_path / "gate.json")
    assert not gate.enabled and not gate.enable(opt_in=True)
    assert not gate.enable(privacy_preflight=True)
    assert gate.enable(opt_in=True, privacy_preflight=True)
    gate.trip("PRIVACY_CANARY_FAILURE")
    assert not gate.enabled and not gate.enable(opt_in=True, privacy_preflight=True)
    assert json.loads((tmp_path / "gate.json").read_text())["BODY_SYNTAX_EXPERIMENT"] == "OFF"


def test_deleted_temp_file_still_trips_candidate_off(tmp_path):
    gate = Gate(tmp_path / "gate.json")
    gate.enable(opt_in=True, privacy_preflight=True)
    monitor = TempMonitor({"BODY": tmp_path / "body"}, gate)
    try:
        file = tmp_path / "body" / "short-lived"
        file.write_bytes(b"nonsecret monitor probe")
        file.unlink()
        end = time.monotonic() + 2
        while gate.enabled and time.monotonic() < end:
            time.sleep(0.01)
        assert monitor.healthy and not gate.enabled and monitor.counts["BODY"] > 0
        assert not list((tmp_path / "body").iterdir())
    finally:
        monitor.close()


def test_chunked_application_response_and_parser_failure_are_forwarded(tmp_path):
    class Upstream(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response_only(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Request-Id", self.headers["X-Request-Id"])
            self.end_headers()
            self.wfile.write(b"4\r\ntrue\r\n0\r\n\r\n")

    server = QuietServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    gate = Gate(tmp_path / "gate.json")
    worker = SyntaxWorker(tmp_path / "worker")
    with tempfile.TemporaryDirectory(prefix="idps-ingress-unit-") as path:
        ingress = LabIngress(
            Path(path) / "ingress.sock", [("/", server.server_port)], worker.socket_path, gate
        )

        class Connection(http.client.HTTPConnection):
            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(3)
                self.sock.connect(str(ingress.path))

        try:
            gate.enable(opt_in=True, privacy_preflight=True)
            for fail in [False, True]:
                if fail:

                    def broken(*_, **__):
                        raise ValueError("untrusted failure text")

                    ingress.extractor = broken
                conn = Connection("lab.local")
                conn.request(
                    "POST",
                    "/api/test",
                    b"message=hello",
                    {"Content-Type": "application/x-www-form-urlencoded", "X-Request-Id": "a" * 32},
                )
                response = conn.getresponse()
                assert response.status == 200 and response.read() == b"true"
                assert response.getheader("X-Request-Id") == "a" * 32
                conn.close()
            assert not gate.enabled and gate.latched and ingress.dropped == 1
        finally:
            ingress.close()
            worker.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

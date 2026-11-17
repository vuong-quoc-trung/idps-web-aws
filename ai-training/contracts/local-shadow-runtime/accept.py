"""Bounded benign HTTP and service recovery probe for the installed Local runtime."""

import argparse
import http.client
import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from nginx import render
from runtime import ONNX
from store import connect, stats

from idps_ai.common import REPO_ROOT, atomic_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request
from idps_ai.training.delegated_guard import membership

NGINX = REPO_ROOT / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"
TELEMETRY = REPO_ROOT / "security-web/deploy/ai-shadow/telemetry.conf"
PREFIX = "idps-r22-local-"


def systemctl(*args):
    return subprocess.check_output(["systemctl", "--user", *args], text=True, timeout=12).strip()


def unit(role):
    return PREFIX + role + ".service"


def show(role, key):
    return systemctl("show", unit(role), "--property", key, "--value")


def wait(check, seconds=12):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        result = check()
        if result:
            return result
        time.sleep(0.02)
    raise TimeoutError("Acceptance evidence deadline")


class BenignBackend(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "3")
        self.end_headers()
        self.wfile.write(b"ok\n")


class UnixClient(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=2)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


def scorer_child():
    pid = int(show("scorer", "MainPID"))
    if not pid:
        return None
    root = membership(pid).parent
    worker = root / "ai-worker/cgroup.procs"
    if worker.is_file():
        children = [int(p) for p in worker.read_text().split()]
        if len(children) == 1 and membership(children[0]).parent == root:
            return children[0]
    return None


def acceptance(config, out):
    state = Path(config["state"])
    db = connect(state / "evidence.sqlite")
    model = cpu_session(state / "bundle/swiglu.onnx", 1)
    cases = []
    nginx = None
    backend = BenignBackendServer(("127.0.0.1", 0), BenignBackend)
    thread = threading.Thread(target=backend.serve_forever)
    thread.start()
    with tempfile.TemporaryDirectory(prefix="idps-local-http-") as scratch:
        root = Path(scratch)
        render(root, Path(config["mirror_socket"]))
        listener = root / "nginx.sock"
        conf = root / "nginx.conf"
        conf.write_text(f"""pid {root}/pid;
            error_log /dev/null crit;
            events {{ worker_connections 32; }}
            http {{ client_body_temp_path {root}/body;
              proxy_temp_path {root}/proxy; fastcgi_temp_path {root}/fastcgi;
              uwsgi_temp_path {root}/uwsgi; scgi_temp_path {root}/scgi;
              include {TELEMETRY};
              server {{ listen unix:{listener};
                access_log syslog:server=unix:{config["ri_socket"]},tag=ai_shadow,severity=info pbl4_ai_telemetry if=$pbl4_ai_api;
                include {root}/r22-server.conf;
                location /api/ {{
                  include {root}/r22-proxy.conf;
                  add_header X-IDPS-Request-Id $request_id always;
                  proxy_pass http://127.0.0.1:{backend.server_port};
                }}
              }}
            }}""")

        def scorer_ready():
            try:
                ready = json.loads((state / "scorer-health.json").read_text())
                return (
                    ready["status"] == "READY"
                    and str(ready["pid"]) == show("scorer", "MainPID")
                    and Path(config["score_socket"]).is_socket()
                )
            except FileNotFoundError:
                return False

        def request(name, target, expect="SCORED", queued=False):
            sent = time.monotonic_ns()
            with_client = UnixClient(listener)
            try:
                with_client.request("GET", target)
                response = with_client.getresponse()
                rid = response.getheader("X-IDPS-Request-Id")
                assert response.status == 200 and response.read() == b"ok\n" and rid
            finally:
                with_client.close()
            elapsed = (time.monotonic_ns() - sent) / 1e6
            table = "inbox" if queued else "evidence"
            raw = wait(
                lambda: db.execute(f"SELECT payload FROM {table} WHERE rid=?", (rid,)).fetchone()
            )
            row = json.loads(raw[0])
            scored = row["r20"]
            assert scored["model_sha256"] == ONNX and scored["status"] == expect, (
                name,
                scored["status"],
                scored.get("reason"),
            )
            assert (
                row["source_mask_at_cutoff"] is None
                and row["label"]["kind"] == "UNLABELED_OBSERVATION"
            )
            elapsed_ms = (scored["available_monotonic_ns"] - sent) / 1e6
            assert 0 <= elapsed_ms <= 999
            vector = np.array(row["uri76"]["vector"], dtype=np.float32)
            assert vector.tobytes() == from_request(target, "GET").tobytes()
            err = None
            if expect == "SCORED":
                err = abs(
                    float(model.run(["score"], {"input": vector.reshape(1, 76)})[0][0])
                    - scored["score"]
                )
                assert err <= 1e-7
            if not queued:
                assert row["ri_v2"]["status"] == "SCORED"
            cases.append(
                {
                    "name": name,
                    "request_id": rid,
                    "http_ms": elapsed,
                    "r20_status": scored["status"],
                    "r20_ms": scored.get("inference_ns", 0) / 1e6 if expect == "SCORED" else None,
                    "r20_availability_ms": elapsed_ms,
                    "parity_error": err,
                    "ri_v2_ms": row.get("ri_v2", {}).get("latency_ms"),
                    "uri76_sha256": row["uri76_sha256"],
                    "queued": queued,
                }
            )
            atomic_json(out.with_name("progress.json"), {"state": "IN_PROGRESS", "cases": cases})
            return rid

        try:
            nginx = subprocess.Popen(
                [
                    str(NGINX),
                    "-p",
                    str(root),
                    "-c",
                    str(conf),
                    "-g",
                    "daemon off; master_process off;",
                ]
            )
            wait(listener.is_socket)
            systemctl("restart", unit("scorer"))
            wait(scorer_ready)
            request("cold_start", "/api/catalog")
            for i in range(4):
                request("warm", f"/api/catalog?page={i + 1}")
            parent, child = int(show("scorer", "MainPID")), wait(scorer_child)
            original_restarts = int(show("scorer", "NRestarts"))
            pidfd = os.pidfd_open(child)
            try:
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            finally:
                os.close(pidfd)
            wait(lambda: show("scorer", "SubState") == "auto-restart")
            request("failure_abstain", "/api/catalog?page=5", "ABSTAIN", queued=True)
            new_child = wait(
                lambda: (
                    (value := scorer_child())
                    and value != child
                    and Path(config["score_socket"]).is_socket()
                    and value
                )
            )
            assert (
                int(show("scorer", "MainPID")) != parent
                and int(show("scorer", "NRestarts")) == original_restarts + 1
            )
            wait(scorer_ready)
            request("cold_recovery", "/api/catalog?page=6")
            original = stats(db)
            systemctl("stop", unit("collector"))
            rid1 = request("queue_while_collector_down", "/api/catalog?page=7", queued=True)
            rid2 = request("queue_while_collector_down", "/api/catalog?page=8", queued=True)
            checkpoint = stats(db)
            assert checkpoint["cursor"] == original["cursor"] and checkpoint["pending"] == 2
            systemctl("start", unit("collector"))
            wait(
                lambda: (
                    db.execute(
                        "SELECT count(*) FROM evidence WHERE rid IN (?,?)", (rid1, rid2)
                    ).fetchone()[0]
                    == 2
                )
            )
            resumed = stats(db)
            assert resumed["committed"] == original["committed"] + 2 and resumed["pending"] == 0
            systemctl("stop", unit("scorer"))
            assert not Path(config["score_socket"]).exists()
            request("rollback_ri_v2_only", "/api/catalog?page=9", "ABSTAIN")
            systemctl("start", unit("scorer"))
            wait(scorer_ready)
            request("shadow_restored", "/api/catalog?page=10")
            atomic_json(
                out,
                {
                    "state": "PASS",
                    "cases": cases,
                    "scorer_crash_recovery": {
                        "old_child": child,
                        "new_child": new_child,
                        "systemd_restarts": 1,
                    },
                    "checkpoint": {"while_stopped": checkpoint, "resumed": resumed},
                    "roll_back": "PASS",
                    "stats": stats(db),
                    "http_scope": "PRIVATE_NGINX_BENIGN_BACKEND",
                },
            )
        finally:
            if nginx and nginx.poll() is None:
                nginx.terminate()
                nginx.wait(timeout=3)
            backend.shutdown()
            backend.server_close()
            thread.join(timeout=3)
            db.close()


class BenignBackendServer(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runtime_config", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    assert not args.output.exists()
    acceptance(json.loads(args.runtime_config.read_text()), args.output)

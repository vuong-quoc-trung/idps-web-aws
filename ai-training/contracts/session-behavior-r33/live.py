"""Owned benign NGINX + backend session probe alongside the existing Local shadow services."""

import argparse
import hashlib
import http.client
import json
import re
import secrets
import signal
import socket
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import numpy as np
import onnx
from history import ORDER, Prefix
from onnx import TensorProto, helper, numpy_helper

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256, load_json
from idps_ai.export.onnx import cpu_session

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "local-shadow-runtime"))
from nginx import render  # noqa: E402

NGINX = REPO_ROOT / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"
TELEMETRY = REPO_ROOT / "security-web/deploy/ai-shadow/telemetry.conf"
PHASES = {
    "ROUTE_HISTORY": slice(0, 4),
    "CADENCE": slice(4, 8),
    "JOINT_HISTORY": slice(0, 8),
}
ROUTES = {"/api/catalog": 1, "/api/topics": 2, "/api/library": 3}


def export_head(frozen, path):
    arm = frozen["selected"]
    params = frozen["arms"][arm]["model"]
    mean, scale, coef = (np.array(params[k]) for k in ("mean", "scale", "coef"))
    w = np.zeros(8)
    w[PHASES[arm]] = coef / scale
    bias = params["intercept"] - mean @ (coef / scale)
    init = [
        numpy_helper.from_array(w.astype("float32").reshape(8, 1), "w"),
        numpy_helper.from_array(np.array([bias], dtype="float32"), "b"),
    ]
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["input", "w"], ["dot"]),
            helper.make_node("Add", ["dot", "b"], ["logit"]),
            helper.make_node("Sigmoid", ["logit"], ["score"]),
        ],
        "r33-private-navigation-head",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [None, 8])],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, [None, 1])],
        init,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=8)
    onnx.checker.check_model(model)
    path.write_bytes(model.SerializeToString())
    return params, PHASES[arm]


class Client(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=2)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.sock.connect(str(self.path))


def run_lab(run):
    frozen = load_json(run / "reconciled/frozen.json")
    path = run / "session-head.onnx"
    if (run / "live.json").exists():
        raise ValueError("completed live evidence already exists")
    if path.exists():
        with tempfile.TemporaryDirectory() as check:
            check_path = Path(check) / "replay.onnx"
            params, cols = export_head(frozen, check_path)
            if file_sha256(path) != file_sha256(check_path):
                raise ValueError("checkpoint export mismatch")
    else:
        params, cols = export_head(frozen, path)
    pin = file_sha256(path)
    model = cpu_session(path, 1)
    records, sessions = {}, {}
    config = load_json(Path.home() / ".local/state/idps-r22-local/runtime.json")

    # This backend is only reachable through a socket under the worker's 0700 directory.
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            arrived = time.monotonic_ns()
            rid = self.headers.get("X-IDPS-Request-Id", "")
            if not re.fullmatch("[0-9a-f]{32}", rid) or rid in records:
                self.send_error(400)
                return
            cookie = self.headers.get("Cookie", "")
            grant = None
            if self.path == "/api/start" and not cookie and len(sessions) < 2:
                grant = "r33=" + secrets.token_urlsafe(32)
                sessions[grant] = Prefix()
                vector, reason = None, "SESSION_ISSUED"
            elif cookie not in sessions:
                vector, reason = None, "SESSION_UNBOUND"
            elif self.path in ROUTES:
                vector, reason = sessions[cookie].observe(
                    arrived // 1_000_000_000, ROUTES[self.path]
                )
            else:
                self.send_error(404)
                return
            ready = time.monotonic_ns()
            score, error = None, None
            if vector is not None:
                x = np.asarray([vector], dtype=np.float32)
                score = float(model.run(["score"], {"input": x})[0][0, 0])
                z = ((x[0, cols] - params["mean"]) / params["scale"]) @ params["coef"] + params[
                    "intercept"
                ]
                error = abs(score - float(1 / (1 + np.exp(-z))))
            done = time.monotonic_ns()
            records[rid] = {
                "arrived_ns": arrived,
                "projected_ns": ready,
                "available_ns": done,
                "history": vector,
                "reason": reason,
                "score": score,
                "onnx_python_error": error,
            }
            self.send_response(200)
            if grant:
                self.send_header("Set-Cookie", grant + "; HttpOnly; SameSite=Strict; Path=/")
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"ok\n")

    with tempfile.TemporaryDirectory(prefix="idps-r33-") as tmp:
        root = Path(tmp)
        back, edge = root / "back.sock", root / "edge.sock"
        render(root, Path(config["mirror_socket"]))
        conf = root / "nginx.conf"
        conf.write_text(f"""pid {root}/pid;
            error_log /dev/null crit;
            events {{ worker_connections 32; }}
            http {{ client_body_temp_path {root}/body; proxy_temp_path {root}/proxy;
            fastcgi_temp_path {root}/fastcgi; uwsgi_temp_path {root}/uwsgi; scgi_temp_path {root}/scgi;
            include {TELEMETRY};
            server {{ listen unix:{edge};
            include {root}/r22-server.conf;
            access_log syslog:server=unix:{config["ri_socket"]},tag=ai_shadow,severity=info pbl4_ai_telemetry if=$pbl4_ai_api;
            location /api/ {{ include {root}/r22-proxy.conf;
            add_header X-IDPS-Request-Id $request_id always; proxy_set_header X-IDPS-Request-Id $request_id;
            proxy_pass http://unix:{back}:; }} }} }}""")
        with socketserver.UnixStreamServer(str(back), Handler) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            proc = None
            try:
                proc = subprocess.Popen(
                    [
                        str(NGINX),
                        "-p",
                        tmp,
                        "-c",
                        str(conf),
                        "-g",
                        "daemon off; master_process off;",
                    ]
                )
                for _ in range(150):
                    if edge.is_socket() or proc.poll() is not None:
                        break
                    time.sleep(0.02)
                if not edge.is_socket():
                    raise RuntimeError("owned NGINX unavailable")
                observations = []

                def get(route, cookie=None):
                    c = Client(edge)
                    start = time.monotonic_ns()
                    try:
                        c.request("GET", route, headers={"Cookie": cookie} if cookie else {})
                        response = c.getresponse()
                        rid = response.getheader("X-IDPS-Request-Id")
                        token = response.getheader("Set-Cookie", "").partition(";")[0]
                        if (
                            response.status != 200
                            or response.read() != b"ok\n"
                            or rid not in records
                        ):
                            raise RuntimeError("response or edge binding failure")
                    finally:
                        c.close()
                    end = time.monotonic_ns()
                    row = dict(
                        records[rid], request_id=rid, sent_ns=start, http_ms=(end - start) / 1e6
                    )
                    if (
                        not start
                        <= row["arrived_ns"]
                        <= row["projected_ns"]
                        <= row["available_ns"]
                        <= end
                    ):
                        raise ValueError("causal order failure")
                    row["within_cutoff"] = row["available_ns"] - start <= 999_000_000
                    observations.append(row)
                    return token

                cookies = [get("/api/start"), get("/api/start")]
                if not all(cookies) or len(set(cookies)) != 2:
                    raise ValueError("invalid separate session grants")
                get("/api/catalog")
                schedules = [[1, 1, 1, 1, 1, 1, 2, 1], [2, 3, 2, 1, 3, 1, 2, 1]]
                routes = {v: k for k, v in ROUTES.items()}
                for j in range(8):
                    if j:
                        time.sleep(1.05)
                    for i, schedule in enumerate(schedules):
                        get(routes[schedule[j]], cookies[i])
                if set(records) != set(r["request_id"] for r in observations) or len(records) != 19:
                    raise ValueError("receipt mismatch")
                deadline = time.monotonic() + 12
                with sqlite3.connect(
                    (Path(config["state"]) / "evidence.sqlite").as_uri() + "?mode=ro", uri=True
                ) as watch:
                    while not all(
                        watch.execute(
                            "SELECT 1 FROM evidence WHERE rid=?", (r["request_id"],)
                        ).fetchone()
                        for r in observations
                    ):
                        if time.monotonic() >= deadline:
                            raise TimeoutError("awaiting real evidence commits")
                        time.sleep(0.05)
            finally:
                if proc:
                    proc.send_signal(signal.SIGQUIT)
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                server.shutdown()
                thread.join(timeout=2)
    # Verify actual RI v2 and R20 committed rows with the same edge-issued ID.
    dburi = (Path(config["state"]) / "evidence.sqlite").as_uri() + "?mode=ro"
    with sqlite3.connect(dburi, uri=True, timeout=1) as db:
        until = time.monotonic() + 12
        for row in observations:
            while True:
                record = db.execute(
                    "SELECT payload,sha256 FROM evidence WHERE rid=?", (row["request_id"],)
                ).fetchone()
                if record:
                    break
                if time.monotonic() >= until:
                    raise TimeoutError("persistent evidence join")
                time.sleep(0.05)
            raw, digest = record
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("receipt SHA")
            value = json.loads(raw)
            if value["request_id"] != row["request_id"]:
                raise ValueError("identity mismatch")
            row.update(
                r20=value["r20"]["status"],
                ri=value["ri_v2"]["status"],
                uri76_sha=value["uri76_sha256"],
                mask=value["source_mask_at_cutoff"],
                evidence_sha=digest,
            )
    eligible = [r for r in observations if r["score"] is not None]
    atomic_json(run / ("live-readback-" + str(time.monotonic_ns()) + ".json"), observations)
    if not (
        len(eligible) == 6
        and all(r["within_cutoff"] and r["ri"] == r["r20"] == "SCORED" for r in observations)
        and max(r["onnx_python_error"] for r in eligible) < 2e-6
        and eligible[0]["uri76_sha"] == eligible[1]["uri76_sha"]
        and eligible[0]["history"] != eligible[1]["history"]
        and not Path(tmp).exists()
        and not thread.is_alive()
    ):
        raise ValueError("live acceptance failed")
    atomic_json(
        run / "live.json",
        {
            "schema": frozen["schema"],
            "order": ORDER,
            "checkpoint_sha": file_sha256(run / "reconciled/frozen.json"),
            "onnx_sha": pin,
            "nginx_sha": file_sha256(NGINX),
            "evidence": observations,
            "owned_resources_clean": True,
            "kind": "two benign controlled Local lab sessions; no attack labels or canonical samples",
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    run_lab(p.parse_args().run)

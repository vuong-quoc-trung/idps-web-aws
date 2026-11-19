"""Measure benign HTTP field availability on an owned Unix edge alongside RI v2 and R20."""

import hashlib
import json
import re
import signal
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import joblib
import numpy as np
from field_schema import FEATURES, WIDTH, project

from idps_ai.common import atomic_json, file_sha256, load_json
from idps_ai.features.request_time import from_request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "session-behavior-r33"))
from live import NGINX, TELEMETRY, Client, render  # noqa: E402

TARGET = "/api/catalog?page=1"
CASES = (
    ("application/json", b'{"quantity":2}'),
    ("application/json", b'{"quantity":"small"}'),
    ("application/json", b'{"tags":["green","blue"]}'),
    ("application/x-www-form-urlencoded", b"quantity=2"),
    ("application/json", b"{}"),
    ("application/octet-stream", b""),
)


def probe(run):
    from http_study import field_probability

    dest = run / "local-readback.json"
    if dest.exists():
        raise ValueError("Local observations already committed")
    meta = load_json(run / "http-pilot-result.json")
    ck = run / "http-pilot/SCHEMA_LR.joblib"
    if file_sha256(ck) != meta["model_shas"]["SCHEMA_LR"]:
        raise ValueError("field head checkpoint changed")
    head = joblib.load(ck)
    cfg = load_json(Path.home() / ".local/state/idps-r22-local/runtime.json")
    records = {}
    cases = []
    path = (Path(cfg["state"]) / "evidence.sqlite").as_uri() + "?mode=ro"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            arrived = time.monotonic_ns()
            rid = self.headers.get("X-IDPS-Request-Id", "")
            if self.path != TARGET or not re.fullmatch("[a-f0-9]{32}", rid) or rid in records:
                self.send_error(400)
                return
            length = int(self.headers["Content-Length"])
            if not 0 <= length <= 4096:
                self.send_error(413)
                return
            payload = self.rfile.read(length)
            received = time.monotonic_ns()
            mime = self.headers.get_content_type()
            body = (
                payload.decode("ascii")
                if mime in ("application/json", "application/x-www-form-urlencoded")
                else None
            )
            z = np.asarray([project(self.path, body)], dtype=np.uint8)
            p = float(field_probability(z, head)[0])
            ready = time.monotonic_ns()
            records[rid] = {
                "arrived_ns": arrived,
                "received_ns": received,
                "ready_ns": ready,
                "body_supported": bool(z[:, WIDTH:].any()),
                "fields_sha": hashlib.sha256(z.tobytes()).hexdigest(),
                "score": p,
                "projection_inference_ms": (ready - received) / 1e6,
            }
            self.send_response(204)
            self.end_headers()

    with tempfile.TemporaryDirectory(prefix="r34-fields-") as tmp:
        root = Path(tmp)
        edge, back = root / "edge.sock", root / "back.sock"
        render(root, Path(cfg["mirror_socket"]))
        conf = root / "nginx.conf"
        conf.write_text(f"""pid {root}/pid;
            error_log /dev/null crit;
            events {{ worker_connections 32; }}
            http {{ client_body_temp_path {root}/body; proxy_temp_path {root}/proxy;
            fastcgi_temp_path {root}/fastcgi; uwsgi_temp_path {root}/uwsgi; scgi_temp_path {root}/scgi;
            include {TELEMETRY};
            server {{ listen unix:{edge};
            include {root}/r22-server.conf;
            access_log syslog:server=unix:{cfg["ri_socket"]},tag=ai_shadow,severity=info pbl4_ai_telemetry if=$pbl4_ai_api;
            location /api/ {{ include {root}/r22-proxy.conf;
            add_header X-IDPS-Request-Id $request_id always; proxy_set_header X-IDPS-Request-Id $request_id;
            proxy_pass http://unix:{back}:; }} }} }}""")
        with (
            socketserver.UnixStreamServer(str(back), Handler) as server,
            sqlite3.connect(path, uri=True) as db,
        ):
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
                until = time.monotonic() + 3
                while not edge.is_socket():
                    if proc.poll() is not None or time.monotonic() >= until:
                        raise RuntimeError("private edge failed to start")
                    time.sleep(0.02)
                for mime, body in CASES:
                    conn = Client(edge)
                    start = time.monotonic_ns()
                    try:
                        conn.request("POST", TARGET, body=body, headers={"Content-Type": mime})
                        response = conn.getresponse()
                        rid = response.getheader("X-IDPS-Request-Id")
                        if response.status != 204 or response.read() or rid not in records:
                            raise RuntimeError("HTTP response or trusted identity mismatch")
                    finally:
                        conn.close()
                    end = time.monotonic_ns()
                    row = records[rid]
                    if (
                        not start
                        <= row["arrived_ns"]
                        <= row["received_ns"]
                        <= row["ready_ns"]
                        <= end
                    ):
                        raise ValueError("causal order violation")
                    cases.append(
                        dict(
                            row,
                            rid=rid,
                            dispatch_ns=start,
                            http_ms=(end - start) / 1e6,
                            before_cutoff=row["ready_ns"] - start <= 999_000_000,
                        )
                    )
                until = time.monotonic() + 12
                for row in cases:
                    while True:
                        saved = db.execute(
                            "SELECT payload,sha256 FROM evidence WHERE rid=?", (row["rid"],)
                        ).fetchone()
                        if saved:
                            break
                        if time.monotonic() >= until:
                            raise TimeoutError("waiting for matching Local receipts")
                        time.sleep(0.05)
                    raw, digest = saved
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("collector digest changed")
                    item = json.loads(raw)
                    if item["request_id"] != row["rid"]:
                        raise ValueError("collector identity mismatch")
                    row.update(
                        uri76_sha=item["uri76_sha256"],
                        ri=item["ri_v2"]["status"],
                        r20=item["r20"]["status"],
                        mask=item["source_mask_at_cutoff"],
                        receipt_sha=digest,
                    )
            finally:
                if proc and proc.poll() is None:
                    proc.send_signal(signal.SIGQUIT)
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                server.shutdown()
                thread.join(timeout=2)
    expected = hashlib.sha256(
        np.asarray(from_request(TARGET, "POST"), dtype="<f4").tobytes()
    ).hexdigest()
    atomic_json(run / "local-observations.json", cases)
    passed = (
        len(records) == len(cases) == len(CASES)
        and len({r["rid"] for r in cases}) == len(CASES)
        and all(
            r["uri76_sha"] == expected and r["ri"] == r["r20"] == "SCORED" and r["before_cutoff"]
            for r in cases
        )
        and [r["body_supported"] for r in cases] == [True, True, True, True, False, False]
        and cases[0]["fields_sha"] == cases[3]["fields_sha"] != cases[1]["fields_sha"]
        and len({r["fields_sha"] for r in cases}) >= 4
        and not root.exists()
        and not thread.is_alive()
    )
    atomic_json(
        dest,
        {
            "pass": passed,
            "requests": len(cases),
            "distinct_URI76": len({r["uri76_sha"] for r in cases}),
            "distinct_schema": len({r["fields_sha"] for r in cases}),
            "schema_fields": len(FEATURES),
            "observations_sha": file_sha256(run / "local-observations.json"),
            "head_sha": file_sha256(ck),
            "within_cutoff": sum(r["before_cutoff"] for r in cases),
            "p50_p95_http_ms": np.percentile([r["http_ms"] for r in cases], [50, 95]).tolist(),
            "p50_p95_projection_inference_ms": np.percentile(
                [r["projection_inference_ms"] for r in cases], [50, 95]
            ).tolist(),
            "resources_clean": not root.exists() and not thread.is_alive(),
            "use": "owned benign HTTP, backend field projection only; no native training labels",
        },
    )
    if not passed:
        raise ValueError("benign Local acceptance incomplete")


if __name__ == "__main__":
    probe(Path(sys.argv[1]))

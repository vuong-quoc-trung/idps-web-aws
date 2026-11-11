#!/usr/bin/env python3
"""Actual disposable veth-client → Nginx/Suricata/AI → Rust → nft response proof.

No host firewall commands. Namespace mode is entered only via unshare -Urn.
Uses the existing narrow actuator, authenticated approval and response queue.
"""

import argparse
import hashlib
import hmac
import http.cookiejar
import importlib.util
import json
import os
import select
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNTIME = Path(
    os.environ.get("IDPS_DEMO_RUNTIME", REPO / ".local-dev/hybrid-v1")
).resolve()


def load(p):
    return json.loads(Path(p).read_text())


def atomic(p, v):
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    t = p.with_suffix(".writing")
    t.write_text(json.dumps(v, indent=2))
    t.replace(p)


def cmd(args, **kw):
    return subprocess.run(args, check=True, capture_output=True, timeout=15, **kw)


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), REPO / "scripts" / name
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def verified_sensor_row(page, rid):
    row = next(v for v in page["detectors"] if v.get("request_id") == rid)
    assert (
        row["correlation"]["status"] == "MATCHED"
        and row["correlation"]["late_event"] is False
    )
    assert any(
        v["source"] == "SURICATA" and v["basis"] == "SENSOR_TRANSACTION"
        for v in row["rules"]
    ), "No genuine transaction-bound Suricata alert"
    assert (
        row["request_ai"]["status"] == "SCORED"
        and row["request_ai"]["request_id"] == rid
    )
    assert all(v.get("id") is not None for v in row["rules"])
    return row


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        target = self.server.target
        upstream = socket.socket(
            socket.AF_UNIX if isinstance(target, str) else socket.AF_INET,
            socket.SOCK_STREAM,
        )
        try:
            upstream.settimeout(10)
            upstream.connect(target)
            peers = (self.request, upstream)
            while True:
                ready, _, _ = select.select(peers, [], [], 15)
                if not ready:
                    return
                for src in ready:
                    data = src.recv(65536)
                    if not data:
                        return
                    peers[1 if src is peers[0] else 0].sendall(data)
        except (OSError, TimeoutError):
            pass
        finally:
            upstream.close()


class TCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Unix(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def server(kind, address, handler, target=None):
    s = kind(address, handler)
    s.target = target
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def client():
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    base = "http://10.203.17.1:18880"
    csrf = {}
    print(json.dumps({"pid": os.getpid(), "ready": True}), flush=True)
    for line in sys.stdin:
        data = json.loads(line)
        operation = data["op"]
        status = None
        rid = None
        try:
            request = base + "/api/auth/csrf" + data.get("query", "")
            if operation in ["login", "bad-login"]:
                with opener.open(base + "/api/auth/csrf", timeout=10) as r:
                    csrf = json.load(r)
                secret = load(RUNTIME / "credentials.json")
                body = urllib.parse.urlencode(
                    {
                        "username": "foundation-admin",
                        "password": secret["student_admin_password"]
                        if operation == "login"
                        else "intentionally-invalid-lab-value",
                    }
                ).encode()
                request = urllib.request.Request(
                    base + "/api/auth/login",
                    data=body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        csrf["headerName"]: csrf["token"],
                    },
                )
            with opener.open(request, timeout=data.get("timeout", 10)) as r:
                status = r.status
                rid = r.headers.get("X-Request-Id")
                r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            rid = e.headers.get("X-Request-Id")
            e.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        print(
            json.dumps({"op": operation, "HTTP": status, "request_id": rid}), flush=True
        )


def namespace(root, operator_approved=False):
    from idps_ai.data.sensor_decode import redact_eve

    sys.path.insert(0, str(REPO / "scripts"))
    from three_source_core import Correlator, identity, response_id

    assert Path("/proc/self/uid_map").read_text().split()[1] != "0"
    cmd(["ip", "link", "set", "lo", "up"])
    cmd(["ip", "link", "add", "labserver", "type", "veth", "peer", "name", "labclient"])
    cmd(["ip", "addr", "add", "10.203.17.1/30", "dev", "labserver"])
    cmd(["ip", "link", "set", "labserver", "up"])
    child = subprocess.Popen(
        [
            "unshare",
            "-n",
            sys.executable,
            str(Path(__file__)),
            "--mode",
            "client",
            "--root",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=(root / "client.log").open("ab"),
        text=True,
    )
    ready = json.loads(child.stdout.readline())
    assert ready["ready"]
    cmd(["ip", "link", "set", "labclient", "netns", str(ready["pid"])])
    for args in [
        ["link", "set", "lo", "up"],
        ["addr", "add", "10.203.17.2/30", "dev", "labclient"],
        ["link", "set", "labclient", "up"],
    ]:
        cmd(["nsenter", "-t", str(ready["pid"]), "-n", "ip", *args])
    cmd(["nft", "-f", str(REPO / "security-web/scripts/pbl4.nft")])
    resources = []
    processes = []
    stop = threading.Event()
    lock = threading.Lock()
    resources.append(server(TCP, ("127.0.0.1", 55434), Relay, str(root / "db.sock")))
    resources.append(server(Unix, str(root / "api.sock"), Relay, ("127.0.0.1", 13011)))
    secret = load(RUNTIME / "credentials.json")
    env = os.environ | {
        "DATABASE_URL": f"postgres://postgres:{secret['security_db_password']}@127.0.0.1:55434/security_db",
        "APP_ADDR": "127.0.0.1:13011",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD_HASH": secret["security_admin_hash"],
        "VIEWER_PASSWORD_HASH": "",
        "SURICATA_EVE_PATH": str(RUNTIME / "suricata/eve.json"),
        "NGINX_ACCESS_PATH": str(RUNTIME / "nginx/access.log"),
        "STUDENT_AUDIT_LOG_PATH": str(RUNTIME / "student-audit/student-audit.log"),
        "AI_SHADOW_RESULTS_PATH": str(RUNTIME / "ai/results.jsonl"),
        "THREE_SOURCE_RESULTS_PATH": str(RUNTIME / "correlation/results.jsonl"),
        "ENFORCEMENT_MODE": "MANUAL",
        "AUTO_BLOCK": "false",
        "COLLECT_ALL_EVENTS": "true",
        "PBL4_FIREWALL_CMD": str(REPO / "security-web/scripts/pbl4-firewall-policy.py"),
        "PBL4_DISPOSABLE_NAMESPACE_RESPONSE": "true",
        "ENFORCE_ALLOWED_SUBNETS": "10.203.17.0/30",
        "WEB_SERVER_IP": "10.203.17.1",
        "PROTECTED_GATEWAY_IP": "10.203.17.1",
        "HYBRID_POLICY_JSON": json.dumps({"approved_clients": ["10.203.17.2"]}),
    }
    backend = subprocess.Popen(
        [str(REPO / "security-web/target/debug/pbl4-security-demo")],
        cwd=REPO / "security-web",
        env=env,
        stdout=(root / "backend.log").open("ab"),
        stderr=subprocess.STDOUT,
    )
    processes.append(backend)
    l = module("dev-up-and-verify.py")
    l.RUNTIME = RUNTIME
    snippet = (
        (REPO / "security-web/nginx/pbl4-proxy.conf")
        .read_text()
        .replace("listen 0.0.0.0:80;", "listen 10.203.17.1:18880;")
        .replace(
            "server 127.0.0.1:8080 max_fails=1 fail_timeout=5s;",
            f"server unix:{root}/app.sock;",
        )
        .replace("    server 192.168.20.10:80 backup;\n", "")
        .replace("/var/log/nginx/access.log", str(RUNTIME / "nginx/access.log"))
    )
    snippet = l.ai_shadow_nginx(snippet, RUNTIME / "ai/nginx.sock")
    temp_paths = " ".join(f"{name}_temp_path {root}/{name};" for name in ["client_body", "proxy", "fastcgi", "uwsgi", "scgi"])
    (root / "nginx.conf").write_text(
        f"user root root; error_log {root}/nginx.log; pid {root}/nginx.pid; events {{}} http {{ {temp_paths} {snippet} }}"
    )
    nginx = str(REPO / ".local-dev/foundation/tools/runtime/usr/sbin/nginx")
    with (root / "nginx-config-test.log").open("ab") as log:
        subprocess.run([nginx, "-t", "-p", str(root), "-c", str(root / "nginx.conf")], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=15)
    processes.append(
        subprocess.Popen(
            [
                nginx,
                "-p",
                str(root),
                "-c",
                str(root / "nginx.conf"),
                "-g",
                "daemon off; master_process off;",
            ],
            stdout=(root / "nginx-stdout.log").open("ab"),
            stderr=subprocess.STDOUT,
        )
    )
    sensor_id = uuid.uuid4().hex
    route_key = os.urandom(32)
    corr = Correlator(sensor_id, route_key)

    def append(path, value):
        with path.open("a") as f:
            f.write(json.dumps(value) + "\n")

    class Eve(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                raw = json.loads(line)
                safe = redact_eve(raw, query_numeric=True, query_version=2)
                if isinstance(raw.get("tx_id"), int):
                    safe["tx_id"] = raw["tx_id"]
                safe["sensor_instance"] = sensor_id
                if raw.get("event_type") == "http" and isinstance(
                    raw.get("http", {}).get("url"), str
                ):
                    safe["http"]["path_fingerprint"] = hmac.new(
                        route_key,
                        urllib.parse.urlsplit(raw["http"]["url"]).path.encode(),
                        hashlib.sha256,
                    ).hexdigest()
                rid = response_id(safe)
                if rid:
                    safe["http"]["request_id"] = rid
                safe["adapter_version"] = "suricata-shadow-1"
                safe["sensor_event_id"] = identity(safe)
                safe["received_at"] = time.time()
                with lock:
                    corr.add("SURICATA", safe, time.time())
                    append(RUNTIME / "suricata/eve.json", safe)

    resources.append(server(Unix, str(root / "eve.sock"), Eve))
    source = module("three-source-shadow.py")
    config = source.sensor_config(root, REPO / ".local-dev/suricata-runtime")
    import yaml

    cfg = yaml.safe_load(config.read_text())
    cfg["vars"]["address-groups"]["HOME_NET"] = "[10.203.17.0/30]"
    cfg["vars"]["port-groups"]["HTTP_PORTS"] = "18880"
    cfg["af-packet"][0]["interface"] = "labserver"
    config.write_text("%YAML 1.1\n---\n" + yaml.safe_dump(cfg))
    sensorenv = os.environ | {
        "LD_LIBRARY_PATH": str(
            REPO / ".local-dev/suricata-runtime/usr/lib/x86_64-linux-gnu"
        )
    }
    sensor = subprocess.Popen(
        [
            str(REPO / ".local-dev/suricata-runtime/usr/bin/suricata"),
            "-c",
            str(config),
            "--runmode",
            "single",
            "-k",
            "none",
            "-i",
            "labserver",
            "-l",
            str(root),
            "--set",
            "detect.profile=low",
            "tcp port 18880",
        ],
        env=sensorenv,
        stdout=(root / "sensor.log").open("ab"),
        stderr=subprocess.STDOUT,
    )
    processes.append(sensor)
    source.wait_engine(sensor, root / "sensor.log", 0)
    offsets = {name: 0 for name in ["NGINX", "STUDENT_AUDIT"]}
    latest = {}

    def correlate():
        paths = {
            "NGINX": RUNTIME / "nginx/access.log",
            "STUDENT_AUDIT": RUNTIME / "student-audit/student-audit.log",
        }
        while not stop.wait(0.2):
            with lock:
                for name, path in paths.items():
                    with path.open("rb") as f:
                        f.seek(offsets[name])
                        while line := f.readline():
                            if not line.endswith(b"\n"):
                                break
                            offsets[name] = f.tell()
                            value = json.loads(line)
                            if (
                                name == "STUDENT_AUDIT"
                                and value.get("event_type") != "http_request"
                            ):
                                continue
                            corr.add(name, value, time.time())
                for rid in list(corr.rows):
                    result = corr.result(rid)
                    fp = identity(result)
                    if latest.get(rid) != fp:
                        result["observed_at"] = time.strftime(
                            "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()
                        )
                        append(RUNTIME / "correlation/results.jsonl", result)
                        latest[rid] = fp

    threading.Thread(target=correlate, daemon=True).start()

    def api(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(
            "http://127.0.0.1:13011" + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)

    def rpc(op, **kw):
        child.stdin.write(json.dumps({"op": op, **kw}) + "\n")
        child.stdin.flush()
        return json.loads(child.stdout.readline())

    def wait(call, predicate, seconds=90):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                v = call()
                if predicate(v):
                    return v
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(0.5)
        raise RuntimeError("Native lab condition deadline")

    proofs = {}
    try:
        wait(lambda: api("/health"), lambda x: True)
        if processes[1].poll() is not None:
            raise RuntimeError(f"Namespace NGINX exited rc={processes[1].returncode}; inspect {root / 'nginx-stdout.log'}")
        token = api(
            "/api/auth/login",
            {"username": "admin", "password": secret["security_admin_password"]},
        )["token"]
        secret.clear()
        proofs["normal_get"] = rpc("get")
        assert proofs["normal_get"]["HTTP"] == 200, f"Native HTTP GET failed: {proofs['normal_get']}; inspect nginx-stdout.log, nginx.log, client.log"
        proofs["normal_post"] = rpc("login")
        assert proofs["normal_post"]["HTTP"] == 204
        for name in ["normal_get", "normal_post"]:
            rid = proofs[name]["request_id"]
            page = wait(
                lambda rid=rid: api(
                    "/api/hybrid-incidents?request_id=" + rid, token=token
                ),
                lambda x: (
                    bool(x["incidents"])
                    and x["incidents"][0]["ai"]["status"] == "SCORED"
                ),
            )
            assert page["incidents"][0]["policy_action"] != "PROPOSE_BLOCK"
            proofs[name + "_policy"] = page["incidents"][0]
        review_receipt = rpc(
            "get", query="?" + urllib.parse.urlencode({"search": "1' OR 1=1--"})
        )
        review_page = wait(
            lambda: api(
                "/api/hybrid-incidents?request_id=" + review_receipt["request_id"],
                token=token,
            ),
            lambda x: (
                bool(x["incidents"])
                and x["incidents"][0]["ai_risk_component"] > 0
                and x["incidents"][0]["rule_risk_component"] > 0
            ),
        )
        assert review_page["incidents"][0]["policy_action"] == "REVIEW"
        proofs["real_review"] = {
            "receipt": review_receipt,
            "decision": review_page["incidents"][0],
        }
        failures = [rpc("bad-login") for _ in range(3)]
        assert all(v["HTTP"] in [401, 403] for v in failures)
        proofs["application_denials"] = failures

        def propose():
            receipt = rpc(
                "get", query="?" + urllib.parse.urlencode({"search": "1' OR 1=1--"})
            )
            assert receipt["HTTP"] == 200
            rid = receipt["request_id"]
            page = wait(
                lambda: api("/api/hybrid-incidents?request_id=" + rid, token=token),
                lambda x: (
                    bool(x["incidents"])
                    and x["incidents"][0]["policy_action"] == "PROPOSE_BLOCK"
                ),
            )
            decision = page["incidents"][0]
            p = next(
                v
                for v in page["proposals"]
                if v["request_id"] == rid and v["status"] == "PENDING"
            )
            assert (
                decision["trusted_client_ip"] == "10.203.17.2"
                and decision["rule_risk_component"] >= 70
                and decision["ai_risk_component"] > 0
            )
            # Get actual detector evidence; an NGINX-only rule is insufficient
            # for the Suricata + AI correlated-incident acceptance claim.
            return receipt, decision, p

        receipt, decision, p = propose()
        proofs["rule_ai_incident"] = {
            "receipt": receipt,
            "decision": decision,
            "proposal": p,
        }
        detector_page = wait(
            lambda: api(
                "/api/ai-shadow?request_id=" + receipt["request_id"], token=token
            ),
            lambda x: any(
                any(
                    v["source"] == "SURICATA" and v["basis"] == "SENSOR_TRANSACTION"
                    for v in row["rules"]
                )
                for row in x["detectors"]
            ),
        )
        proofs["detector_view"] = detector_page
        # Verify raw detector API shape below; never create synthetic sensor rules.
        verified_sensor_row(detector_page, receipt["request_id"])
        # A protected-server API rejection is not a real block action.
        try:
            api(
                "/api/blocked-ips",
                {"ip": "10.203.17.1", "reason": "must refuse protected server"},
                token,
            )
        except urllib.error.HTTPError as e:
            assert e.code in [400, 403]
        else:
            raise AssertionError("Protected server accepted")
        proofs["protected_ip_refused"] = True
        if not operator_approved:
            atomic(
                root / "result.json",
                {
                    "state": "PASS",
                    "REAL_RULE_AI_CORRELATION": "PASS",
                    "PROPOSE_BLOCK": "PASS",
                    "HYBRID_POLICY": "PASS",
                    "MANUAL_BLOCK": "PENDING_APPROVAL",
                    "UNBLOCK_TTL": "PENDING_APPROVAL",
                    "operator_approval": False,
                    "namespace_only": True,
                    "host_firewall_touched": False,
                    "proofs": proofs,
                },
            )
            return
        approved = api(
            f"/api/hybrid-proposals/{p['id']}/approve",
            {"ttl_seconds": 15, "decision_fingerprint": decision["fingerprint"]},
            token,
        )
        wait(
            lambda: api("/api/audit", token=token),
            lambda rows: any(
                v["id"] == approved["action_id"] and v["status"] == "SUCCESS"
                for v in rows
            ),
        )
        state = api("/api/blocked-ips", token=token)
        assert "10.203.17.2" in state["kernel"] and state["in_sync"]
        proofs["manual_block"] = {"approval": approved, "state": state}
        denied = rpc("get", timeout=1)
        assert denied["HTTP"] is None
        proofs["later_packet_dropped"] = denied
        req = urllib.request.Request(
            "http://127.0.0.1:13011/api/blocked-ips/10.203.17.2",
            method="DELETE",
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            unblock = json.load(r)
        wait(
            lambda: api("/api/blocked-ips", token=token),
            lambda x: "10.203.17.2" not in x["kernel"] and x["in_sync"],
        )
        assert rpc("get")["HTTP"] == 200
        proofs["manual_unblock"] = unblock
        # The central response cooldown is deliberately honored, never disabled.
        time.sleep(31)
        receipt, decision, p = propose()
        approved = api(
            f"/api/hybrid-proposals/{p['id']}/approve",
            {"ttl_seconds": 4, "decision_fingerprint": decision["fingerprint"]},
            token,
        )
        wait(
            lambda: api("/api/audit", token=token),
            lambda rows: any(
                v["id"] == approved["action_id"] and v["status"] == "SUCCESS"
                for v in rows
            ),
        )
        time.sleep(6)
        expired = wait(
            lambda: api("/api/blocked-ips", token=token),
            lambda x: "10.203.17.2" not in x["kernel"] and x["in_sync"],
        )
        assert rpc("get")["HTTP"] == 200
        proofs["ttl_expiry"] = {"approval": approved, "state": expired}
        try:
            api(
                "/api/blocked-ips",
                {"ip": "10.203.17.1", "reason": "must refuse protected server"},
                token,
            )
        except urllib.error.HTTPError as e:
            assert e.code in [400, 403]
        else:
            raise AssertionError("Protected server accepted")
        proofs["protected_ip_refused"] = True
        atomic(
            root / "result.json",
            {
                "state": "PASS",
                "MANUAL_BLOCK": "PASS",
                "UNBLOCK_TTL": "PASS",
                "PROPOSE_BLOCK": "PASS",
                "HYBRID_POLICY": "PASS",
                "namespace_only": True,
                "host_firewall_touched": False,
                "proofs": proofs,
            },
        )
    except Exception as exc:
        atomic(
            root / "result.json",
            {
                "state": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc) or f"{type(exc).__name__} without message; inspect namespace.log and saved proofs",
                "proofs": proofs,
                "namespace_only": True,
            },
        )
        raise
    finally:
        stop.set()
        child.terminate()
        child.wait(timeout=5)
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
        for s in resources:
            s.shutdown()
            s.server_close()


def host(root, operator_approved=False):
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    resources = [
        server(Unix, str(root / "app.sock"), Relay, ("127.0.0.1", 8080)),
        server(Unix, str(root / "db.sock"), Relay, ("127.0.0.1", 55434)),
    ]
    try:
        with (root / "namespace.log").open("ab") as log:
            process = subprocess.Popen(
                [
                    "unshare",
                    "-Urn",
                    sys.executable,
                    str(Path(__file__)),
                    "--mode",
                    "namespace",
                    "--root",
                    str(root),
                ]
                + (
                    ["--operator-approved-isolated-client"] if operator_approved else []
                ),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=420)
            finally:
                # Own process group only; also remove descendants if namespace
                # setup or an assertion failed before its local finally block.
                for sig in [signal.SIGTERM, signal.SIGKILL]:
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        break
                    if sig == signal.SIGTERM:
                        time.sleep(0.5)
                process.wait(timeout=5)
        if (
            code
            or not (root / "result.json").exists()
            or load(root / "result.json")["state"] != "PASS"
        ):
            raise RuntimeError(
                "Native namespace hybrid/response proof failed; inspect private namespace log/result"
            )
    finally:
        for s in resources:
            s.shutdown()
            s.server_close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["host", "namespace", "client"], required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument(
        "--operator-approved-isolated-client",
        action="store_true",
        help="Explicit operator authorizes block/unblock of disposable10.203.17.2 only",
    )
    a = p.parse_args()
    os.umask(0o077)
    if a.mode == "host":
        host(a.root.resolve(), a.operator_approved_isolated_client)
    elif a.mode == "namespace":
        namespace(a.root.resolve(), a.operator_approved_isolated_client)
    else:
        client()

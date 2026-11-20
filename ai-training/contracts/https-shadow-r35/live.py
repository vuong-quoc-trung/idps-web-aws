"""Bounded acceptance in a NEW loopback-only netns. Two ordinary TLS requests, private H2."""

import argparse
import base64
import contextlib
import hashlib
import http.client
import importlib.util
import json
import os
import re
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCRIPTS = ROOT / "security-web/scripts"


def load(path):
    s = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return mod


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def eventually(check, child, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return
        need(child.poll() is None, "Component exited before readiness")
        time.sleep(0.025)
    raise RuntimeError("Component readiness deadline")


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
    child.wait(timeout=3)


def jsonlines(path):
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_bytes().splitlines(keepends=True)
        if line.endswith(b"\n")
    ]


def csrf(body, headers):
    obj = json.loads(body)
    token = base64.urlsafe_b64decode(obj["token"])
    already_masked = (
        len(token) == 72
        and uuid.UUID(bytes(a ^ b for a, b in zip(token[:36], token[36:])).decode()).version == 4
    )
    return (
        obj["headerName"] == "X-CSRF-TOKEN"
        and already_masked
        and any(
            c.startswith("JSESSIONID=") and "httponly" in c.lower()
            for c in headers.get_all("Set-Cookie", [])
        )
    )


def main(a, out):
    # Refuse the initial network namespace even when a test is invoked locally by mistake.
    need(
        os.readlink("/proc/self/ns/net") != a.host_netns
        and socket.if_nameindex() == [(1, "lo")]
        and os.geteuid() == 0
        and Path("/proc/self/uid_map").read_text().split()[:2] == ["0", str(a.owner_uid)]
        and a.owner_uid > 0,
        "Requires disposable rootless network namespace",
    )
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    subprocess.run(["ip", "addr", "add", "192.0.2.10/32", "dev", "lo"], check=True)
    a.output.mkdir(mode=0o700, exist_ok=False)
    with (
        (
            contextlib.nullcontext(a.delivery)
            if a.delivery
            else tempfile.TemporaryDirectory(prefix="idps-r35-")
        ) as temporary,
        contextlib.ExitStack() as cleanup,
    ):
        w = Path(temporary)
        if a.delivery:
            need(
                w.is_dir()
                and not w.is_symlink()
                and not (w.stat().st_mode & 0o077)
                and not any(w.iterdir()),
                "Private empty delivery directory required",
            )

        def start(name, cmd, env=None):
            log = cleanup.enter_context((w / (name + ".log")).open("wb"))
            p = subprocess.Popen(
                cmd, cwd=w, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL
            )
            cleanup.callback(stop, p)
            return p

        try:
            socket_path = w / "edge.sock"
            local = a.bundle is None
            r36 = HERE.parent / "https-model-r36"

            def start_receiver(slot=None):
                cmd = [
                    sys.executable,
                    "-B",
                    str(r36 / "serve.py" if local else HERE / "receiver.py"),
                    "--socket",
                    socket_path,
                    "--database",
                    w / "evidence.db",
                    "--ort",
                    a.ort,
                    "--binary",
                    a.scorer,
                    "--lineage",
                    a.output.name,
                ]
                if local:
                    cmd += ["--journal", a.output / "https-research.jsonl"]
                    if slot:
                        cmd += ["--slot", slot]
                else:
                    model_json = json.loads((a.bundle / "manifest.json").read_text())
                    cmd += [
                        "--model",
                        a.bundle / "publisher.onnx",
                        "--model-sha",
                        model_json["model_sha256"],
                    ]
                proc = start("receiver", cmd)
                eventually(socket_path.is_socket, proc, 5)
                return proc

            receiver = start_receiver()
            cert, key = w / "cert.pem", w / "tls.key"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-noenc",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=student.test",
                    "-addext",
                    "subjectAltName=DNS:student.test,IP:127.0.0.1",
                    "-keyout",
                    key,
                    "-out",
                    cert,
                ],
                check=True,
                capture_output=True,
            )
            group = w / "keys"
            group.mkdir()
            os.chown(group, 0, 991)
            group.chmod(0o750)
            secret = {"kid": "r35", "epoch": secrets.token_hex(16), "key": secrets.token_hex(32)}
            keyfile = group / "key.json"
            keyfile.write_text(json.dumps(secret))
            os.chown(keyfile, 0, 991)
            keyfile.chmod(0o640)
            env = os.environ | dict(
                STUDENT_SOURCE_INSTANCE="student-r35",
                STUDENT_AUDIT_LOG_ENABLED="true",
                STUDENT_AUDIT_LOG_PATH=str(w / "audit.jsonl"),
                STUDENT_AUDIT_HMAC_KEY=secrets.token_hex(32),
                AUDIT_INCLUDE_SUCCESSFUL_READS="true",
                AUDIT_RETENTION_ENABLED="false",
            )
            if a.extended:
                env.update(
                    BOOTSTRAP_ADMIN_ENABLED="true",
                    BOOTSTRAP_ADMIN_USERNAME="local-acceptance",
                    BOOTSTRAP_ADMIN_PASSWORD=secrets.token_urlsafe(24),
                )
            java = start(
                "student",
                [
                    "java",
                    "-XX:ActiveProcessorCount=1",
                    "-XX:+UseSerialGC",
                    "-Xms64m",
                    "-Xmx320m",
                    "-Dloader.path=" + str(a.h2),
                    "-cp",
                    a.student,
                    "org.springframework.boot.loader.launch.PropertiesLauncher",
                    "--spring.datasource.url=jdbc:h2:mem:r35;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
                    "--spring.datasource.driver-class-name=org.h2.Driver",
                    "--spring.datasource.username=sa",
                    "--spring.datasource.password=",
                    "--spring.flyway.enabled=false",
                    "--spring.jpa.hibernate.ddl-auto=create-drop",
                    "--spring.jpa.properties.hibernate.default_schema=PUBLIC",
                    "--server.address=127.0.0.1",
                    "--server.port=18081",
                    "--server.tomcat.threads.max=4",
                    "--server.tomcat.threads.min-spare=1",
                ],
                env,
            )
            eventually(
                lambda: b"Started StudentWebApplication" in (w / "student.log").read_bytes(),
                java,
                150,
            )
            site, formats = load(SCRIPTS / "prepare-proof-egress.py").render(
                str(cert),
                str(key),
                str(cert),
                "student.test",
                str(ROOT / "security-web/tests/njs/proof-probe.js"),
                str(keyfile),
                991,
                shadow_socket=str(socket_path),
                edge_ip="127.0.0.1",
                student_ip="127.0.0.3",
            )
            site = site.replace("127.0.0.1:443 ssl", "127.0.0.1:18443 ssl").replace(
                "127.0.0.1:80;", "127.0.0.1:18082;"
            )
            site = site.replace("127.0.0.3:443;", "127.0.0.3:18444;").replace(
                "/var/log/nginx/access.log", str(w / "access")
            )
            site = site.replace(
                "syslog:server=unix:/run/pbl4-ai-shadow/nginx.sock,tag=ai_shadow,nohostname",
                str(w / "ri-input"),
            )
            web = (
                load(ROOT / "student-web/deploy/tls/prepare.py")
                .render(
                    "server { listen 127.0.0.3:18083; location / { proxy_pass http://127.0.0.1:5173; } "
                    "location /api/ { proxy_pass http://127.0.0.1:8080; } }",
                    str(cert),
                    str(key),
                    "127.0.0.3",
                )
                .replace("127.0.0.3:443 ssl", "127.0.0.3:18444 ssl")
                .replace("127.0.0.1:8080;", "127.0.0.1:18081;")
            )
            temps = "\n".join(
                f"{x}_temp_path {w}/{x};"
                for x in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
            )
            conf = w / "nginx.conf"
            conf.write_text(
                f"load_module {a.module};\npid {w}/nginx.pid;\nerror_log {w}/error warn;\n"
                f"events {{}} http {{ access_log off; {temps}\n{formats}\n{site}\n{web}\n}}"
            )
            ngcmd = [str(a.nginx), "-p", str(w), "-e", str(w / "bootstrap"), "-c", str(conf)]
            check = subprocess.run(ngcmd + ["-t"], capture_output=True)
            need(check.returncode == 0, check.stderr.decode()[-1500:])
            nginx = start("nginx", ngcmd + ["-g", "daemon off; master_process off;"])

            def listening():
                with socket.socket() as s:
                    return s.connect_ex(("127.0.0.1", 18443)) == 0

            eventually(listening, nginx, 4)
            config = load(SCRIPTS / "prepare-suricata-post-proxy.py").render(
                yaml.safe_load((ROOT / "security-web/config/suricata/suricata.yaml").read_text()),
                "local-egress",
            )
            config.pop("run-as", None)
            etc = a.sensor_prefix / "etc/suricata"
            config.update(
                {
                    "default-log-dir": str(w),
                    "unix-command": {"enabled": False},
                    "reference-config-file": str(etc / "reference.config"),
                    "classification-file": str(etc / "classification.config"),
                }
            )
            config["outputs"] = [
                {
                    "eve-log": {
                        "enabled": True,
                        "filetype": "regular",
                        "filename": "eve.json",
                        "types": [
                            {"alert": {"payload": False, "packet": False, "http-body": False}},
                            {"http": {"extended": True, "dump-all-headers": "none"}},
                        ],
                    }
                },
                {
                    "lua": {
                        "enabled": True,
                        "scripts-dir": str(ROOT / "security-web/config/suricata"),
                        "scripts": ["transaction-evidence.lua"],
                    }
                },
            ]
            cfg = w / "sensor.yaml"
            cfg.write_text("%YAML 1.1\n---\n" + yaml.safe_dump(config))
            # Passive test instrumentation on an allowed public GET, confined to this sensor.
            rules = w / "isolated.rules"
            rules.write_bytes(
                (ROOT / "security-web/suricata/pbl4.rules").read_bytes()
                + b'\nalert http any any -> any any (msg:"R35 benign CSRF observation"; flow:established,to_server; http.method; content:"GET"; http.uri; content:"/api/auth/csrf"; startswith; endswith; priority:3; sid:9100035; rev:1;)\n'
            )
            cmd, senv = load(SCRIPTS / "run-suricata-generation.py").launch_spec(
                [
                    "-c",
                    str(cfg),
                    "-l",
                    str(w),
                    "-S",
                    str(rules),
                    "--af-packet=lo",
                    "--runmode",
                    "single",
                ]
            )
            cmd[0] = str(a.sensor_prefix / "usr/bin/suricata")
            senv["LD_LIBRARY_PATH"] = str(a.sensor_prefix / "usr/lib/x86_64-linux-gnu")
            sensor = start("sensor", cmd, senv)
            eventually(lambda: b"Engine started" in (w / "sensor.log").read_bytes(), sensor, 20)
            observed = {}
            halt = threading.Event()

            def collect():
                while not halt.is_set():
                    for src, file in (("N", "access"), ("A", "audit.jsonl"), ("E", "eve.json")):
                        for event in jsonlines(w / file):
                            if src == "E" and event.get("event_type") != "http":
                                continue
                            rid = (
                                event.get("request_id")
                                if src != "E"
                                else (event.get("host"), str(event["flow_id"]), event["tx_id"])
                            )
                            if src == "N" and (
                                event.get("source") != "nginx_access"
                                or event.get("schema_version") != "1.0"
                            ):
                                continue
                            if src == "A" and (
                                event.get("source") != "STUDENT_AUDIT"
                                or event.get("source_instance") != "student-r35"
                                or not event.get("event_id")
                            ):
                                continue
                            observed.setdefault((src, rid), time.time_ns())
                    halt.wait(0.004)

            collector = threading.Thread(target=collect, daemon=True)
            collector.start()
            cleanup.callback(collector.join, 2)
            cleanup.callback(halt.set)
            ctx = ssl.create_default_context(cafile=str(cert))
            requests = {}
            roster = [("GET", "/api/auth/csrf", 200), ("GET", "/api/auth/me", 401)]
            if local:
                roster += [
                    ("GET", "/api/auth/csrf?view=compact", 200),
                    ("HEAD", "/api/profile-options", 401),
                    ("POST", "/api/auth/logout", 204),
                    ("GET", "/api/auth/csrf?locale=vi&page=2", 200),
                ]
            auth_headers = {}
            for seq, (method, route, expected) in enumerate(roster):
                if local and seq in (2, 3, 4):
                    stop(receiver)
                    receiver = start_receiver("rollback" if seq == 3 else None)
                c = http.client.HTTPSConnection(
                    "127.0.0.1", 18443, context=ctx, source_address=("192.0.2.10", 0), timeout=10
                )
                with contextlib.closing(c):
                    t = time.monotonic_ns()
                    c.request(
                        method,
                        route,
                        headers=auth_headers
                        if method == "POST"
                        else ({"Cookie": auth_headers["Cookie"]} if local and seq == 5 else {}),
                    )
                    res = c.getresponse()
                    body = res.read(16384)
                    elapsed = (time.monotonic_ns() - t) / 1e6
                    rid = res.getheader("X-Request-Id")
                    need(
                        res.status == expected
                        and rid
                        and rid not in requests
                        and not res.getheader("X-WS-Receipt"),
                        "HTTP identity/status",
                    )
                    if expected == 200:
                        oracle = csrf(body, res.headers)
                        previous_cookie = auth_headers.get("Cookie")
                        auth_headers = {
                            "X-CSRF-TOKEN": json.loads(body)["token"],
                            "Cookie": res.getheader("Set-Cookie").split(";", 1)[0],
                        }
                        if local and seq == 5:
                            oracle = (
                                oracle
                                and previous_cookie is not None
                                and previous_cookie != auth_headers["Cookie"]
                            )
                    elif expected == 204:
                        # Final CSRF GET presents this same cookie and must get a new session.
                        oracle = not body
                    else:
                        oracle = res.status == 401
                    need(oracle, f"Student response contract {seq + 1} {method} {res.status}")
                    requests[rid] = dict(
                        route=route,
                        method=method,
                        status=res.status,
                        oracle="CSRF_CONTENT_SESSION"
                        if expected == 200
                        else ("SESSION_LOGOUT" if expected == 204 else "ANONYMOUS_AUTH_CHALLENGE"),
                        http_ms=round(elapsed, 3),
                    )

            extended = {}
            if a.extended:
                from extended_https import exercise

                def restart_sensor():
                    nonlocal sensor
                    begin = time.monotonic()
                    launch = load(SCRIPTS / "run-suricata-generation.py")
                    fresh, variables = launch.launch_spec(cmd[1:-2])
                    fresh[0] = cmd[0]
                    variables["LD_LIBRARY_PATH"] = senv["LD_LIBRARY_PATH"]
                    sensor = start("sensor-recovery", fresh, variables)
                    eventually(
                        lambda: b"Engine started" in (w / "sensor-recovery.log").read_bytes(),
                        sensor,
                        20,
                    )
                    engine_ms = round((time.monotonic() - begin) * 1000, 3)
                    flow = load(SCRIPTS / "proof-flow-readiness.py")
                    # No requests are dispatched in this planned rotation window. A
                    # sensor starting mid-stream did not see the original TCP handshake.
                    drain = flow.wait_for_rotation(flow.current(), 5)
                    return dict(
                        sensor_engine_ms=engine_ms,
                        **drain,
                        sensor_ready_ms=round((time.monotonic() - begin) * 1000, 3),
                    )

                extended = exercise(
                    ctx,
                    requests,
                    env["BOOTSTRAP_ADMIN_USERNAME"],
                    env["BOOTSTRAP_ADMIN_PASSWORD"],
                    lambda: stop(sensor),
                    restart_sensor,
                )
                roster = list(requests)
            expected_sensor = len(roster) - int(a.extended)

            def complete():
                return (
                    all(("N", rid) in observed and ("A", rid) in observed for rid in requests)
                    and len(
                        {r.get("request_id") for r in jsonlines(w / "ri-input")} & requests.keys()
                    )
                    == len(roster)
                    and len([key for key in observed if key[0] == "E"]) >= expected_sensor
                    and len(jsonlines(w / "audit.jsonl")) >= len(roster)
                    and len([e for e in jsonlines(w / "eve.json") if e.get("event_type") == "http"])
                    >= expected_sensor
                    and (w / "chain.tsv").exists()
                    and len((w / "chain.tsv").read_text().splitlines()) >= expected_sensor
                )

            try:
                eventually(complete, sensor, 8 if a.extended else 20)
            except RuntimeError:
                if a.extended:

                    def ids(name):
                        return {r.get("request_id") for r in jsonlines(w / name)}

                    counts = dict(
                        total=len(requests),
                        access=len(ids("access")),
                        audit=len(ids("audit.jsonl")),
                        ri=len(ids("ri-input")),
                        eve=len(
                            [r for r in jsonlines(w / "eve.json") if r.get("event_type") == "http"]
                        ),
                        missing_audit=[
                            v["oracle"] for k, v in requests.items() if k not in ids("audit.jsonl")
                        ],
                        missing_edge=[
                            v["oracle"] for k, v in requests.items() if k not in ids("access")
                        ],
                        chain_by_generation={},
                        expected_sensor=expected_sensor,
                    )
                    for line in (w / "chain.tsv").read_text().splitlines():
                        gen = line.rsplit("\t", 1)[-1]
                        if re.fullmatch(r"[0-9a-f]{32}", gen):
                            counts["chain_by_generation"][gen] = (
                                counts["chain_by_generation"].get(gen, 0) + 1
                            )
                    (a.output / "readiness-diagnosis.json").write_text(json.dumps(counts, indent=2))
                if not (
                    a.extended
                    and counts["access"] == counts["audit"] == counts["ri"] == len(roster)
                    and len(counts["chain_by_generation"]) == 2
                ):
                    raise
            halt.set()
            collector.join(2)
            eve = {
                (e.get("host"), str(e["flow_id"]), e["tx_id"]): e
                for e in jsonlines(w / "eve.json")
                if e.get("event_type") == "http"
            }
            audit = {e["request_id"]: e for e in jsonlines(w / "audit.jsonl")}
            edges = {e["request_id"]: e for e in jsonlines(w / "access")}
            ri = {e["request_id"]: e for e in jsonlines(w / "ri-input")}
            with contextlib.closing(sqlite3.connect(w / "evidence.db")) as db:
                records = {
                    r: json.loads(j)
                    for r, j in db.execute(
                        "SELECT request_id,data FROM receipts WHERE conflicted=0"
                    )
                }
            seen_transactions = set()
            seen_sensor_ids = set()
            proofrows = []
            observations = []
            for line in (w / "chain.tsv").read_text().splitlines():
                flow, tx, proof, receipt, client, rid, scheme, host, generation = line.split("\t")
                key = ("ws-generation-" + generation, flow, int(tx))
                need(key not in seen_transactions, "Duplicate native transaction")
                seen_transactions.add(key)
                e = eve[key]
                if a.extended and not rid and not proof and not receipt:
                    continue
                need(
                    rid not in seen_sensor_ids and rid in requests,
                    "Unexpected or ambiguous sensor identity",
                )
                seen_sensor_ids.add(rid)
                row = requests[rid]
                need("tx" not in row, "Duplicate transaction for request")
                need(
                    e["host"] == "ws-generation-" + generation
                    and e["in_iface"] == "lo"
                    and e["src_ip"] == "127.77.0.1"
                    and e["dest_ip"] == "127.77.0.2"
                    and e["dest_port"] == 18080
                    and scheme == "https"
                    and client == "192.0.2.10",
                    "Sensor scope",
                )
                if a.extended and (not receipt or e["http"].get("status") is None):
                    row["sensor_absence"] = "incomplete_sensor_response"
                    continue
                need(
                    e["http"]["url"] == row["route"]
                    and e["http"]["status"] == row["status"]
                    and e["http"]["http_method"] == row["method"],
                    "Transaction outcome",
                )
                need(
                    audit[rid]["source_instance"] == "student-r35"
                    and audit[rid]["status_code"] == row["status"]
                    and uuid.UUID(audit[rid]["event_id"])
                    and edges[rid]["status"] == row["status"]
                    and ri[rid]["schema_version"] == "nginx-ai-1",
                    "Edge/Audit mismatch",
                )
                k = dict(flow_id=flow, tx_id=int(tx), generation=generation)
                proofrows.append(dict(tx=k, proof=proof, receipt=receipt))
                observations.append(
                    dict(
                        tx=k,
                        client=client,
                        request_id=rid,
                        scheme=scheme,
                        host=host,
                        method=row["method"],
                        target_sha256=hashlib.sha256(row["route"].encode()).hexdigest(),
                        observed_ms=int(datetime.fromisoformat(e["timestamp"]).timestamp() * 1000),
                        response_complete=True,
                    )
                )
                alerts = [
                    v
                    for v in jsonlines(w / "eve.json")
                    if v.get("event_type") == "alert"
                    and v.get("host") == "ws-generation-" + generation
                    and (v.get("host"), str(v.get("flow_id")), v.get("tx_id")) == key
                    and v.get("in_iface") == "lo"
                    and v.get("src_ip") == "127.77.0.1"
                    and v.get("dest_ip") == "127.77.0.2"
                ]
                row["sensor_rules"] = [
                    dict(
                        source="SURICATA",
                        basis="SENSOR_TRANSACTION",
                        sid=v["alert"]["signature_id"],
                        severity=v["alert"]["severity"],
                    )
                    for v in alerts
                ]
                need(
                    any(v["sid"] == 9100035 for v in row["sensor_rules"])
                    == (row["route"] == "/api/auth/csrf"),
                    "Benign canary rule transaction attribution",
                )
                projection = records[rid]
                need(projection["status"] == "SCORED", "Shadow unavailable or late")
                row.update(
                    tx=k,
                    audit_id=audit[rid]["event_id"],
                    dispatch_ns=projection["dispatch_ns"],
                    projection_ms=round(
                        (projection["available_ns"] - projection["dispatch_ns"]) / 1e6, 3
                    ),
                    score=projection["score"],
                    vector_sha256=projection["vector_sha256"],
                    model_sha256=projection["model_sha256"],
                    available_ns=projection["available_ns"],
                    scorer_timing=projection.get("scorer_timing", {}),
                    source_receipts_ns={
                        s: observed.get((s, rid if s != "E" else key)) for s in ("N", "A", "E")
                    },
                )
            if a.extended:
                rid = extended["sensor_unavailable_request"]
                need("tx" not in requests[rid], "Invalid sensor attribution while offline")
                for missing_id, row in requests.items():
                    if "tx" in row:
                        continue
                    pr = records[missing_id]
                    need(
                        pr["status"] == "SCORED"
                        and ri[missing_id]["schema_version"] == "nginx-ai-1"
                        and uuid.UUID(audit[missing_id]["event_id"])
                        and edges[missing_id]["status"]
                        == audit[missing_id]["status_code"]
                        == row["status"],
                        "Partial observation integrity",
                    )
                    row.update(
                        tx=None,
                        audit_id=audit[missing_id]["event_id"],
                        dispatch_ns=pr["dispatch_ns"],
                        available_ns=pr["available_ns"],
                        model_sha256=pr["model_sha256"],
                        score=pr["score"],
                        vector_sha256=pr["vector_sha256"],
                        scorer_timing=pr.get("scorer_timing", {}),
                        sensor_absence=row.get(
                            "sensor_absence", "offline" if missing_id == rid else "unobserved"
                        ),
                        source_receipts_ns={s: observed.get((s, missing_id)) for s in ("N", "A")},
                    )
                need(
                    len({k["tx"]["generation"] for k in proofrows}) == 2,
                    "Sensor generation did not rotate",
                )
            need(
                seen_transactions == set(eve) and (a.extended or len(proofrows) == expected_sensor),
                "Sensor proof roster mismatch",
            )
            need(
                len(requests) == len(records) == len(ri) == len(audit) == len(edges) == len(roster),
                "Roster mismatch",
            )
            fixture = w / "proof.json"
            fixture.write_text(
                json.dumps(
                    dict(
                        key_hex=secret["key"],
                        kid=secret["kid"],
                        epoch=secret["epoch"],
                        rows=proofrows,
                        observations=observations,
                    )
                )
            )
            checked = subprocess.run(
                [
                    a.proof_binary,
                    "--exact",
                    "transaction_proof::external_njs_suricata_batch",
                    "--ignored",
                ],
                cwd=w,
                env=os.environ | {"WS_PROOF_TEST_FIXTURE": str(fixture)},
                capture_output=True,
                timeout=10,
            )
            need(
                checked.returncode == 0 and b"1 passed" in checked.stdout, "Rust batch proof failed"
            )
            verified = time.time_ns()
            need(
                len(jsonlines(w / "access"))
                == len(jsonlines(w / "audit.jsonl"))
                == len(jsonlines(w / "ri-input"))
                == len(roster),
                "Duplicate event in the physical roster",
            )
            for row in requests.values():
                times = row["source_receipts_ns"]
                times["S_verified"] = verified if row["tx"] is not None else None
                row["mask_at_cutoff"] = (
                    "".join(
                        s
                        for s in "NSA"
                        if (v := times["S_verified" if s == "S" else s]) is not None
                        and row["dispatch_ns"] <= v
                        and v + 1_000_000 <= row["dispatch_ns"] + 1_000_000_000
                    )
                    or "NONE"
                )
            # Durable numeric-only engineering views. Independent semantic review is external.
            with (a.output / "observations.jsonl").open("x") as output:
                for rid, projection in records.items():
                    evidence = requests[rid]
                    item = dict(
                        projection,
                        route_class="AUTH_API",
                        source_mask_at_cutoff=evidence["mask_at_cutoff"],
                        structural_mask="NSA" if evidence["tx"] is not None else "NA",
                        source_receipts_ns=evidence["source_receipts_ns"],
                        tx=evidence["tx"],
                        audit_event_id=evidence["audit_id"],
                        oracle=evidence["oracle"],
                        role="ENGINEERING_ONLY",
                    )
                    output.write(json.dumps(item, sort_keys=True) + "\n")
            # Only redacted, finite input from the verified edge may leave this test namespace.
            (a.output / "ri-input.json").write_text(json.dumps(list(ri.values())))
            out.update(
                requests=requests,
                structural_nsa=len(proofrows),
                native_sensor_transactions=len(seen_transactions),
                extended=extended,
                rust_transaction_proof="PASS",
                native_train=0,
                protected_ip_verified=False,
            )
        except Exception:
            # Retain component startup diagnostics, never raw HTTP, proof keys or application payloads.
            for name in ("sensor", "student", "nginx", "receiver", "error"):
                path = w / (name + ".log" if name != "error" else name)
                if path.exists():
                    lines = [
                        l
                        for l in path.read_text(errors="replace").splitlines()
                        if any(x in l.lower() for x in ("error", "exception", "failed", "warning"))
                    ]
                    print(name, [l[:160] for l in lines[-5:]], file=sys.stderr)
            raise
    out["cleanup"] = "PASS"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extended", action="store_true")
    for opt in (
        "output",
        "nginx",
        "module",
        "student",
        "h2",
        "sensor-prefix",
        "ort",
        "scorer",
        "proof-binary",
    ):
        ap.add_argument("--" + opt, type=Path, required=True)
    ap.add_argument(
        "--delivery",
        type=Path,
        help="Private empty run directory owned and removed by the Local acceptance controller",
    )
    ap.add_argument(
        "--bundle",
        type=Path,
        help="Explicit historical R35 bundle. Default uses the Local release slot.",
    )
    ap.add_argument("--owner-uid", type=int, required=True)
    ap.add_argument("--host-netns", required=True)
    args = ap.parse_args()
    os.umask(0o077)
    result = {}
    main(args, result)
    (args.output / "live.json").write_text(json.dumps(result, indent=2) + "\n")

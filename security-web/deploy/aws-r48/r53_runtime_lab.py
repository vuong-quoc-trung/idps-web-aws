"""Exercise the installed AWS observation pipeline with a benign, isolated marker."""

import contextlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess as sp
import sys
import tempfile
import time

import gateway

PG = Path("/usr/lib/postgresql/18/bin")
ACTIVE = Path("/opt/websentinel-r47/current")
KIT = Path("/opt/websentinel-r48/runtime")
MARKER_SID = 153001
PATH = "/api/auth/csrf"


def run(*args, **kwargs):
    return sp.check_output(args, text=True, timeout=20, **kwargs).strip()


def wait_for(read):
    until = time.monotonic() + 38
    while time.monotonic() < until:
        try:
            value = read()
            if value:
                return value
        except (OSError, sp.CalledProcessError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Isolated runtime readiness or evidence timed out")


def request(port, path, method="GET", payload=None, token=None, tls=None, headers=None):
    options = {"Authorization": "Bearer " + token} if token else {}
    options.update(headers or {})
    if payload is not None:
        options["Content-Type"] = "application/json"
    connection = (http.client.HTTPSConnection("localhost", port, timeout=5, context=tls)
                  if tls else http.client.HTTPConnection("127.0.0.1", port, timeout=5))
    with contextlib.closing(connection):
        connection.request(method, path, json.dumps(payload) if payload is not None else None, options)
        response = connection.getresponse()
        return response.status, response.getheader("X-Request-Id"), response.read()


def main(root, pgdata, outer_namespace):
    if os.geteuid() != 0 or os.readlink("/proc/self/ns/net") == outer_namespace or socket.if_nameindex() != [(1, "lo")]:
        raise RuntimeError("A private loopback-only network namespace is required")
    if run("ip", "route", "show", "default"):
        raise RuntimeError("Unexpected default route")
    os.umask(0o077)
    print("R53 runtime lab: private network, temporary databases, synthetic alert marker", flush=True)
    binary = ACTIVE / "security/pbl4-security-demo"
    scorer = ACTIVE / "scorer"
    password = secrets.token_urlsafe(22)
    password_hash = run(binary, "--hash-password", input=password + "\n")
    with contextlib.ExitStack() as cleanup:
        def start(name, *args, extra=None, cwd=root):
            with (root / (name + ".log")).open("w") as output:
                child = sp.Popen(args, cwd=cwd, stdout=output, stderr=output, env=os.environ | (extra or {}))

            def stop():
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(4)
                    except sp.TimeoutExpired:
                        child.kill()
                        child.wait(3)

            cleanup.callback(stop)
            return child

        run("runuser", "-u", "postgres", "--", PG / "initdb", "-D", pgdata / "data", "-A", "trust", "--no-locale", "-E", "UTF8")
        run("runuser", "-u", "postgres", "--", PG / "pg_ctl", "-D", pgdata / "data", "-o",
            f"-h 127.0.0.1 -p 55453 -k {pgdata}", "-l", pgdata / "postgres.log", "-w", "start")
        cleanup.callback(run, "runuser", "-u", "postgres", "--", PG / "pg_ctl", "-D", pgdata / "data", "-m", "fast", "-w", "stop")
        for name in ("student_r53", "security_r53"):
            run(PG / "createdb", "-h", "127.0.0.1", "-p", "55453", "-U", "postgres", name)

        files = {name: root / name for name in ("edge.jsonl", "audit.jsonl", "proof.jsonl", "score.jsonl")}
        for path in files.values():
            path.touch()
        for name in ("client", "proxy", "fastcgi", "uwsgi", "scgi", "sensor", "score", "kit"):
            (root / name).mkdir()
        kit = root / "kit"
        for name in ("pbl4-access.conf", "proof-probe.js", "https-shadow-mirror.conf", "transaction-evidence.lua", "pbl4.rules"):
            shutil.copyfile(KIT / name, kit / name)
        # A safe GET is positive only for this labeled, lab-only rule.
        with (kit / "pbl4.rules").open("a") as rules:
            rules.write(f'\nalert http any any -> $HOME_NET $HTTP_PORTS (msg:"R53 isolated benign observation marker"; flow:established,to_server; http.uri; content:"{PATH}"; startswith; endswith; sid:{MARKER_SID}; rev:1;)\n')
        key = root / "key.json"
        key.write_text(json.dumps({"kid": "r53-lab", "epoch": secrets.token_hex(16), "key": secrets.token_hex(32)}))
        crt, tlskey = root / "tls.crt", root / "tls.key"
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost", "-keyout", tlskey, "-out", crt, stderr=sp.DEVNULL)
        base = f'''server {{
    listen 127.0.0.1:18453 ssl;
    server_name localhost;
    ssl_certificate {crt};
    ssl_certificate_key {tlskey};
    add_header X-Request-Id $request_id always;
    location /api/ {{
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header X-Request-Id $request_id;
    }}
}}
'''
        cfg = root / "nginx.conf"
        paths = "".join(f"{name}_temp_path {root / directory};\n" for name, directory in
                        (("client_body", "client"), ("proxy", "proxy"), ("fastcgi", "fastcgi"), ("uwsgi", "uwsgi"), ("scgi", "scgi")))
        rendered = gateway.render(base, kit, key, 0, files["edge.jsonl"], root / "score/receiver.sock")
        rendered = rendered.replace('js_var $probe_key_gid 0;', 'js_var $probe_key_gid "";')
        cfg.write_text(f"load_module /usr/lib/nginx/modules/ngx_http_js_module.so;\nmaster_process off;\n"
                       f"pid {root / 'nginx.pid'};\nevents {{ worker_connections 64; }}\nhttp {{\n{paths}{rendered}}}")
        sensor = root / "sensor.yaml"
        sensor.write_text(gateway.sensor_config(kit, root / "sensor"))
        run("nginx", "-t", "-c", cfg, stderr=sp.STDOUT)
        run("suricata", "-T", "-c", sensor, stderr=sp.STDOUT)
        start("student", "java", "-XX:ActiveProcessorCount=2", "-Xmx384m", "-jar", ACTIVE / "student.jar",
              extra={"DB_URL": "jdbc:postgresql://127.0.0.1:55453/student_r53", "DB_USERNAME": "postgres", "DB_PASSWORD": password,
                     "STUDENT_SOURCE_INSTANCE": "aws-r47", "STUDENT_AUDIT_LOG_PATH": str(files["audit.jsonl"]),
                     "STUDENT_AUDIT_HMAC_KEY": secrets.token_hex(32), "PASSWORD_RESET_MAIL_ENABLED": "false"})
        generation = secrets.token_hex(16)
        start("sensor", "suricata", "-c", sensor, "--af-packet=lo", "--runmode", "single", "--set", "sensor-name=ws-generation-" + generation,
              extra={"WS_SENSOR_GENERATION": generation})
        start("scorer", sys.executable, "-IB", scorer / "ai-training/contracts/https-model-r36/serve.py",
              "--socket", root / "score/receiver.sock", "--database", root / "score/receipts.db", "--journal", files["score.jsonl"],
              "--binary", scorer / "bin/scorer", "--ort", scorer / "lib/onnxruntime.so", "--slot", "candidate", "--lineage", "r53-isolated")
        start("correlator", sys.executable, "-B", KIT / "correlate.py", "--key", key, "--output", files["proof.jsonl"],
              files["edge.jsonl"], root / "sensor/chain.tsv", root / "sensor/eve.json", files["audit.jsonl"])
        start("security", binary, cwd=ACTIVE / "security", extra={
            "DATABASE_URL": "postgresql://postgres@127.0.0.1:55453/security_r53", "APP_ADDR": "127.0.0.1:33053",
            "ADMIN_PASSWORD_HASH": password_hash, "VIEWER_PASSWORD_HASH": password_hash,
            "ENFORCEMENT_MODE": "OFF", "AUTO_BLOCK": "false", "PBL4_FIREWALL_CMD": "/bin/false",
            "COLLECT_ALL_EVENTS": "true", "SECURITY_SENSOR_ID": "r53-isolated", "NGINX_ACCESS_PATH": str(files["edge.jsonl"]),
            "STUDENT_AUDIT_LOG_PATH": str(files["audit.jsonl"]), "SURICATA_EVE_PATH": str(root / "sensor/eve.json"),
            "SURICATA_LUA_PATH": str(root / "sensor/chain.tsv"), "THREE_SOURCE_RESULTS_PATH": str(files["proof.jsonl"]),
            "AI_HTTPS_RESULTS_PATH": str(files["score.jsonl"]), "SURICATA_CAPTURE_MODE": "post-proxy",
            "SURICATA_POST_PROXY_INTERFACE": "lo", "SURICATA_PROXY_IP": gateway.SOURCE, "SURICATA_WEB_IP": gateway.EGRESS,
            "SURICATA_WEB_PORT": str(gateway.PORT), "SURICATA_EVE_GENERATION_HOST": "true"})
        start("nginx", "nginx", "-c", cfg, "-g", "daemon off;")
        wait_for(lambda: request(8080, PATH)[0] == 200)
        wait_for(lambda: request(33053, "/health")[0] == 200)
        wait_for(lambda: "engine started" in (root / "sensor.log").read_text().lower())
        wait_for(lambda: run("curl", "-fsS", "--max-time", "2", "--unix-socket", root / "score/receiver.sock",
                             "-o", "/dev/null", "-w", "%{http_code}", "http://localhost/healthz", stderr=sp.DEVNULL) == "200")
        _, _, login = request(33053, "/api/auth/login", "POST", {"username": "admin", "password": password})
        token = json.loads(login)["token"]
        events = http.client.HTTPConnection("127.0.0.1", 33053, timeout=17)
        cleanup.callback(events.close)
        events.request("GET", "/api/events", headers={"Authorization": "Bearer " + token})
        stream = events.getresponse()
        assert stream.status == 200
        while (line := stream.readline()) and line.strip() != b"event: resync":
            continue
        assert line, "SSE closed before resync"
        code, rid, _ = request(18453, PATH, tls=ssl.create_default_context(cafile=str(crt)),
                               headers={"X-Forwarded-For": "192.0.2.53"})
        assert code == 200 and rid and len(rid) == 32

        def sql(statement):
            return run(PG / "psql", "-XAt", "-h", "127.0.0.1", "-p", "55453", "-U", "postgres", "-d", "security_r53", "-c", statement)

        def evidence():
            result = json.loads(sql(f"""
                WITH marker AS (SELECT id FROM security_alerts WHERE rule_name LIKE 'SURICATA: SID {MARKER_SID}:%')
                SELECT jsonb_build_object(
                    'correlation',(SELECT result FROM request_correlations WHERE request_id='{rid}'),
                    'hybrid',(SELECT decision FROM hybrid_incidents WHERE request_id='{rid}'),
                    'alerts',(SELECT count(*) FROM marker),
                    'links',(SELECT count(*) FROM detector_alert_links l JOIN marker m ON m.id=l.alert_id
                             WHERE l.link_basis='SENSOR_TRANSACTION'),
                    'actions',(SELECT count(*) FROM firewall_actions))
            """))
            if (result["correlation"] and result["hybrid"] and result["hybrid"].get("https_research")
                    and result["hybrid"]["rule_sources"] == ["SURICATA"]):
                return result
            return None

        proof = wait_for(evidence)
        print(json.dumps({"marker_alerts": proof["alerts"], "marker_links": proof["links"],
                          "score_status": proof["hybrid"]["https_research"]["status"],
                          "firewall_actions": proof["actions"]}), flush=True)
        assert proof["correlation"]["status"] == "MATCHED" and not proof["correlation"]["late_event"]
        assert proof["hybrid"]["https_research"]["status"] == "SCORED" and proof["alerts"] == proof["links"] == 1 and proof["actions"] == 0
        assert sql(f"SELECT count(*) FROM normalized_events WHERE request_id='{rid}' AND source IN ('NGINX','STUDENT_AUDIT') AND client_ip='127.0.0.1'") == "2"
        assert proof["hybrid"]["trusted_client_ip"] is None
        alert_id = sql(f"SELECT id FROM security_alerts WHERE rule_name LIKE 'SURICATA: SID {MARKER_SID}:%'")
        assert request(33053, f"/api/alerts/{alert_id}", token=token)[0] == 200
        while True:
            line = stream.readline()
            if not line:
                raise RuntimeError("SSE ended before marker delivery")
            if line.strip() == b"event: alert.created" and stream.readline().strip() == b"data: " + alert_id.encode():
                break

        _, _, viewer_login = request(33053, "/api/auth/login", "POST", {"username": "viewer", "password": password})
        viewer = json.loads(viewer_login)["token"]
        triage_path = f"/api/alerts/{alert_id}/triage"
        change = {"status": "INVESTIGATING", "version": 0, "note": "R53 isolated benign marker"}
        assert request(33053, triage_path, "POST", change, viewer)[0] == 403
        status, _, updated = request(33053, triage_path, "POST", change, token)
        assert status == 200 and json.loads(updated) == {"status": "INVESTIGATING", "version": 1}
        assert request(33053, triage_path, "POST", change, token)[0] == 409
        assert sql(f"SELECT count(*) FROM alert_triage_history WHERE alert_id={alert_id}") == "1"
        print(json.dumps({"request_id": rid, "http": code, "sources": proof["correlation"]["sources"],
                          "flow_id": proof["correlation"]["flow_id"], "tx_id": proof["correlation"]["tx_id"],
                          "late": False, "ai": proof["hybrid"]["https_research"], "hybrid": proof["hybrid"]["policy_action"],
                          "risk": proof["hybrid"]["final_risk"], "alerts": proof["alerts"], "firewall_actions": 0,
                          "forwarded_header_ignored": True, "enforcement_target": None, "sse": "alert.created",
                          "triage": ["viewer403", "admin200", "stale409"], "triage_history": 1}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])

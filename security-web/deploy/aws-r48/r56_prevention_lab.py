"""Run the Prevention API against a narrowly scoped actuator in an EC2 test unit."""

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socket
import struct
import subprocess as sp
import sys
from threading import Event, Thread
import time

from r53_runtime_lab import PG, request, wait_for

SERVER, PEER = "10.254.56.1", "10.254.56.2"
PORT, API_PORT = 18456, 33056
TABLE = "r56_prevention"
SET = ("inet", TABLE, "blocked_ips")
CAPABILITY = Path("/run/websentinel-r56-lab")
UNIT = "websentinel-r56-prevention.service"


def run(*args, **kwargs):
    return sp.check_output(args, text=True, timeout=5, **kwargs).strip()


def validate_scope(host):
    if (os.geteuid() != 0 or os.stat("/proc/self/ns/net").st_ino == host
            or os.stat("/proc/1/ns/net").st_ino != host
            or {name for _, name in socket.if_nameindex()} != {"lo", "r56-edge"}
            or run("ip", "route", "show", "default")
            or run("ip", "-6", "route", "show", "default")
            or run("ip", "-4", "route", "get", PEER).split()[:5]
            != [PEER, "dev", "r56-edge", "src", SERVER]):
        raise RuntimeError("Isolated interface or route identity differs")


def respond(conn, uid, host, authorize_block, ingress=None):
    conn.settimeout(1)
    pid, actual_uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if (actual_uid != uid
            or os.stat(f"/proc/{pid}/ns/net").st_ino != os.stat("/proc/self/ns/net").st_ino):
        return
    line = bytearray()
    while len(line) < 64:
        piece = conn.recv(64 - len(line))
        if not piece:
            break
        line.extend(piece)
    proof = None
    auto = re.fullmatch(rb"APPLY (CANARY_RULE|CANARY_HYBRID) ([0-9a-f]{32}) ([1-6])\n", line)
    lookup = re.fullmatch(rb"PROOF ([0-9a-f]{32})\n", line)
    if ingress and (auto or lookup):
        validate_scope(host)
        rid = (auto[2] if auto else lookup[1]).decode()
        proof = ingress.receipt(rid)
        if proof is None:
            return
        if lookup:
            conn.sendall(json.dumps(proof).encode())
            return
        expected = b"CANARY_HYBRID" if proof["application_denied"] else b"CANARY_RULE"
        if auto[1] != expected:
            return
    elif not re.fullmatch(rb"(?:STATUS|BLOCK 10\.254\.56\.2 [1-9][0-9]{0,2}|UNBLOCK 10\.254\.56\.2)\n", line):
        return
    else:
        validate_scope(host)
    parts = bytes(line).decode().split()
    original = json.loads(run("nft", "-j", "list", "set", *SET))
    contents = next(item["set"] for item in original["nftables"] if "set" in item)
    entries = contents.get("elem", [])
    if any((item if isinstance(item, str) else item.get("elem", {}).get("val")) != PEER
           for item in entries):
        raise RuntimeError("Unexpected lease target")
    changed = False
    if parts[0] in ("BLOCK", "APPLY"):
        seconds = int(parts[-1])
        if not authorize_block() or not 1 <= seconds <= 300:
            return
        if proof and (entries or ingress.receipt(proof["request_id"]) != proof):
            return
        if not entries:
            run("nft", "add", "element", *SET, "{", PEER, "timeout", f"{seconds}s", "}")
            changed = True
    elif parts[0] == "UNBLOCK" and entries:
        run("nft", "delete", "element", *SET, "{", PEER, "}")
    try:
        conn.sendall(run("nft", "-j", "list", "set", *SET).encode())
    except (OSError, sp.SubprocessError):
        if changed:
            run("nft", "delete", "element", *SET, "{", PEER, "}")
        raise


def serve(listener, uid, host, authorize_block, stop, ingress=None):
    listener.settimeout(.2)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except TimeoutError:
            continue
        with conn:
            try:
                respond(conn, uid, host, authorize_block, ingress)
            except (OSError, RuntimeError, ValueError, sp.SubprocessError):
                # An empty response is a denial to the caller.
                print("Actuator refused a request or lost readback", file=sys.stderr, flush=True)


def main(root, pg, host, *, browser_check=None, ingress=None):
    if (os.geteuid() != 0 or os.stat("/proc/self/ns/net").st_ino == host
            or os.stat("/proc/1/ns/net").st_ino != host
            or socket.if_nameindex() != [(1, "lo")] or run("nft", "list", "tables")
            or f"/{UNIT}" not in Path("/proc/self/cgroup").read_text()
            or run("systemctl", "show", UNIT, "-p", "PrivateNetwork", "--value") != "yes"):
        raise RuntimeError("Expected the owned systemd unit and a fresh network namespace")
    actor = pwd.getpwnam("ws-r47-security")
    binary = root / "lab-bin"
    password = (root / "browser.password").read_text().strip() if browser_check else secrets.token_urlsafe(24)
    phc = run(binary, "--hash-password", input=password + "\n")
    with ExitStack() as cleanup:
        def start(args, **kwargs):
            child = sp.Popen(args, **kwargs)
            def stop():
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(5)
                    except sp.TimeoutExpired:
                        child.kill()
                        child.wait(3)
            cleanup.callback(stop)
            return child, stop

        peer, _ = start(["unshare", "--net", "sleep", "135"])
        wait_for(lambda: os.stat(f"/proc/{peer.pid}/ns/net").st_ino not in
                 (host, os.stat("/proc/self/ns/net").st_ino))
        client = ("nsenter", "-t", str(peer.pid), "-n")
        run("ip", "link", "add", "r56-edge", "type", "veth", "peer", "name", "r56-peer")
        run("ip", "link", "set", "r56-peer", "netns", str(peer.pid))
        for prefix, interface, address in [((), "r56-edge", SERVER), (client, "r56-peer", PEER)]:
            run(*prefix, "ip", "addr", "add", address + "/30", "dev", interface)
            run(*prefix, "ip", "link", "set", interface, "up")
            assert not run(*prefix, "ip", "route", "show", "default")
        validate_scope(host)
        assert not run("ip", "-4", "route", "show", "default")
        def verify_table_cleanup():
            assert not run("nft", "list", "tables")
            print(f"{'R60' if ingress else 'R56'}_KERNEL_CLEANUP=PASS", flush=True)

        cleanup.callback(verify_table_cleanup)
        run("nft", "-f", "-", input=f"""
            table inet {TABLE} {{
                set blocked_ips {{ type ipv4_addr; flags timeout; }}
                chain input {{
                    type filter hook input priority filter; policy accept;
                    iifname "r56-edge" ip saddr {PEER} ip daddr {SERVER} tcp dport {PORT} ip saddr @blocked_ips counter drop
                }}
            }}
        """)
        cleanup.callback(run, "nft", "delete", "table", "inet", TABLE)
        observed = Event()

        class Probe(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.client_address[0] != PEER:
                    self.send_error(403)
                    return
                observed.set()
                self.send_response(204)
                self.end_headers()

            def log_message(self, *_):
                pass

        def connects(path="/"):
            code = sp.run([*client, "curl", "-fsS", "--max-time", "0.5", "-o", "/dev/null",
                           f"http://{SERVER}:{PORT}{path}"], stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                          timeout=2).returncode
            assert code in (0, 28), f"Unexpected probe error {code}"
            return code == 0

        authorize_block = observed.is_set
        if ingress:
            connects, authorize_block = ingress.start(root, start, cleanup, client)
        else:
            listener = cleanup.enter_context(HTTPServer((SERVER, PORT), Probe))
            probe_thread = Thread(target=listener.serve_forever, daemon=True)
            probe_thread.start()
            cleanup.callback(listener.shutdown)
        assert connects() and (ingress or observed.is_set())
        capability_dir = CAPABILITY.stat()
        assert capability_dir.st_uid == 0 and capability_dir.st_mode & 0o022 == 0
        (CAPABILITY / "host-netns").write_text(str(host) + "\n")
        (CAPABILITY / "host-netns").chmod(0o644)
        canary = ingress if ingress and ingress.canary else None
        if canary:
            approval = CAPABILITY / "ingress-canary"
            approval.write_text("R61-v1\n")
            approval.chmod(0o644)
        sock = cleanup.enter_context(socket.socket(socket.AF_UNIX))
        socket_path = CAPABILITY / "actuator.sock"
        sock.bind(str(socket_path))
        os.chown(socket_path, 0, actor.pw_gid)
        socket_path.chmod(0o660)
        sock.listen(8)
        stopped = Event()
        thread = Thread(target=serve, args=(sock, actor.pw_uid, host, authorize_block, stopped, canary), daemon=True)
        thread.start()
        cleanup.callback(thread.join, 4)
        cleanup.callback(stopped.set)

        sp.run(["runuser", "-u", "postgres", "--", PG / "initdb", "-D", pg / "data",
                "-A", "trust", "--no-locale"], stdout=sp.DEVNULL, check=True, timeout=12)
        sp.run(["runuser", "-u", "postgres", "--", PG / "pg_ctl", "-D", pg / "data",
                "-o", f"-h 127.0.0.1 -p 55456 -k {pg}", "-l", pg / "pg.log", "-w", "start"],
               stdout=sp.DEVNULL, check=True, timeout=12)
        cleanup.callback(run, "runuser", "-u", "postgres", "--", PG / "pg_ctl",
                         "-D", pg / "data", "-m", "fast", "-w", "stop")
        evidence_files = ["edge.jsonl", "eve.json"]
        if ingress:
            evidence_files.append("manual-eve.json")
        for name in evidence_files:
            (root / name).touch()
            (root / name).chmod(0o644)
        from gateway import sensor_config
        sensor = sensor_config(root, root)
        sensor = sensor.split("  - lua:", 1)[0] + "unix-command:\n  enabled: no\n"
        interface = "lo" if ingress else "r56-edge"
        if not ingress:
            sensor = (sensor.replace("127.77.0.1", PEER).replace("127.77.0.2", SERVER)
                      .replace("18080", str(PORT)).replace("interface: lo", f"interface: {interface}"))
        sensor = (sensor.replace("filemode: 640", "filemode: 644")
                  .replace("checksum-validation: yes", "checksum-validation: no"))
        config = root / "sensor.yaml"
        config.write_text(sensor)
        (root / "pbl4.rules").write_text(
            'alert http any any -> $HOME_NET $HTTP_PORTS (msg:"R56 benign rule marker"; '
            'flow:established,to_server; http.uri; content:"/r56-health"; startswith; endswith; sid:156001; rev:1;)\n'
            + (canary.sensor_rules() if canary else "")
        )
        with (root / "sensor.log").open("w") as log:
            start(["suricata", "-c", str(config), f"--af-packet={interface}", "--runmode", "single"],
                  stdout=log, stderr=sp.STDOUT)
        wait_for(lambda: "engine started" in (root / "sensor.log").read_text().lower())
        env = {"PATH": "/usr/sbin:/usr/bin:/bin", "RUST_LOG": "warn",
               "DATABASE_URL": "postgresql://postgres@127.0.0.1:55456/postgres",
               "ENFORCEMENT_MODE": "MANUAL", "AUTO_BLOCK": "false",
               "ENFORCE_ALLOWED_SUBNETS": PEER + "/32", "APP_ADDR": f"127.0.0.1:{API_PORT}",
               "ADMIN_PASSWORD_HASH": phc, "VIEWER_PASSWORD_HASH": phc,
               "NGINX_ACCESS_PATH": str(root / "edge.jsonl"),
               "SURICATA_EVE_PATH": str(root / "eve.json"),
               "SURICATA_CAPTURE_MODE": "pre-proxy", "SURICATA_WEB_IP": SERVER,
               "SURICATA_WEB_PORT": str(PORT), "SURICATA_POST_PROXY_INTERFACE": "r56-edge"}
        if ingress:
            # Post-proxy ingestion requires OFF mode. The root observer reads the
            # backend EVE directly for the lab proof. The manual API has no feed
            # from that sensor and cannot promote its addresses into targets.
            env["SURICATA_EVE_PATH"] = str(root / "manual-eve.json")
        if canary:
            env["WS_C2_INGRESS_CANARY"] = "1"
            env["COLLECT_ALL_EVENTS"] = "true"

        def launch():
            child, stop = start(["runuser", "-u", actor.pw_name, "--",
                                 "setpriv", "--no-new-privs", str(binary)],
                                cwd=root if browser_check else "/opt/websentinel-r47/current/security", env=env)
            def healthy():
                if child.poll() is not None:
                    raise RuntimeError(f"Isolated Prevention API exited with status {child.returncode}")
                return request(API_PORT, "/health")[0] == 200

            wait_for(healthy)
            return stop

        def token(user):
            code, _, body = request(API_PORT, "/api/auth/login", "POST", {"username": user, "password": password})
            assert code == 200
            return json.loads(body)["token"]

        def call(path, method="GET", payload=None, auth=None):
            code, _, data = request(API_PORT, path, method, payload, auth or admin)
            return code, json.loads(data) if data.startswith((b"{", b"[")) else None

        def audit(action_id):
            return next(row for row in call("/api/audit")[1] if row["id"] == action_id)

        def synced(active):
            status = call("/api/blocked-ips")[1]
            if status["sync"]["status"] == "SYNCED" and status["kernel"] == ([PEER] if active else []):
                assert [row["ip"] for row in status["database"]] == status["kernel"]
                return status

        def mutate(path, method, payload=None):
            code, result = call(path, method, payload)
            assert code == 202, (code, result)
            action_id = result["id"]
            wait_for(lambda: audit(action_id)["status"] != "PENDING")
            assert audit(action_id)["status"] == "SUCCESS" and audit(action_id)["actor"] == "admin"
            return action_id

        stop_api = launch()
        admin, viewer = token("admin"), token("viewer")
        endpoint = "/api/blocked-ips"
        wait_for(lambda: call("/api/status")[1]["prevention_state"] == "READY")
        block = {"ip": PEER, "reason": "R56 isolated manual test", "ttl_seconds": 70}
        assert request(API_PORT, endpoint, "POST", block)[0] == 401
        assert call(endpoint, "POST", block, viewer)[0] == 403
        assert call(endpoint, "POST", block | {"ip": SERVER})[0] == 400
        assert call(endpoint, "POST", block | {"event_id": 1})[0] == 400
        if browser_check:
            browser_check(call, synced, connects, audit)
        else:
            def restart():
                nonlocal admin, stop_api
                stop_api()
                stop_api = launch()
                admin = token("admin")

            if ingress:
                ingress.verify(call, mutate, synced, audit, connects, restart, block, authorize_block)
                stopped.set()
                thread.join(4)
                assert not thread.is_alive()
                sock.close()
                assert call(endpoint, "POST", block)[0] == 400
                assert call(endpoint)[1]["sync"]["status"] == "UNVERIFIED" and connects()
                print("R60_ACTUATOR_OFFLINE_REFUSED=PASS", flush=True)
                return
            first = mutate(endpoint, "POST", block)
            assert synced(True) and not connects()
            assert re.search(r"counter packets [1-9][0-9]*", run("nft", "list", "table", "inet", TABLE))
            restart()
            assert synced(True) and not connects() and audit(first)["status"] == "SUCCESS"
            second = mutate(endpoint + "/" + PEER, "DELETE")
            assert synced(False) and connects()
            time.sleep(31)
            assert connects("/r56-health")
            def query(sql):
                return run(PG / "psql", "-h", "127.0.0.1", "-p", "55456", "-U", "postgres",
                           "-XAt", "-c", sql)
            native_alert = int(wait_for(lambda: query(
                "SELECT id FROM security_alerts WHERE rule_name LIKE 'SURICATA: SID 156001:%'"
                " AND client_ip_verified IS FALSE AND network_src_ip='10.254.56.2' AND NOT suricata_post_proxy"
                " AND evidence::jsonb#>>'{suricata_origin,client_ip_verified}'='true'"
            )))
            third = mutate(endpoint, "POST", block | {"ttl_seconds": 6, "event_id": native_alert})
            assert synced(True) and not connects()
            time.sleep(7)
            wait_for(lambda: synced(False))
            assert connects() and audit(third)["status"] == "SUCCESS"
            assert audit(third)["event_id"] == native_alert
            assert {row["id"] for row in call("/api/audit")[1]} == {first, second, third}
            assert run(PG / "psql", "-h", "127.0.0.1", "-p", "55456", "-U", "postgres",
                       "-XAt", "-c", "SELECT count(*) FROM blocked_ips WHERE active") == "0"
            stopped.set()
            thread.join(4)
            assert not thread.is_alive()
            sock.close()
            assert call(endpoint, "POST", block)[0] == 400
            assert call(endpoint)[1]["sync"]["status"] == "UNVERIFIED"
            assert len(call("/api/audit")[1]) == 3 and connects()
            print(json.dumps({"namespace": os.readlink("/proc/self/ns/net"), "peer": PEER,
                              "block": first, "unblock": second, "ttl": third, "audit": "3 SUCCESS",
                              "rule_alert": native_alert, "rule_sid": 156001,
                              "restart": "PASS", "protected_scope": "PASS", "rbac": [401, 403],
                              "offline_refused": "PASS", "db_kernel": "SYNCED_EMPTY"}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))

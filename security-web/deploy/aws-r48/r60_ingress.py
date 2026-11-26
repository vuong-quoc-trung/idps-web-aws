"""Bind a benign HTTP observation to its TLS ingress socket in the C2 lab."""

from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import ssl
import subprocess as sp
import sys
from threading import Thread
import time

from gateway import EGRESS, PORT as BACKEND_PORT, SOURCE
from r56_prevention_lab import PEER, PORT, SERVER, TABLE, main, run, wait_for

PATH = "/r56-health"
PROOF_SECONDS = 10
SHIPPER_IP = "192.0.2.60"  # Test-only header value from the documentation network.
CANARY = {"/health": (161001, 204), "/api/profile": (161002, 403)}


def parse_endpoint(value):
    address, port = value.split(":")
    return str(ipaddress.IPv4Address(bytes.fromhex(address)[::-1])), int(port, 16)


def established(rows, owned_inodes, local, remote):
    """Return the unique established IPv4 socket owned by the TLS terminator."""
    matches = []
    for row in rows:
        fields = row.split()
        if fields[3] != "01" or parse_endpoint(fields[1]) != local or parse_endpoint(fields[2]) != remote:
            continue
        matches.append(int(fields[9]))
    if len(matches) != 1 or matches[0] == 0 or matches[0] not in owned_inodes:
        return None
    return matches[0]


def same_request(row, request_id, local, remote, status=204):
    # The tuple comes from socket readback. Request ID links observations only.
    return (bool(re.fullmatch(r"[a-f0-9]{32}", request_id))
            and row == {"request_id": request_id, "peer": list(remote), "local": list(local), "status": status})


def nginx_socket(pid, local, remote):
    if os.stat(f"/proc/{pid}/ns/net").st_ino != os.stat("/proc/self/ns/net").st_ino:
        return None
    inodes = set()
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        match = re.fullmatch(r"socket:\[(\d+)\]", target)
        if match:
            inodes.add(int(match[1]))
    with Path(f"/proc/{pid}/net/tcp").open() as table:
        next(table)
        return established(table, inodes, local, remote)


def marked_client(cert, path=PATH, status="204"):
    """Hold the same connection open for before-and-after kernel reads."""
    context = ssl.create_default_context(cafile=cert)
    with socket.create_connection((SERVER, PORT), timeout=5) as tcp:
        with context.wrap_socket(tcp, server_hostname="localhost") as tls:
            print(tls.getsockname()[1], flush=True)
            command, session = sys.stdin.readline().split()
            assert command == "GET"
            assert path == PATH or path in CANARY
            tls.sendall(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n"
                        f"X-Forwarded-For: {SHIPPER_IP}\r\nX-Request-ID: {'f' * 32}\r\n"
                        f"X-Lab-Session: {session}\r\n\r\n".encode())
            with http.client.HTTPResponse(tls) as response:
                response.begin()
                assert response.status == int(status) and response.read() == b""
                assert not response.will_close
                print(response.getheader("X-Request-Id"), flush=True)
                sys.stdin.readline()


def read_line(process):
    if not select.select([process.stdout], [], [], 5)[0]:
        raise RuntimeError("Isolated TLS client stopped reporting progress")
    value = process.stdout.readline().strip()
    if not value:
        raise RuntimeError("Isolated TLS client closed before returning its observation")
    return value


class Ingress:
    canary = False

    def __init__(self):
        self.application = {}
        self.active = None
        self.active_receipt = None

    def start(self, root, start, cleanup, client):
        self.root, self.client = root, client
        self.lab_session = secrets.token_urlsafe(32)
        self.cert = root / "tls.crt"
        key = root / "tls.key"
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost", "-keyout", key, "-out", self.cert, stderr=sp.DEVNULL)
        self.log = root / "tls-ingress.jsonl"
        self.log.touch(mode=0o600)

        class Probe(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(handler):
                # The protected test resource checks an ephemeral application
                # session independent of the URI-based marker rule.
                denied = (self.canary and handler.path == "/api/profile"
                          and not secrets.compare_digest(handler.headers.get("X-Lab-Session", ""), self.lab_session))
                status = 403 if denied else 204
                if handler.path == PATH or self.canary and handler.path in CANARY:
                    request_id = handler.headers["X-Request-Id"]
                    self.application[request_id] = (handler.client_address, handler.headers["X-Forwarded-For"], denied)
                handler.send_response(status)
                if denied:
                    handler.send_header("Content-Length", "0")
                handler.send_header("Connection", "close")
                handler.end_headers()

            def log_message(self, *_):
                pass

        listener = cleanup.enter_context(HTTPServer((EGRESS, BACKEND_PORT), Probe))
        probe_thread = Thread(target=listener.serve_forever, daemon=True)
        probe_thread.start()
        cleanup.callback(listener.shutdown)
        cfg = root / "nginx.conf"
        paths = []
        for name in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"):
            directory = root / name
            directory.mkdir()
            paths.append(f"{name}_temp_path {directory};")
        canary_log = ""
        if self.canary:
            canary_log = f'''log_format observe escape=json
                '{{"timestamp":"$time_iso8601","request_id":"$request_id","event_id":"r51-main-$request_id",'
                '"client_ip":"$remote_addr","uri_path":"$uri","http_method":"$request_method","status":$status}}';
                access_log {root / 'edge.jsonl'} observe;'''
        cfg.write_text(f'''master_process off;
        pid {root / 'nginx.pid'};
        events {{ worker_connections 64; }}
        http {{
            {' '.join(paths)}
            log_format ingress escape=json '{{"request_id":"$request_id","peer":["$remote_addr",$remote_port],'
                '"local":["$server_addr",$server_port],"status":$status}}';
            access_log {self.log} ingress;
            {canary_log}
            server {{
                listen {SERVER}:{PORT} ssl;
                server_name localhost;
                ssl_certificate {self.cert};
                ssl_certificate_key {key};
                add_header X-Request-Id $request_id always;
                location / {{
                    proxy_pass http://{EGRESS}:{BACKEND_PORT};
                    proxy_bind {SOURCE};
                    proxy_set_header X-Request-Id $request_id;
                    proxy_set_header X-Forwarded-For $remote_addr;
                }}
            }}
        }}''')
        run("nginx", "-t", "-c", cfg, stderr=sp.STDOUT)
        with (root / "nginx.log").open("w") as log:
            self.nginx, _ = start(["nginx", "-c", cfg, "-g", "daemon off;"], stdout=log, stderr=sp.STDOUT)
        wait_for(lambda: self.connects(startup=True))
        return self.connects, self.authorized

    def connects(self, startup=False):
        code = sp.run([*self.client, "curl", "-fsS", "--max-time", "0.6", "--cacert", self.cert,
                       "--resolve", f"localhost:{PORT}:{SERVER}", "-o", "/dev/null", f"https://localhost:{PORT}/"],
                      stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=2).returncode
        assert code in ((0, 7, 28) if startup else (0, 28)), f"Unexpected TLS probe error {code}"
        return code == 0

    def authorized(self):
        if self.active is None or self.nginx.poll() is not None:
            return False
        created, local, remote, inode = self.active
        return time.monotonic() - created <= PROOF_SECONDS and nginx_socket(self.nginx.pid, local, remote) == inode

    def sensor_pair(self, backend, path=PATH, sid=156001):
        with (self.root / "eve.json").open() as eve:
            rows = [json.loads(line) for line in eve if line.endswith("\n")]
        transaction = [row for row in rows if row.get("proto") == "TCP" and row.get("in_iface") == "lo"
                       and (row.get("src_ip"), row.get("src_port")) == backend
                       and (row.get("dest_ip"), row.get("dest_port")) == (EGRESS, BACKEND_PORT)]
        http = [row for row in transaction if row["event_type"] == "http" and row.get("http", {}).get("url") == path]
        if len(http) > 1:
            raise RuntimeError("Ambiguous Suricata backend transaction")
        if http:
            flow = (http[0]["flow_id"], http[0]["tx_id"])
            alerts = [row for row in transaction if row["event_type"] == "alert" and row["alert"]["signature_id"] == sid
                      and (row.get("flow_id"), row.get("tx_id")) == flow]
            if len(alerts) > 1:
                raise RuntimeError("Duplicate rule alert on the backend transaction")
            if alerts:
                return flow

    @contextmanager
    def proof(self, path=PATH, *, publish=True, authorized_session=False):
        sid, status = CANARY.get(path, (156001, 204))
        if authorized_session:
            assert self.canary and path == "/api/profile"
            status = 204
        with sp.Popen([*self.client, sys.executable, "-B", __file__, "--client", self.cert, path, str(status)],
                      stdin=sp.PIPE, stdout=sp.PIPE, text=True, bufsize=1) as process:
            try:
                local = SERVER, PORT
                remote = PEER, int(read_line(process))
                inode = wait_for(lambda: nginx_socket(self.nginx.pid, local, remote))
                observed_at = time.monotonic()
                process.stdin.write(f"GET {self.lab_session if authorized_session else '-'}\n")
                request_id = read_line(process)
                assert request_id != "f" * 32
                assert nginx_socket(self.nginx.pid, local, remote) == inode
                rows = [json.loads(line) for line in self.log.read_text().splitlines()]
                matching = [row for row in rows if row["request_id"] == request_id]
                assert len(matching) == 1 and same_request(matching[0], request_id, local, remote, status)
                backend, forwarded_ip, denied = self.application.pop(request_id)
                assert forwarded_ip == remote[0] and backend[0] == SOURCE
                flow, tx = wait_for(lambda: self.sensor_pair(backend, path, sid))
                self.active = observed_at, local, remote, inode
                assert self.authorized(), "Ingress proof expired or socket changed"
                if self.canary and path in CANARY and publish:
                    self.active_receipt = {"request_id": request_id, "ip": remote[0], "path": path, "status": status,
                                           "flow_id": flow, "tx_id": tx, "sid": sid, "application_denied": denied}
                yield {"request_id": request_id, "status": status, "local": list(local), "peer": list(remote),
                       "socket_inode": inode, "backend": list(backend), "suricata_flow": flow, "suricata_tx": tx,
                       "rule_sid": sid}
            finally:
                self.active_receipt = None
                self.active = None
                process.stdin.close()
                try:
                    process.wait(2)
                except sp.TimeoutExpired:
                    process.kill()
                    process.wait(3)

    def verify(self, call, mutate, synced, audit, connects, restart, block, authorize):
        endpoint = "/api/blocked-ips"
        block = block | {"reason": "R60 verified TLS ingress lab"}
        assert not authorize()
        rejected, attempt = call(endpoint, "POST", block)
        assert rejected == 202, rejected
        denied_id = attempt["id"]
        wait_for(lambda: audit(denied_id)["status"] == "ERROR")
        assert synced(False) and connects()
        # The existing 30-second cooldown counts rejected BLOCK operations too.
        time.sleep(31)
        with self.proof() as first:
            assert authorize()
            block_id = mutate(endpoint, "POST", block | {"ip": first["peer"][0], "ttl_seconds": 30})
            assert synced(True) and not connects()
            assert re.search(r"counter packets [1-9]\d*", run("nft", "list", "table", "inet", TABLE))
        assert not authorize()
        restart()
        assert synced(True) and not connects() and audit(block_id)["status"] == "SUCCESS"
        unblock_id = mutate(endpoint + "/" + PEER, "DELETE")
        assert synced(False) and connects()
        time.sleep(31)
        with self.proof() as second:
            assert first["request_id"] != second["request_id"]
            ttl_id = mutate(endpoint, "POST", block | {"ip": second["peer"][0], "ttl_seconds": 6})
            assert synced(True) and not connects()
        wait_for(lambda: synced(False))
        assert connects()
        history = call("/api/audit")[1]
        assert {row["id"]: row["status"] for row in history} == {
            denied_id: "ERROR", block_id: "SUCCESS", unblock_id: "SUCCESS", ttl_id: "SUCCESS"}
        assert all(row["actor"] == "admin" for row in history)
        print("R60_INGRESS=" + json.dumps({"proofs": [first, second], "lab_namespace": os.readlink("/proc/self/ns/net"),
              "unit": "websentinel-r56-prevention.service", "proof_max_age_s": PROOF_SECONDS,
              "manual_block": block_id, "manual_unblock": unblock_id, "ttl": ttl_id, "ttl_seconds": 6,
              "restart": "PASS", "db_kernel": "SYNCED_EMPTY", "audit": "3 SUCCESS, 1 ERROR", "rbac": [401, 403],
              "protected_scope": "PASS", "forwarded_header_ignored": True, "unproven_peer_refused": denied_id}), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--client":
        marked_client(*sys.argv[2:])
    else:
        os.umask(0o077)
        main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), ingress=Ingress())

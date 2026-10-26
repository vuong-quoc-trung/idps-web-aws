#!/usr/bin/env python3
"""Exercise edge config with disposable loopback Nginx and offline Suricata.

No host service, firewall, production log or external destination is touched.
Set NGINX_BIN/SURICATA_BIN to test extracted binaries without installing them.
"""
import http.client
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def binary(name):
    return os.environ.get(name.upper() + "_BIN") or shutil.which(name)


class EdgeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nginx = binary("nginx")
        if not cls.nginx:
            raise unittest.SkipTest("nginx unavailable; set NGINX_BIN for runtime checks")
        cls.temporary = tempfile.TemporaryDirectory(prefix="idps-edge-test-")
        cls.work = Path(cls.temporary.name)
        cls.upstream_headers = []

        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                cls.upstream_headers.append(dict(self.headers))
                if self.command == "POST":
                    self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(401 if self.path.startswith("/api/auth/login") else 204)
                self.send_header("X-Request-Id", "untrusted-upstream-value")
                self.end_headers()

            do_POST = do_GET

        cls.upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            cls.port = reservation.getsockname()[1]
        snippet = (ROOT / "nginx/pbl4-proxy.conf").read_text()
        snippet = snippet.replace("listen 0.0.0.0:80;", f"listen 127.0.0.1:{cls.port};")
        snippet = snippet.replace("127.0.0.1:8080", f"127.0.0.1:{cls.upstream.server_port}").replace("127.0.0.1:5173", f"127.0.0.1:{cls.upstream.server_port}").replace("192.168.20.10:80 backup", "127.0.0.1:1 backup")
        cls.access = cls.work / "access.log"
        snippet = snippet.replace("/var/log/nginx/access.log", str(cls.access))
        config = cls.work / "nginx.conf"
        paths = "\n".join(
            f"{kind}_temp_path {cls.work / kind};"
            for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
        )
        config.write_text(
            f"error_log /dev/null crit; pid {cls.work / 'nginx.pid'};\n"
            f"events {{}}\nhttp {{\n{paths}\n{snippet}\n}}\n"
        )
        cls.command = [cls.nginx, "-p", str(cls.work), "-e", str(cls.work / "bootstrap.log"), "-c", str(config)]
        try:
            subprocess.run(cls.command + ["-t"], check=True, capture_output=True, text=True)
            cls.process = subprocess.Popen(
                cls.command + ["-g", "daemon off; master_process off;"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 3
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("disposable nginx did not start")
                    time.sleep(0.02)
        except BaseException:
            cls.upstream.shutdown()
            cls.upstream.server_close()
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def request(self, target, *, headers=None, method="GET", body=None):
        before = len(self.access.read_text().splitlines()) if self.access.exists() else 0
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        connection.request(method, target, body=body, headers=headers or {})
        response = connection.getresponse()
        status, request_ids = response.status, response.headers.get_all("X-Request-Id")
        response.read()
        connection.close()
        deadline = time.monotonic() + 2
        while True:
            lines = self.access.read_text().splitlines()
            if len(lines) > before:
                return status, request_ids, json.loads(lines[-1]), lines[-1]
            if time.monotonic() >= deadline:
                self.fail("access event was not written")
            time.sleep(0.01)

    def test_identity_headers_and_secret_redaction_before_disk(self):
        secret = "EDGE_CANARY_SECRET_7c463"
        status, ids, event, raw = self.request(
            "/api/auth/login?token=" + secret,
            headers={"X-Request-Id": secret, "X-Forwarded-For": "203.0.113.99",
                     "Authorization": "Bearer " + secret, "Cookie": "session=" + secret,
                     "User-Agent": "Bearer " + secret},
            method="POST", body="password=" + secret,
        )
        self.assertEqual(status, 401)
        self.assertEqual(ids, [event["request_id"]])
        self.assertRegex(event["request_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(self.upstream_headers[-1]["X-Request-Id"], event["request_id"])
        self.assertEqual(self.upstream_headers[-1]["X-Forwarded-For"], "127.0.0.1")
        self.assertEqual(event["client_ip"], "127.0.0.1")
        self.assertIsNone(event["query_string"])
        self.assertEqual(event["user_agent"], "[REDACTED]")
        self.assertNotIn(secret, raw)
        self.assertIsInstance(event["latency_seconds"], (int, float))
        self.assertIsInstance(event["response_bytes"], int)

    def test_sensitive_path_is_not_persisted(self):
        for path in ("/activate/PATH_CANARY", "/api/token/PATH_CANARY", "/api/students;jsessionid=PATH_CANARY"):
            with self.subTest(path=path):
                _, _, event, raw = self.request(path)
                self.assertEqual(event["uri_path"], "[REDACTED_PATH]")
                self.assertNotIn("PATH_CANARY", raw)

    def test_rule_signals_survive_query_redaction(self):
        for signal, query in (
            ("SQLI", "q=%27/**/OR/**/1=1"),
            ("SQLI", "q=UNION%20ALL%20SELECT"),
            ("SQLI", "q=pg_sleep%281%29"),
            ("XSS", "q=%3Csvg%20onload=alert%281%29%3E"),
            ("PATH_TRAVERSAL", "q=%252e%252e%252fetc%252fpasswd"),
            ("COMMAND_INJECTION", "q=%3Bwhoami"),
        ):
            with self.subTest(signal=signal, query=query):
                _, _, event, raw = self.request("/probe?" + query)
                self.assertEqual(event["rule_signals"][signal], 1)
                self.assertIsNone(event["query_string"])
                self.assertNotIn(query, raw)

    def test_benign_traffic_and_json_escaping(self):
        _, _, event, _ = self.request(
            "/catalog?search=O%27Reilly&token=BENIGN_CANARY",
            headers={"User-Agent": 'Browser "quoted" \\ slash'},
        )
        self.assertEqual(event["rule_signals"], dict.fromkeys(
            ("SQLI", "XSS", "PATH_TRAVERSAL", "COMMAND_INJECTION"), 0))
        self.assertEqual(event["user_agent"], 'Browser "quoted" \\ slash')


    def test_local_first_then_backup_on_connection_refusal(self):
        def handler(label):
            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self, *_): pass
                def do_GET(self):
                    self.send_response(200); self.end_headers(); self.wfile.write(label.encode())
            return Handler
        primary = http.server.ThreadingHTTPServer(("127.0.0.1",0),handler("LOCAL"))
        backup = http.server.ThreadingHTTPServer(("127.0.0.1",0),handler("BACKUP"))
        for server in [primary,backup]: threading.Thread(target=server.serve_forever,daemon=True).start()
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix="idps-failover-") as temporary:
                work=Path(temporary)
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
                snippet=(ROOT/"nginx/pbl4-proxy.conf").read_text().replace("listen 0.0.0.0:80;",f"listen 127.0.0.1:{port};")
                snippet=snippet.replace("127.0.0.1:8080",f"127.0.0.1:{primary.server_port}").replace("127.0.0.1:5173",f"127.0.0.1:{primary.server_port}").replace("192.168.20.10:80 backup",f"127.0.0.1:{backup.server_port} backup")
                snippet=snippet.replace("/var/log/nginx/access.log",str(work/"access.log"))
                paths="\n".join(f"{kind}_temp_path {work/kind};" for kind in ["client_body","proxy","fastcgi","uwsgi","scgi"])
                config=work/"nginx.conf"
                config.write_text(f"error_log /dev/null crit; pid {work/'nginx.pid'};\nevents {{}} http {{ {paths}\n{snippet}\n}}")
                process=subprocess.Popen([self.nginx,"-p",str(work),"-e",str(work/"bootstrap.log"),"-c",str(config),"-g","daemon off; master_process off;"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(100):
                    try:
                        with socket.create_connection(("127.0.0.1",port),timeout=.1): break
                    except OSError: time.sleep(.02)
                def read():
                    connection=http.client.HTTPConnection("127.0.0.1",port,timeout=5)
                    connection.request("GET","/api/auth/csrf"); response=connection.getresponse(); body=response.read().decode(); connection.close(); return body
                self.assertEqual(read(),"LOCAL")
                primary.shutdown(); primary.server_close()
                self.assertEqual(read(),"BACKUP")
                process.terminate(); process.wait(timeout=5); process=None
        finally:
            if process: process.terminate(); process.wait(timeout=5)
            primary.shutdown(); primary.server_close(); backup.shutdown(); backup.server_close()


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!" + "H" * (len(data) // 2), data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def packet(src, dst, sport, dport, seq, ack, flags, payload=b""):
    src, dst = socket.inet_aton(src), socket.inet_aton(dst)
    tcp = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 5 << 4, flags, 65535, 0, 0) + payload
    pseudo = src + dst + struct.pack("!BBH", 0, 6, len(tcp))
    tcp = tcp[:16] + struct.pack("!H", checksum(pseudo + tcp)) + tcp[18:]
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0, src, dst)
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    return bytes.fromhex("00112233445566778899aabb0800") + ip + tcp


def write_pcap(path, requests):
    with path.open("wb") as stream:
        stream.write(struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        for index, (target, agent, method, status) in enumerate(requests):
            sport = 40000 + index
            request = (f"{method} {target} HTTP/1.1\r\nHost: lab\r\nUser-Agent: {agent}\r\nContent-Length: 0\r\n\r\n").encode()
            response = f"HTTP/1.1 {status} Test\r\nContent-Length: 0\r\n\r\n".encode()
            client, server = "192.168.10.10", "192.168.10.1"
            frames = [
                packet(client, server, sport, 80, 100, 0, 2),
                packet(server, client, 80, sport, 500, 101, 18),
                packet(client, server, sport, 80, 101, 501, 16),
                packet(client, server, sport, 80, 101, 501, 24, request),
                packet(server, client, 80, sport, 501, 101 + len(request), 24, response),
                packet(client, server, sport, 80, 101 + len(request), 501 + len(response), 17),
                packet(server, client, 80, sport, 501 + len(response), 102 + len(request), 17),
            ]
            for offset, frame in enumerate(frames):
                stream.write(struct.pack("<IIII", 1_800_000_000 + index // 4, (index % 4) * 100_000 + offset * 1000, len(frame), len(frame)))
                stream.write(frame)


class SensorRuleTests(unittest.TestCase):
    def test_suricata_rules_against_offline_http_transactions(self):
        suricata = binary("suricata")
        if not suricata:
            self.skipTest("suricata unavailable; set SURICATA_BIN for offline engine test")
        # Existing SID meanings are retained; 1000009 is intentionally alert-only.
        requests = [
            ("/normal", "Browser", "GET", 200),
            ("/probe?q=%27/**/OR/**/1=1", "Browser", "GET", 200),
            ("/probe?q=UNION%20ALL%20SELECT", "Browser", "GET", 200),
            ("/probe?q=pg_sleep%281%29", "Browser", "GET", 200),
            ("/probe?q=extractvalue%281,2%29", "Browser", "GET", 200),
            ("/probe?q=%3Csvg%20onload=alert%281%29%3E", "Browser", "GET", 200),
            ("/a/%2e%2e/%2e%2e/etc/passwd", "Browser", "GET", 200),
            ("/probe?q=php://filter/resource=index.php", "Browser", "GET", 200),
            ("/probe?q=%3Bwhoami", "Browser", "GET", 200),
            ("/.env", "Browser", "GET", 404),
            ("/normal", "nuclei/test", "GET", 200),
            ("/normal", "ffuf/test", "GET", 200),
        ] + [("/api/auth/login", "Browser", "POST", 401 if i % 2 else 403) for i in range(5)]
        with tempfile.TemporaryDirectory(prefix="idps-sensor-test-") as temporary:
            work = Path(temporary)
            config = (ROOT / "config/suricata/suricata.yaml").read_text()
            # Extracted packages keep their support files beside the binary.
            support = Path(suricata).resolve().parents[2] / "etc/suricata"
            if support.exists():
                config = config.replace("/etc/suricata/", str(support) + "/")
            configuration = work / "suricata.yaml"
            configuration.write_text(config)
            common = [suricata, "-c", str(configuration), "-S", str(ROOT / "suricata/pbl4.rules"), "-l", str(work)]
            subprocess.run(common + ["-T"], check=True, capture_output=True, text=True, timeout=30)
            capture = work / "requests.pcap"
            write_pcap(capture, requests)
            subprocess.run(common + ["-r", str(capture), "--runmode", "single", "-k", "none"], check=True, capture_output=True, text=True, timeout=30)
            alerts = [json.loads(line) for line in (work / "eve.json").read_text().splitlines()]
            alerts = [event for event in alerts if event.get("event_type") == "alert"]
            sids = {event["alert"]["signature_id"] for event in alerts}
            self.assertTrue(set(range(1000001, 1000010)).issubset(sids), sids)
            normal = [event for event in alerts if event.get("http", {}).get("url") == "/normal" and event["alert"]["signature_id"] not in (1000001, 1000007)]
            self.assertEqual(normal, [])
            failures = [event for event in alerts if event["alert"]["signature_id"] == 1000009]
            self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

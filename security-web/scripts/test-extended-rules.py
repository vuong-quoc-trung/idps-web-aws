#!/usr/bin/env python3
"""Offline PCAP regressions for extended signatures; sends no network traffic."""

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "scripts/test-config-contracts.py"), run_name="pcap_support")
packet = SUPPORT["packet"]
NEW_SIDS = {1000008, 1000010, 1000011, 1000012, 1000013, 1000014}


def request(target="/normal", *, client="192.168.10.10", method="GET", body=b"", content_type=None, at=0):
    return dict(target=target, client=client, method=method, body=body, content_type=content_type, at=at)


def multipart(files):
    chunks = []
    for filename, body in files:
        chunks.append((f'--pbl4-boundary\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                       'Content-Type: application/octet-stream\r\n\r\n').encode() + body + b"\r\n")
    return b"".join(chunks) + b"--pbl4-boundary--\r\n"


def write_transactions(path, requests, keepalive=False):
    frames = []
    sequence = {}
    for index, item in enumerate(requests):
        client, server = item["client"], "192.168.10.1"
        sport = 40000 if keepalive else 40000 + index
        key = (client, sport)
        now = item["at"]
        if key not in sequence:
            frames.extend([(now, packet(client, server, sport, 80, 100, 0, 2)),
                           (now + .0001, packet(server, client, 80, sport, 500, 101, 18)),
                           (now + .0002, packet(client, server, sport, 80, 101, 501, 16))])
            sequence[key] = (101, 501)
        seq, ack = sequence[key]
        headers = f'{item["method"]} {item["target"]} HTTP/1.1\r\nHost: lab\r\nUser-Agent: pbl4-fixture\r\n'
        headers += f'Content-Length: {len(item["body"])}\r\n'
        if item["content_type"]:
            headers += f'Content-Type: {item["content_type"]}\r\n'
        payload = (headers + "\r\n").encode() + item["body"]
        reply = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
        frames.append((now + .0003, packet(client, server, sport, 80, seq, ack, 24, payload)))
        frames.append((now + .0004, packet(server, client, 80, sport, ack, seq + len(payload), 24, reply)))
        sequence[key] = (seq + len(payload), ack + len(reply))
        if not keepalive:
            frames.extend([(now + .0005, packet(client, server, sport, 80, seq + len(payload), ack + len(reply), 17)),
                           (now + .0006, packet(server, client, 80, sport, ack + len(reply), seq + len(payload) + 1, 17))])
    with path.open("wb") as output:
        output.write(struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        for at, frame in sorted(frames, key=lambda entry: entry[0]):
            output.write(struct.pack("<IIII", 1_800_000_000 + int(at), int((at % 1) * 1_000_000), len(frame), len(frame)))
            output.write(frame)


class ExtendedRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suricata = os.environ.get("SURICATA_BIN") or shutil.which("suricata")
        if not cls.suricata:
            raise unittest.SkipTest("Suricata 8 required for offline rule checks")

    def inspect(self, requests, keepalive=False):
        with tempfile.TemporaryDirectory(prefix="pbl4-extended-rules-") as temporary:
            work = Path(temporary)
            config = (ROOT / "config/suricata/suricata.yaml").read_text()
            support = Path(self.suricata).resolve().parents[2] / "etc/suricata"
            if support.exists():
                config = config.replace("/etc/suricata/", str(support) + "/")
            (work / "suricata.yaml").write_text(config)
            write_transactions(work / "requests.pcap", requests, keepalive)
            command = [self.suricata, "-c", str(work / "suricata.yaml"), "-S", str(ROOT / "suricata/pbl4.rules"),
                       "-l", str(work)]
            checked = subprocess.run(command + ["-T"], capture_output=True, text=True, timeout=45)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            command += ["-r", str(work / "requests.pcap"), "--runmode", "single", "-k", "none"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            raw = (work / "eve.json").read_text()
            self.assertNotIn("WEB_SHELL_FIXTURE_CANARY", raw, "request body must not be logged to EVE")
            return [event for line in raw.splitlines() if (event := json.loads(line)).get("event_type") == "alert"]

    def test_time_blind_sqli_uri_and_post_with_benign_controls(self):
        requests = [
            request("/probe?q=pg_sleep%281%29"),
            request("/probe?q=1%3BWAITFOR%20DELAY%20%270%3A0%3A1%27"),
            request("/probe?q=DBMS_PIPE.RECEIVE_MESSAGE%28%27lab%27,1%29"),
            request("/probe?q=benchmark%2810,md5%281%29%29"),
            request("/probe?q=extractvalue%281,2%29"),
            request("/probe", method="POST", content_type="application/x-www-form-urlencoded", body=b"id=1%3BSELECT%20pg_sleep%281%29"),
            request("/probe", method="POST", content_type="application/json", body=b'{"q":"1; WAITFOR DELAY \'00:00:01\'"}'),
            request("/help?sleep=healthy&delay=normal"),
            request("/probe", method="POST", content_type="application/json", body=b'{"sleep":8,"message":"normal sleep schedule"}'),
        ]
        hits = {(event["src_port"] - 40000, event["alert"]["signature_id"]) for event in self.inspect(requests)
                if event["alert"]["signature_id"] in NEW_SIDS}
        self.assertEqual(hits, {(i, 1000008) for i in range(5)} | {(5, 1000013), (6, 1000013)})

    def test_web_shell_requires_executable_filename_and_code(self):
        php = b"<?php /* WEB_SHELL_FIXTURE_CANARY */ system('echo PBL4'); ?>"
        jsp = b'<% Runtime.getRuntime().exec("echo PBL4"); %>'
        fixtures = [[("probe.php", php)], [("probe.jsp", jsp)], [("notes.txt", php)],
                    [("normal.php", b"<?php echo 'hello'; ?>")], [("photo.png", b"PNG benign fixture")],
                    [("normal.php", b"<?php echo 'hello'; ?>"), ("notes.txt", php)]]
        requests = [request("/upload", method="POST", content_type="multipart/form-data; boundary=pbl4-boundary",
                            body=multipart(files)) for files in fixtures]
        hits = {event["src_port"] - 40000 for event in self.inspect(requests) if event["alert"]["signature_id"] == 1000011}
        self.assertEqual(hits, {0, 1}, "different multipart files must not be correlated as one uploaded shell")

    def test_ssrf_destination_context_and_public_url_controls(self):
        requests = [
            request("/fetch?url=http%3A%2F%2F169.254.169.254%2Flatest%2Fmeta-data%2F"),
            request("/fetch?target=http://127.0.0.1:8080/admin"),
            request("/fetch?url=http://10.1.2.3/"),
            request("/fetch?url=http://[::1]/"),
            request("/fetch?url=file:///pbl4-fixture"),
            request("/fetch", method="POST", content_type="application/json", body=b'{"url":"http://metadata.google.internal/"}'),
            request("/fetch", method="POST", content_type="application/x-www-form-urlencoded", body=b"url=http%3A%2F%2Flocalhost%2F"),
            request("/fetch?url=https://example.test/"),
            request("/fetch?url=http://127.0.0.1.example.test/"),
            request("/search?q=http://127.0.0.1/"),
            request("/fetch", method="POST", content_type="application/json", body=b'{"url":"https://example.test/"}'),
        ]
        hits = {(event["src_port"] - 40000, event["alert"]["signature_id"]) for event in self.inspect(requests)
                if event["alert"]["signature_id"] in (1000012, 1000014)}
        self.assertEqual(hits, {(i, 1000012) for i in range(5)} | {(5, 1000014), (6, 1000014)})

    def test_flood_threshold_per_client_keepalive_and_window(self):
        below = [request(at=i * .01) for i in range(99)]
        self.assertFalse(any(event["alert"]["signature_id"] == 1000010 for event in self.inspect(below)))
        above = below + [request(at=.99), request(at=1)]
        for keepalive in (False, True):
            with self.subTest(keepalive=keepalive):
                hits = [event for event in self.inspect(above, keepalive) if event["alert"]["signature_id"] == 1000010]
                self.assertEqual(len(hits), 1)
                offset = datetime.fromisoformat(hits[0]["timestamp"]).timestamp() - 1_800_000_000
                self.assertGreaterEqual(offset, .99)
                self.assertLess(offset, 1.01)
        independent = [request(client=f"192.168.10.{10 + (i % 2)}", at=i * .01) for i in range(100)]
        slow = [request(client="192.168.10.12", at=i * .3) for i in range(100)]
        hits = Counter(event["src_ip"] for event in self.inspect(independent + slow) if event["alert"]["signature_id"] == 1000010)
        self.assertEqual(hits, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)

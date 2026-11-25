import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import correlate
from gateway import EGRESS, PORT, SOURCE


class CorrelationTest(unittest.TestCase):
    def setUp(self):
        self.rid = "a" * 32
        self.generation = "b" * 32
        self.model = correlate.Correlator()
        self.material = {"kid": "fixture", "epoch": "c" * 32, "key": "d" * 64}
        self.started = 1_700_000_000_000_000_000
        self.now = self.started + 100_000_000
        self.route = "/api/auth/csrf"
        date = datetime.fromtimestamp(self.started / 1e9, timezone.utc).isoformat()
        self.edge = {"request_id": self.rid, "http_method": "GET", "uri_path": self.route,
                     "status": 200, "client_ip": "192.0.2.10", "http_host": "example.test",
                     "timestamp": date, "dispatch": "1700000000.000"}
        self.audit = dict(self.edge, status_code=200, source="STUDENT_AUDIT",
                          source_instance="aws-r47", event_id="fixture")
        self.eve = {"src_ip": SOURCE, "dest_ip": EGRESS, "dest_port": PORT,
                    "in_iface": "lo", "proto": "TCP", "event_type": "http",
                    "host": "ws-generation-" + self.generation, "flow_id": 1, "tx_id": 0,
                    "timestamp": date, "http": {"http_method": "GET", "url": self.route, "status": 200}}
        ms = self.started // 1_000_000
        fields = [1, self.material["kid"], self.material["epoch"], "e" * 32, self.edge["client_ip"],
                  self.rid, "GET", "https", self.edge["http_host"], correlate.sha(self.route.encode()),
                  ms, ms + 60000]
        proof = self.wire("ws-request-v1:", fields)
        receipt = self.wire("ws-receipt-v1:", fields[:4] + [correlate.sha(proof.encode()), "accepted", ms])
        self.lua = ["1", "0", proof, receipt, self.edge["client_ip"], self.rid,
                    "https", self.edge["http_host"], self.generation]

    def wire(self, prefix, fields):
        body = base64.urlsafe_b64encode(json.dumps(fields, separators=(",", ":")).encode()).decode().rstrip("=")
        return body + "." + correlate.hmac.digest(bytes.fromhex(self.material["key"]), (prefix + body).encode(), "sha256").hex()

    def add(self, kind, value):
        line = "\t".join(value) if kind == "lua" else json.dumps(value)
        self.model.add(kind, line.encode(), self.now)

    def batch(self):
        self.add("edge", self.edge)
        self.add("audit", self.audit)
        self.add("eve", self.eve)
        self.add("lua", self.lua)

    def rows(self):
        return list(self.model.finalize(self.material, self.now))

    def test_exact_scope_and_duplicate(self):
        self.batch()
        self.batch()
        row, = self.rows()
        self.assertEqual(row["status"], "MATCHED")
        self.assertEqual(row["sources"], ["NGINX", "STUDENT_AUDIT", "SURICATA"])
        self.assertFalse(row["late_event"])
        self.assertEqual(self.rows(), [])

    def test_wrong_sensor_and_bad_mac_do_not_join(self):
        self.eve["host"] = "ws-generation-" + "f" * 32
        self.batch()
        self.assertEqual(self.rows(), [])
        self.lua[2] = self.lua[2].split(".")[0] + "." + "0" * 64
        self.model = correlate.Correlator()
        self.eve["host"] = "ws-generation-" + self.generation
        self.batch()
        self.assertEqual(self.rows(), [])

    def test_late_and_conflict(self):
        self.now = self.started + correlate.CUTOFF_NS
        self.batch()
        match, = self.rows()
        self.assertTrue(match["late_event"])
        self.add("audit", dict(self.audit, status_code=503))
        conflict, = self.rows()
        self.assertEqual(conflict["status"], "AMBIGUOUS")
        self.assertEqual(conflict["sources"], [])
        self.assertEqual(self.rows(), [])

    def test_restart_preserves_committed_cutoff(self):
        self.batch()
        row, = self.rows()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "correlation.jsonl"
            output.write_text(json.dumps(row) + "\n")
            self.model = correlate.Correlator()
            self.now += correlate.CUTOFF_NS
            self.model.recover(output, self.now)
            self.batch()
            self.assertEqual(self.rows(), [])
            self.add("audit", dict(self.audit, status_code=503))
            conflict, = self.rows()
            self.assertEqual(conflict["status"], "AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()

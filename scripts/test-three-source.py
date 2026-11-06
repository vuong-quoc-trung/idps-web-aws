#!/usr/bin/env python3
"""Adversarial correlation fixtures; not human review or independent labels."""

import copy
import hashlib
import hmac
import json
import random
import unittest

from three_source_core import Correlator

T = "2026-11-06T12:00:00+00:00"


def events(n, tx=0, flow=123):
    rid = f"{n:032x}"
    base = {
        "request_id": rid,
        "timestamp": T,
        "http_method": "GET",
        "uri_path": "/api/faculties",
        "status_code": 200,
    }
    return rid, [
        ("NGINX", dict(base, status=200)),
        ("STUDENT_AUDIT", dict(base, event_type="http_request")),
        (
            "SURICATA",
            {
                "timestamp": T,
                "event_type": "http",
                "sensor_instance": "d" * 32,
                "flow_id": flow,
                "tx_id": tx,
                "http": {
                    "http_method": "GET",
                    "url": "/api/faculties",
                    "status": 200,
                    "response_headers": [{"name": "X-Request-Id", "value": rid}],
                },
            },
        ),
    ]


class Tests(unittest.TestCase):
    def test_next_response_cannot_change_current_history_features(self):
        from idps_ai.features.pipeline import FeatureExtractor
        from three_source_core import replay_prefix

        past = {
            "request_key": "past",
            "timestamp": 100.0,
            "client_key": "client",
            "user_key": None,
            "status_code": 200,
            "uri_path": "/api/faculties",
            "http_method": "GET",
        }
        target = dict(past, request_key="target", timestamp=101.0)
        future = dict(past, request_key="future", timestamp=102.0, status_code=500)
        for status in [200, 403, 500]:
            future["status_code"] = status
            ext = FeatureExtractor(query_structure=True, behavior_dynamics=True)
            row, count = replay_prefix(ext, [past, target, future], "target", 101.0)
            values = ext.observe(row)
            self.assertEqual(count, 1)
            self.assertEqual(values["ip_10s_count"], 2.0)
            self.assertEqual(values["ip_10s_error5_ratio"], 0.0)
            self.assertEqual(values["status_2xx"], 1.0)
        with self.assertRaises(RuntimeError):
            replay_prefix(FeatureExtractor(), [past, future], "target", 101.0)

    def test_coarse_nginx_only_history_requires_completed_second(self):
        from idps_ai.features.pipeline import FeatureExtractor
        from three_source_core import UncertainHistoryTime, replay_prefix

        past = {"request_key": "past", "timestamp": 100.0, "sources": ["NGINX"]}
        target = {"request_key": "target", "timestamp": 100.7}
        with self.assertRaises(UncertainHistoryTime):
            replay_prefix(FeatureExtractor(), [past, target], "target", 100.7)
        target["timestamp"] = 101.0
        row, count = replay_prefix(FeatureExtractor(), [past, target], "target", 101.0)
        self.assertEqual(row, target)
        self.assertEqual(count, 1)

    def test_single_and_concurrent_same_route_and_time(self):
        c = Correlator("f" * 32)
        stream = []
        for i in range(12):
            stream += events(i, tx=i)[1]
        random.Random(42).shuffle(stream)
        for s, e in stream:
            c.add(s, e, 1793966400.5)
        for i in range(12):
            r = c.result(f"{i:032x}")
            self.assertEqual(r["status"], "MATCHED")
            self.assertEqual(r["tx_id"], i)

    def test_no_ip_time_or_route_only_match_when_id_missing(self):
        c = Correlator("f" * 32)
        rid, es = events(1)
        for s, e in es[:2]:
            c.add(s, e, 1793966400)
        other = events(2)[1][-1]
        c.add(*other, 1793966400)
        self.assertEqual(c.result(rid)["status"], "MISSING_SOURCE")

    def test_two_ids_claiming_same_flow_transaction_are_ambiguous(self):
        c = Correlator("f" * 32)
        for i in [1, 2]:
            for s, e in events(i, tx=0)[1]:
                c.add(s, e, 1793966400)
        for i in [1, 2]:
            self.assertEqual(c.result(f"{i:032x}")["status"], "AMBIGUOUS")

    def test_duplicate_is_counted_once_but_conflict_is_ambiguous(self):
        c = Correlator("f" * 32)
        rid, es = events(1)
        for s, e in es:
            c.add(s, e, 1793966400)
        c.add(*es[0], 1793966401)
        self.assertEqual(c.result(rid)["duplicate_events"], 1)
        self.assertEqual(c.result(rid)["status"], "MATCHED")
        n = copy.deepcopy(es[0][1])
        n["status"] = 403
        c.add("NGINX", n, 1793966401)
        self.assertEqual(c.result(rid)["status"], "AMBIGUOUS")

    def test_missing_delayed_out_of_order_source_is_explicit(self):
        c = Correlator("f" * 32)
        rid, es = events(1)
        for s, e in es[:2]:
            c.add(s, e, 1793966400)
        self.assertEqual(c.result(rid)["status"], "MISSING_SOURCE")
        c.add(*es[2], 1793966410)
        self.assertEqual(c.result(rid)["status"], "MATCHED")
        self.assertTrue(c.result(rid)["late_event"])

    def test_flow_alert_remains_context(self):
        c = Correlator("f" * 32)
        rid, es = events(1)
        for s, e in es:
            c.add(s, e, 1793966400)
        c.add(
            "SURICATA",
            {
                "event_type": "alert",
                "sensor_instance": "d" * 32,
                "flow_id": 123,
                "alert": {"signature_id": 1000001},
            },
            1793966400,
        )
        r = c.result(rid)
        self.assertEqual(r["flow_context_alerts"], 1)
        self.assertIsNone(r["glu"])
        self.assertNotIn("attack_label", r)

    def test_sensor_generation_prevents_cross_restart_flow_collision(self):
        c = Correlator("f" * 32)
        for i, gen in [(1, "d" * 32), (2, "e" * 32)]:
            _rid, es = events(i, tx=0, flow=123)
            es[-1][1]["sensor_instance"] = gen
            for s, e in es:
                c.add(s, e, 1793966400)
        for i in [1, 2]:
            self.assertEqual(c.result(f"{i:032x}")["status"], "MATCHED")

    def test_hmac_route_check_does_not_accept_redaction_collision(self):
        key = b"x" * 32
        c = Correlator("f" * 32, key)
        rid, es = events(1)
        es[-1][1]["http"]["url"] = "[redacted]"
        es[-1][1]["http"]["path_fingerprint"] = hmac.new(
            key, b"/api/faculties", hashlib.sha256
        ).hexdigest()
        for s, e in es:
            c.add(s, e, 1793966400)
        self.assertEqual(c.result(rid)["status"], "MATCHED")
        other = Correlator("f" * 32, key)
        es[-1][1]["http"]["path_fingerprint"] = hmac.new(
            key, b"/api/other", hashlib.sha256
        ).hexdigest()
        for s, e in es:
            other.add(s, e, 1793966400)
        self.assertEqual(other.result(rid)["status"], "AMBIGUOUS")

    def test_transient_response_headers_are_allowlisted_before_disk(self):
        from idps_ai.data.sensor_decode import redact_eve

        raw = events(1)[1][-1][1]
        raw["payload"] = "SecretCanary"
        raw["http"]["response_headers"] += [
            {"name": "Set-Cookie", "value": "SecretCanary"},
            {"name": "Authorization", "value": "SecretCanary"},
        ]
        safe = redact_eve(raw, query_numeric=True, query_version=2)
        self.assertNotIn("SecretCanary", json.dumps(safe))
        self.assertEqual(len(safe["http"]["response_headers"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

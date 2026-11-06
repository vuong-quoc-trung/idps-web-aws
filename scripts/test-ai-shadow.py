#!/usr/bin/env python3
"""Contract, privacy, overflow and journal tests; no model fit or live traffic."""

import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "worker", Path(__file__).with_name("ai-shadow-worker.py")
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class ShadowTests(unittest.TestCase):
    def message(self):
        return {
            "schema_version": "nginx-ai-1",
            "request_id": "a" * 32,
            "timestamp": datetime.now(UTC).isoformat(),
            "method": "GET",
            "url": "/api/health?token=private-canary",
            "headers": {
                "User-Agent": "test",
                "Accept": "application/json",
                "Content-Type": "",
            },
        }

    def test_only_explicit_transient_contract_is_accepted(self):
        value = self.message()
        self.assertEqual(
            worker.read_message(
                b"<190>Nov 6 12:00:00 ai_shadow: " + json.dumps(value).encode()
            ),
            value,
        )
        for key in ["body", "cookie", "authorization", "score", "rule_signals"]:
            bad = value | {key: "private-canary"}
            with self.assertRaises(ValueError):
                worker.read_message(b"ai_shadow: " + json.dumps(bad).encode())

    def test_truncated_stale_or_wrong_id_cannot_be_scored(self):
        for patch in [
            {"request_id": "not-trusted"},
            {"timestamp": "2020-01-01T00:00:00+00:00"},
            {"url": "https://outside.example/"},
        ]:
            with self.assertRaises(ValueError):
                worker.read_message(
                    b"ai_shadow: " + json.dumps(self.message() | patch).encode()
                )
        with self.assertRaises(ValueError):
            worker.read_message(b"ai_shadow: " + b"x" * 9000)

    def test_frozen_model_receives_header_text_and_explicit_missing_body(self):
        value = self.message()
        value["headers"]["Content-Type"] = "-"
        incoming = worker.model_record(value)
        self.assertEqual(incoming["record_id"], value["request_id"])
        self.assertIsInstance(incoming["http_request"]["headers"], str)
        self.assertEqual(
            incoming["http_request"]["headers"],
            "User-Agent: test\r\nAccept: application/json",
        )
        self.assertIsNone(incoming["http_request"]["body"])

    def test_journal_rotation_remains_bounded_and_replayable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "results.jsonl"
            sink = worker.Journal(path, limit=100)
            for i in range(100):
                sink.append({"event_id": i, "status": "SCORED"})
            files = list(Path(d).iterdir())
            self.assertLessEqual(len(files), 4)
            for file in files:
                self.assertLessEqual(file.stat().st_size, 100)
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                for line in file.read_text().splitlines():
                    json.loads(line)


if __name__ == "__main__":
    unittest.main(verbosity=2)

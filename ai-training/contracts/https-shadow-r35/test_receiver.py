import hashlib
import struct
import sqlite3
import unittest
from receiver import decision, record, initialize, vector_sha


class ReceiptTests(unittest.TestCase):
    def test_signed_zero_has_one_feature_identity(self):
        expected = hashlib.sha256(struct.pack("<100f", *([0.0] * 100))).hexdigest()
        self.assertEqual(vector_sha([-0.0] * 100), expected)

    def test_cutoff_and_clock(self):
        self.assertEqual(decision(0, 1, 999_000_000, 998_999_999), "AVAILABLE")
        self.assertEqual(decision(0, 1, 999_000_001, 999_000_000), "LATE")
        self.assertEqual(decision(10, 9, 20, 11), "CLOCK_INVALID")
        self.assertEqual(decision(0, 1, 20, 1_000_030), "CLOCK_INVALID")

    def test_restart_and_conflict(self):
        db = sqlite3.connect(":memory:")
        initialize(db)
        row = {
            "request_id": "a" * 32,
            "lineage": "owned-run",
            "dispatch_ns": 1,
            "vector_sha256": "a",
            "model_sha256": "b",
        }
        self.assertEqual(record(db, row), "COMMITTED")
        self.assertEqual(record(db, row), "DUPLICATE")
        self.assertEqual(record(db, dict(row, vector_sha256="c")), "QUARANTINED")
        self.assertEqual(db.execute("SELECT conflicted FROM receipts").fetchone(), (1,))


if __name__ == "__main__":
    unittest.main()


def test_partial_worker_response_abstains_within_deadline(tmp_path):
    import time
    from receiver import Scorer

    worker = tmp_path / "slow-worker"
    worker.write_text(
        "#!/usr/bin/python3\nimport os,sys,time\nsys.stdin.buffer.readline()\nos.write(1,b'{')\ntime.sleep(2.5)\n"
    )
    worker.chmod(0o700)
    scorer = Scorer(worker, tmp_path / "unused", "a" * 64, tmp_path / "unused")
    started = time.monotonic()
    try:
        assert scorer.score("GET", "/api/auth/me") is None
        assert scorer.last_inference_error
        assert time.monotonic() - started < 1.5
    finally:
        scorer.close()


def test_private_health_returns_unavailable_then_recovers_without_receipts(tmp_path):
    import http.client
    import os
    import socket
    from contextlib import closing
    import threading
    from unittest.mock import Mock
    from receiver import serve

    path = tmp_path / "receiver.sock"
    scorer = Mock(sha="b" * 64)
    scorer.score.side_effect = [None, ([0.0] * 100, 0.1, {})]
    with (
        closing(sqlite3.connect(":memory:")) as db,
        serve(path, db, scorer, "health", os.getuid()) as server,
    ):
        server.timeout = 2
        for status in (503, 200):
            handler = threading.Thread(target=server.handle_request)
            handler.start()
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(2)
                client.connect(str(path))
                client.sendall(b"GET /healthz HTTP/1.0\r\n\r\n")
                response = http.client.HTTPResponse(client)
                response.begin()
                assert response.status == status and response.read() == b""
                assert response.getheader("X-Model-SHA256") == scorer.sha
            handler.join(timeout=2)
            assert not handler.is_alive()
        assert db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 0

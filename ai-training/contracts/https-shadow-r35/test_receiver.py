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

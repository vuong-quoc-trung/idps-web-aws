"""Fixture-only native admission bridge. The test creates no requests or training samples on disk outside temp."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from native import PROTOCOL, PROFILE, SCHEMA, load_native
from receiver import vector_sha


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "review.json"
        self.obs = self.path.with_name("observations.jsonl")
        self.rows = []
        self.entries = []
        for i in range(4):
            rid = f"{i:032x}"
            part = "FIT" if i < 2 else "TUNING"
            v = [float(i) / 4] * 100
            self.rows.append(
                dict(
                    schema=SCHEMA,
                    profile=PROFILE,
                    lineage=part,
                    request_id=rid,
                    role="TRAIN",
                    receipt_ns=10,
                    dispatch_ns=0,
                    available_ns=12,
                    cutoff_ns=1000000000,
                    guard_ns=1000000,
                    availability="AVAILABLE",
                    status="PROJECTED",
                    source_mask_at_cutoff="N",
                    source_receipts_ns={"N": 12},
                    clock="EDGE_RECEIVER_SAME_KERNEL",
                    features=v,
                    vector_sha256=vector_sha(v),
                )
            )
            self.entries.append(
                dict(
                    campaign=part,
                    request_id=rid,
                    role="TRAIN",
                    partition=part,
                    label=("BENIGN_VERIFIED", "ATTACK_VERIFIED")[i % 2],
                    semantic_review_sha256=sha(("review" + rid).encode()),
                    correlation_proof_sha256=sha(("proof" + rid).encode()),
                    lineage_component_sha256=sha(part.encode()),
                )
            )
        self.m = dict(
            version="https-native-admitted-v1",
            abi=SCHEMA,
            profile=PROFILE,
            task="VERIFIED_HTTP_ATTACK_DETECTION",
            source_role="TRAIN",
            protocol_sha256=sha(PROTOCOL.read_bytes()),
            observation_file=self.obs.name,
            examples=self.entries,
        )
        for field in (
            "admission_report_sha256",
            "protected_lineage_registry_sha256",
            "precollection_split_plan_sha256",
            "usage_grant_sha256",
        ):
            self.m[field] = sha(field.encode())

    def lock(self):
        lines = [(json.dumps(r) + "\n").encode() for r in self.rows]
        self.obs.write_bytes(b"".join(lines))
        for entry, line in zip(self.entries, lines, strict=True):
            entry["receipt_sha256"] = sha(line)
        self.m["observation_sha256"] = sha(self.obs.read_bytes())
        self.path.write_text(json.dumps(self.m))
        return sha(self.path.read_bytes())

    def test_admitted_fixture_and_tampering(self):
        pin = self.lock()
        self.assertEqual(load_native(self.path, pin)[4], 2)
        with self.obs.open("ab") as f:
            f.write(b" ")
        with self.assertRaisesRegex(ValueError, "SHA"):
            load_native(self.path, pin)

    def test_quarantine_across_roles(self):
        self.entries[2]["lineage_component_sha256"] = self.entries[0]["lineage_component_sha256"]
        with self.assertRaisesRegex(ValueError, "overlap"):
            load_native(self.path, self.lock())

    def test_engineering_and_late_receipts(self):
        self.rows[0]["role"] = "ENGINEERING_ONLY"
        with self.assertRaisesRegex(ValueError, "engineering"):
            load_native(self.path, self.lock())
        self.rows[0]["role"] = "TRAIN"
        self.rows[0]["available_ns"] = 1000000000
        with self.assertRaisesRegex(ValueError, "causal"):
            load_native(self.path, self.lock())

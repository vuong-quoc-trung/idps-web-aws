#!/usr/bin/env python3
"""Validate v1 fixtures and optional actual exporter/normalized JSONL (no writes)."""
import ipaddress
import json
import os
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT/'canonical-event-v1.schema.json').read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


class CanonicalSchemaTests(unittest.TestCase):
    def test_schema_and_fixture(self):
        Draft202012Validator.check_schema(SCHEMA)
        for line in (ROOT/'fixtures/student-audit-v1.jsonl').read_text().splitlines():
            VALIDATOR.validate(json.loads(line))

    def test_rejects_plaintext_identity_unknown_extensions_and_version_drift(self):
        fixture = json.loads((ROOT/'fixtures/student-audit-v1.jsonl').read_text())
        for update in [{'username':'raw-user'}, {'password':'secret'}, {'schema_version':'2.0'},
                       {'timestamp':'2026-10-26T07:00:00+07:00'}, {'status_code':999}, {'src_port':70000}]:
            with self.subTest(update=tuple(update)):
                self.assertFalse(VALIDATOR.is_valid(fixture | update))

    def test_actual_java_and_rust_outputs_when_supplied(self):
        files = os.environ.get('CANONICAL_TEST_FILES','')
        if not files:
            self.skipTest('set CANONICAL_TEST_FILES to validate actual runtime JSONL')
        checked = 0
        for filename in files.split(os.pathsep):
            for line in Path(filename).read_text().splitlines():
                value = json.loads(line)
                VALIDATOR.validate(value)
                for key in ['client_ip','peer_ip','dest_ip']:
                    if value.get(key) is not None:
                        ipaddress.ip_address(value[key])
                checked += 1
        self.assertGreater(checked,0)


if __name__=='__main__':
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Mocked nft transaction tests; no sudo, netlink or host firewall changes."""

import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
loader = runpy.run_path(str(ROOT / "pbl4-load-firewall"), run_name="loader_tests")
RULES = (ROOT / "pbl4.nft").read_text()


class FakeNft:
    def __init__(self, exists=False):
        self.exists = exists
        self.calls = []
        self.applied = []
        self.fail_syntax = False
        self.fail_listing = False
        self.race = False
        self.compatible = True

    def __call__(self, *args):
        args = tuple(map(str, args))
        self.calls.append(args)
        if args[:2] == ("-c", "-f"):
            if self.fail_syntax:
                raise subprocess.CalledProcessError(1, args, stderr="syntax failure")
            return ""
        if args == ("-j", "list", "tables"):
            if self.fail_listing:
                raise subprocess.CalledProcessError(1, args, stderr="netlink failure")
            tables = [{"table": {"family": "ip", "name": "docker"}},
                      {"table": {"family": "inet", "name": "ufw"}}]
            if self.exists:
                tables.append({"table": {"family": "inet", "name": "pbl4_demo"}})
            return json.dumps({"nftables": tables})
        if args == ("-j", "list", "table", "inet", "pbl4_demo"):
            return json.dumps({"nftables": [
                {"set": {"name": "protected_ips", "type": "ipv4_addr"}},
                {"set": {"name": "blocked_ips", "type": "ipv4_addr",
                         "flags": ["interval", "timeout"] if self.compatible else []}},
                {"chain": {"name": "input"}}, {"chain": {"name": "forward"}}]})
        if args[0] == "-f":
            batch = Path(args[1]).read_text()
            if self.race:
                self.exists = True
                raise subprocess.CalledProcessError(1, args, stderr="table exists")
            self.applied.append(batch)
            self.exists = True
            return ""
        raise AssertionError(f"Unexpected nft operation: {args}")


class LoaderTests(unittest.TestCase):
    def ensure(self, fake, rules=RULES):
        with contextlib.redirect_stdout(io.StringIO()):
            return loader["ensure_table"](rules, ruleset=ROOT / "pbl4.nft", run=fake)

    def test_absent_table_is_checked_and_created_atomically(self):
        fake = FakeNft()
        self.assertEqual(self.ensure(fake), "loaded")
        self.assertEqual(fake.calls[0][:2], ("-c", "-f"))
        self.assertEqual(len(fake.applied), 1)
        self.assertEqual(fake.applied[0], "create table inet pbl4_demo\n" + RULES)

    def test_existing_table_never_receives_a_mutation(self):
        fake = FakeNft(exists=True)
        self.assertEqual(self.ensure(fake), "preserved")
        self.assertFalse(fake.applied)
        self.assertFalse(any(call[0] == "-f" for call in fake.calls))

    def test_repeated_start_does_not_duplicate_rules(self):
        fake = FakeNft()
        self.ensure(fake)
        self.ensure(fake)
        self.assertEqual(len(fake.applied), 1)

    def test_failed_syntax_aborts_before_any_listing_or_load(self):
        fake = FakeNft()
        fake.fail_syntax = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.ensure(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse(fake.applied)

    def test_failed_listing_is_not_treated_as_absent(self):
        fake = FakeNft()
        fake.fail_listing = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.ensure(fake)
        self.assertFalse(fake.applied)

    def test_concurrent_creation_does_not_append_rules(self):
        fake = FakeNft()
        fake.race = True
        self.assertEqual(self.ensure(fake), "preserved")
        self.assertFalse(fake.applied)

    def test_incompatible_existing_table_is_not_replaced(self):
        fake = FakeNft(exists=True)
        fake.compatible = False
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.ensure(fake)
        self.assertFalse(fake.applied)

    def test_extra_tables_and_global_commands_are_refused(self):
        for text in [RULES + "\ntable ip unrelated {}", "flush ruleset\n" + RULES,
                     RULES.replace("table inet pbl4_demo", "table inet other"),
                     RULES.replace("chain input {", 'include "/tmp/other.nft"\nchain input {'),
                     RULES + "\n}", RULES.replace("set protected_ips", "set other")]:
            with self.subTest(text=text[:45]), self.assertRaises(ValueError):
                loader["validate_scope"](text)

    def test_comments_and_braces_in_quoted_strings_are_accepted(self):
        loader["validate_scope"](RULES.replace('iifname "lo" return',
            'iifname "lo" return comment "braces {} and # text"') + "\n# trailing comment\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)

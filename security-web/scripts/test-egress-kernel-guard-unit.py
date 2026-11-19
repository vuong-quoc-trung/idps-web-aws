#!/usr/bin/env python3
"""Unprivileged policy-rendering tests, not kernel acceptance."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('test-egress-kernel-guard.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

class PolicyTests(unittest.TestCase):
    group = 'ws-egress-test-' + 'a' * 32 + '/allowed'

    def test_both_identity_checks_and_default_deny(self):
        policy = guard.policy(self.group)
        self.assertIn('meta skuid 65534 socket cgroupv2 level 2', policy)
        self.assertIn('ip saddr 127.77.0.1', policy)
        self.assertIn('ip daddr 127.77.0.2 tcp dport 18080 jump egress', policy)
        self.assertIn('counter drop', policy)
        self.assertNotIn('ct state', policy)
        self.assertNotIn('flush ruleset', policy)

    def test_revoked_grant(self):
        policy = guard.policy(self.group, allow=False)
        self.assertNotIn('counter accept', policy)
        self.assertIn('counter drop', policy)

    def test_reject_arbitrary_cgroup_and_injection(self):
        for group in ('system.slice/nginx.service', '../allowed', self.group + '"; accept'):
            with self.assertRaises(ValueError): guard.policy(group)
        with self.assertRaises(ValueError): guard.policy(self.group, -1)

if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Lifecycle/unit tests use mocked nft only, never host firewall."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('manager', Path(__file__).with_name('local-egress-guard.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def test_render_requires_both_and_never_global_flush(self):
        rule = m.render('system.slice/nginx.service', 33, True)
        self.assertIn('meta skuid 33 socket cgroupv2 level 2', rule)
        self.assertIn('counter drop', rule)
        self.assertNotIn('flush', rule)
        for group in ('../x', '/x', 'x;accept', 'x//y'):
            with self.assertRaises(ValueError): m.render(group, 33)
        with self.assertRaises(ValueError): m.render('x', 0)

    def test_snapshot_counters_only_are_ignored(self):
        a = {'nftables': [{'rule': {'handle': 1, 'expr': [{'counter': {'packets': 3}}, {'accept': None}]}}]}
        b = {'nftables': [{'rule': {'handle': 8, 'expr': [{'counter': {'packets': 9}}, {'accept': None}]}}]}
        self.assertEqual(m.canonical(a), m.canonical(b))
        b['nftables'][0]['rule']['expr'][-1] = {'drop': None}
        self.assertNotEqual(m.canonical(a), m.canonical(b))

    def test_deleted_policy_latches_failure_even_when_restored(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'allowed'; path.mkdir()
            command = Mock(return_value=SimpleNamespace(stdout='{"nftables": []}'))
            guard = m.Guard('allowed', 33, command, Path(d))
            guard.arm(); guard.grant()
            self.assertTrue(guard.ready())
            command.side_effect = subprocess.CalledProcessError(1, 'nft')
            self.assertFalse(guard.ready())
            command.side_effect = None
            self.assertFalse(guard.ready())
            self.assertFalse(guard.status()['attribution_ready'])
            with self.assertRaises(RuntimeError): guard.grant()

    def test_cgroup_identity_change_revokes_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'allowed'; path.mkdir()
            command = Mock(return_value=SimpleNamespace(stdout='{"nftables": []}'))
            guard = m.Guard('allowed', 33, command, Path(d))
            guard.arm(); guard.grant()
            guard.identity += 1
            self.assertFalse(guard.ready())

    def test_existing_table_refused(self):
        command = Mock(return_value=SimpleNamespace(stdout=json.dumps({'nftables': [
            {'table': {'family': 'inet', 'name': m.TABLE}}]})))
        guard = m.Guard('allowed', 33, command)
        with self.assertRaises(RuntimeError): guard.arm()
        guard.revoke()
        self.assertFalse(any(call.args[0] == ['nft', '-f', '-'] for call in command.call_args_list))

    def test_lifecycle_fault_stops_and_prevents_reload(self):
        guard = Mock(); guard.ready.return_value = False
        stop, reload = Mock(), Mock()
        lifecycle = m.Lifecycle(guard, Mock(), stop, reload, lambda: True)
        with self.assertRaises(RuntimeError): lifecycle.reload()
        guard.revoke.assert_called_once()
        stop.assert_called_once()
        reload.assert_not_called()

    def test_lifecycle_reload_and_intentional_restart(self):
        guard = Mock(); guard.ready.return_value = True
        start, stop, reload = Mock(), Mock(), Mock()
        lifecycle = m.Lifecycle(guard, start, stop, reload, lambda: True)
        lifecycle.start(); lifecycle.reload(); lifecycle.restart()
        self.assertEqual(start.call_count, 2)
        self.assertEqual(reload.call_count, 1)
        self.assertEqual(stop.call_count, 1)
        self.assertEqual(guard.grant.call_count, 2)

if __name__ == '__main__': unittest.main()

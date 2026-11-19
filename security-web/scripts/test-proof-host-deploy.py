#!/usr/bin/env python3
"""Repository-only tests: temporary filesystem, mocked service/kernel commands."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('deploy', HERE/'deploy-proof-host.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.root = self.work/'root'
        self.bundle = self.work/'bundle'
        self.bundle.mkdir()
        self.calls = []
        for name in m.TARGETS:
            target = self.root/m.TARGETS[name].lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('original ' + name)
            (self.bundle/name).write_text('candidate ' + name)
        (self.bundle/'suricata.yaml').write_text('default-log-dir: /var/log/suricata\n')
        self.deploy = m.Deployment(self.bundle, self.work/'backup', self.run_command, self.root)
        temp_patch = patch.object(self.deploy, 'prepare_temp')
        self.temp_mock = temp_patch.start()
        self.addCleanup(temp_patch.stop)
        for method in ('capture_health', 'restored_http_health'):
            mocker = patch.object(self.deploy, method)
            mocker.start()
            self.addCleanup(mocker.stop)
        checkpoint = patch.object(self.deploy, 'nginx_health')
        self.checkpoint = checkpoint.start()
        self.addCleanup(checkpoint.stop)

    def run_command(self, args):
        self.calls.append(args)
        if args[:2] == ['systemctl', 'show']:
            return '/usr/local/lib/websentinel/proof-nginx-lifecycle.py' if args[2] == 'nginx' else '/etc/suricata/pbl4/local-egress.yaml'
        return 'active\n' if args[:2] == ['systemctl', 'is-active'] else ''

    def test_dedicated_temp_permissions_and_rollback(self):
        from types import SimpleNamespace
        self.deploy.snapshot()
        old = self.root/'var/lib/nginx/body'
        old.mkdir(parents=True, mode=0o700)
        with patch.object(m.life, 'identity', return_value=SimpleNamespace(pw_uid=997, pw_gid=972)), patch.object(m.os, 'chown') as chown:
            m.Deployment.prepare_temp(self.deploy)
            self.assertEqual(chown.call_count, 6)
            self.assertEqual((self.root/'var/lib/websentinel-nginx/proxy').stat().st_mode & 0o777, 0o700)
            with self.assertRaises(ValueError):
                m.Deployment.prepare_temp(self.deploy)
        self.deploy.restore()
        self.assertTrue(old.exists())
        self.assertFalse((self.root/'var/lib/websentinel-nginx').exists())

    def test_key_rotation_changes_epoch_and_key_and_is_private(self):
        key = self.work/'key'
        m.life.rotate(key, os.getgid())
        first = json.loads(key.read_text())
        m.life.rotate(key, os.getgid())
        second = json.loads(key.read_text())
        self.assertNotEqual(first['key'], second['key'])
        self.assertNotEqual(first['epoch'], second['epoch'])
        self.assertEqual(key.stat().st_mode & 0o777, 0o640)
        self.assertEqual(len(second['key']), 64)

    def test_backup_restores_contents_and_absent_files(self):
        absent = self.deploy.target('ca.crt')
        absent.unlink()
        self.deploy.snapshot()
        absent.write_text('new')
        self.deploy.target('site').write_text('changed')
        self.deploy.restore()
        self.assertEqual(self.deploy.target('site').read_text(), 'original site')
        self.assertFalse(absent.exists())
        self.assertIn(['systemctl', 'start', 'nginx'], self.calls)

    def test_corrupt_backup_refuses_before_stopping_services(self):
        self.deploy.snapshot()
        (self.deploy.backup/'site').write_text('tampered')
        self.calls.clear()
        with self.assertRaises(ValueError): self.deploy.restore()
        self.assertEqual(self.calls, [])

    def test_failed_nginx_validation_rolls_back(self):
        failed = False
        def runner(args):
            nonlocal failed
            self.calls.append(args)
            if args == ['/usr/sbin/nginx', '-t'] and not failed:
                failed = True
                raise subprocess.CalledProcessError(1, args)
            if args[:2] == ['systemctl', 'show']:
                return '/usr/local/lib/websentinel/proof-nginx-lifecycle.py' if args[2] == 'nginx' else '/etc/suricata/pbl4/local-egress.yaml'
            return 'active\n'
        self.deploy.runner = runner
        with patch.object(m, 'validate'), self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
            self.deploy.apply()
        self.assertEqual(self.deploy.target('site').read_text(), 'original site')
        self.assertNotIn(['systemctl', 'start', 'suricata'], self.calls[:self.calls.index(['systemctl', 'daemon-reload'])])

    def test_health_failure_rolls_back(self):
        with patch.object(m, 'validate'), patch.object(m.time, 'sleep'), \
             patch.object(self.deploy, 'health', side_effect=RuntimeError('bad TLS')), \
             self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
            self.deploy.apply()
        self.assertEqual(self.deploy.target('site').read_text(), 'original site')

    def test_each_component_failure_restores_original(self):
        failures = (["systemctl", "start", "nginx"],
                    ["systemctl", "start", "suricata"],
                    ["/usr/bin/suricata", "-T", "-c", m.TARGETS['suricata.yaml']])
        for index, failing in enumerate(failures):
            with self.subTest(command=failing):
                self.deploy.backup = self.work/('backup-' + str(index))
                failed = False
                def runner(args):
                    nonlocal failed
                    if args == failing and not failed:
                        failed = True
                        raise subprocess.CalledProcessError(1, args)
                    return self.run_command(args)
                self.deploy.runner = runner
                with patch.object(m, 'validate'), self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
                    self.deploy.apply()
                self.assertEqual(self.deploy.target('site').read_text(), 'original site')

    def test_conflicting_systemd_override_rolls_back(self):
        def runner(args):
            if args[:2] == ['systemctl', 'show']:
                return 'unexpected service command'
            return self.run_command(args)
        self.deploy.runner = runner
        with patch.object(m, 'validate'), self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
            self.deploy.apply()
        self.assertEqual(self.deploy.target('site').read_text(), 'original site')

    def test_rollback_failure_is_reported_separately(self):
        with patch.object(m, 'validate'), patch.object(self.deploy, 'health', side_effect=RuntimeError()), \
             patch.object(m.time, 'sleep'), patch.object(self.deploy, 'restore', side_effect=RuntimeError()), \
             self.assertRaisesRegex(RuntimeError, 'ROLLBACK ALSO FAILED'):
            self.deploy.apply()

    def test_checkpoint_failure_does_not_switch_suricata(self):
        self.checkpoint.side_effect = RuntimeError('HTTP checkpoint failed')
        with patch.object(m, 'validate'), patch.object(m.time, 'sleep'), \
             patch.object(self.deploy, 'restore') as restore, \
             self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
            self.deploy.apply()
        restore.assert_called_once()
        self.assertNotIn(['systemctl', 'stop', 'suricata'], self.calls)
        self.assertNotIn(['systemctl', 'start', 'suricata'], self.calls)

    def test_checkpoint_precedes_sensor_switch(self):
        self.checkpoint.side_effect = lambda: self.calls.append(['CHECKPOINT'])
        with patch.object(m, 'validate'), patch.object(self.deploy, 'health'):
            self.deploy.apply()
        self.assertLess(self.calls.index(['CHECKPOINT']), self.calls.index(['systemctl', 'stop', 'suricata']))

    def test_success_keeps_candidate(self):
        with patch.object(m, 'validate'), patch.object(self.deploy, 'health'):
            self.deploy.apply()
        self.assertEqual(self.deploy.target('site').read_text(), 'candidate site')

    def test_symlink_destination_refused_before_mutation(self):
        target = self.deploy.target('site')
        target.unlink()
        target.symlink_to(self.work/'elsewhere')
        with self.assertRaises(ValueError): self.deploy.snapshot()
        self.assertFalse((self.work/'elsewhere').exists())

    def test_stage_and_dry_run_use_only_temporary_files(self):
        main = self.work/'nginx-base'
        main.write_text('user www-data;\nevents {}\nhttp { include /etc/nginx/conf.d/*.conf; }\n')
        suri = self.work/'suri-base'
        suri.write_text('vars: {address-groups: {HOME_NET: any}}\noutputs:\n - eve-log:\n    enabled: true\n    filename: eve.json\n    types: [{http: {}}, {alert: {}}]\n')
        ca = self.work/'ca'
        ca.write_text('PUBLIC TEST CA')
        staged = self.work/'staged'
        subprocess.run([sys.executable, str(HERE/'stage-proof-host.py'),
            '--output', str(staged), '--nginx-base', str(main), '--suricata-base', str(suri),
            '--student-ca', str(ca), '--edge-ca', str(ca), '--edge-cert', '/tmp/cert',
            '--edge-key', '/tmp/key', '--module', '/tmp/module.so', '--gid', '991'],
            check=True, capture_output=True)
        m.validate(staged)
        output = subprocess.run([sys.executable, str(HERE/'deploy-proof-host.py'), 'dry-run',
            '--bundle', str(staged), '--backup', str(self.work/'not-created')],
            check=True, capture_output=True, text=True)
        self.assertFalse(json.loads(output.stdout)['writes'])
        self.assertFalse((self.work/'not-created').exists())
        self.assertIn('proxy_ssl_name student.lab;', (staged/'site').read_text())

    def test_bundle_hash_mismatch_refused(self):
        (self.bundle/'manifest.json').write_text(json.dumps({'sha256': dict.fromkeys(m.TARGETS, 'wrong')}))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): m.read_bundle(self.bundle)

if __name__ == '__main__': unittest.main(verbosity=2)

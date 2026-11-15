#!/usr/bin/env python3
"""Offline PCAP tests only; no capture, network requests or host mutations."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

profile = load('profile', 'prepare-suricata-post-proxy.py')
fixtures = load('fixtures', 'test-extended-rules.py')

class ProfileTests(unittest.TestCase):
    def test_passive_and_original_unchanged(self):
        original = yaml.safe_load((HERE.parent / 'config/suricata/suricata.yaml').read_text())
        old = json.dumps(original, sort_keys=True)
        result = profile.render(original)
        self.assertEqual(json.dumps(original, sort_keys=True), old)
        self.assertEqual([i['interface'] for i in result['af-packet']], ['vmnet3'])
        self.assertNotIn('copy-mode', result['af-packet'][0])
        self.assertFalse(result['stream']['inline'])
        self.assertEqual(result['rule-files'], original['rule-files'])
        eve = next(o['eve-log'] for o in result['outputs'] if 'eve-log' in o)
        self.assertEqual(eve['xff']['mode'], 'extra-data')

    @unittest.skipUnless(shutil.which('suricata'), 'Suricata required')
    def test_keepalive_transaction_identity_and_http_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            base = yaml.safe_load((HERE.parent / 'config/suricata/suricata.yaml').read_text())
            config = profile.render(base)
            config['classification-file'] = '/etc/suricata/classification.config'
            config['reference-config-file'] = '/etc/suricata/reference.config'
            config['default-log-dir'] = str(work)
            config['unix-command'] = {'enabled': False}
            (work / 'config.yaml').write_text('%YAML 1.1\n---\n' + yaml.safe_dump(config, sort_keys=False))
            targets = ['/api/probe?q=%27%20OR%201=1', '/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E', '/api/probe?file=../../etc/passwd', '/api/probe']
            requests = []
            for i, target in enumerate(targets):
                rid = f'{i+1:032x}'
                raw = (f'GET {target} HTTP/1.1\r\nHost: lab\r\nX-Forwarded-For: 192.168.10.{10+i}\r\n'
                       f'X-Request-Id: {rid}\r\nCookie: BODY_SECRET_CANARY\r\nContent-Length: 0\r\n\r\n').encode()
                row = fixtures.request(client='192.168.20.1', raw=raw, at=i)
                row['server'] = '192.168.20.10'
                requests.append(row)
            fixtures.write_transactions(work / 'input.pcap', requests, keepalive=True)
            command = ['suricata', '-c', str(work / 'config.yaml'), '-S', os.environ.get('SURICATA_RULES', str(HERE.parent / 'suricata/pbl4.rules')), '-l', str(work)]
            for extra in [['-T'], ['-r', str(work / 'input.pcap'), '--runmode', 'single', '-k', 'none']]:
                result = subprocess.run(command + extra, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            raw = (work / 'eve.json').read_text()
            self.assertNotIn('BODY_SECRET_CANARY', raw)
            events = [json.loads(line) for line in raw.splitlines()]
            alerts = [e for e in events if e['event_type'] == 'alert']
            self.assertTrue({1000002, 1000003, 1000004}.issubset({e['alert']['signature_id'] for e in alerts}))
            for e in alerts:
                self.assertEqual(e['src_ip'], '192.168.20.1')
                self.assertEqual(e['dest_ip'], '192.168.20.10')
                self.assertEqual(e.get('xff', e['alert'].get('xff')), '192.168.10.' + str(10 + e['tx_id']))
            http = [e for e in events if e['event_type'] == 'http']
            self.assertEqual(len(http), 4)
            for e in http:
                self.assertEqual(e['http']['xff'], '192.168.10.' + str(10 + e['tx_id']))
                self.assertEqual(e['http']['status'], 404)
                self.assertNotIn('request_id', e['http'])
            self.assertEqual(len({e['flow_id'] for e in http}), 1)

if __name__ == '__main__':
    unittest.main(verbosity=2)

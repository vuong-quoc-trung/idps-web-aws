#!/usr/bin/env python3
"""Optional egress tests: disposable NGINX/TLS mock, no production traffic."""
import importlib.util
import ssl
import subprocess
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

host = load('host', 'test-nginx-host.py')
prepare = host.prepare
sensor = load('sensor', 'prepare-suricata-post-proxy.py')

class OptionsTests(unittest.TestCase):
    def test_persistence_and_rollback(self):
        options = prepare.egress_options('/tmp/ca.pem', 'student.test')
        site, _ = prepare.render(tls_cert='/tmp/edge.crt', tls_key='/tmp/edge.key', egress=options)
        args = SimpleNamespace(egress_ca=None, egress_name=None, egress_port=None, disable_egress=False)
        self.assertEqual(prepare.select_egress(args, site), options)
        self.assertIn('proxy_bind 127.77.0.1;', site)
        self.assertEqual(site.count('tag=ai_shadow'), 1)
        args.disable_egress = True
        self.assertIsNone(prepare.select_egress(args, site))
        self.assertIn('proxy_pass http://192.168.20.10:80;', prepare.render()[0])
        for bad in ['student;include', 'bad name', '']:
            with self.assertRaises(ValueError): prepare.egress_options('/tmp/ca', bad)
        with self.assertRaises(ValueError): prepare.render(egress=options)
        with self.assertRaises(ValueError): prepare.egress_options('/tmp/ca', 'student.test', 0)

    def test_sensor_profile(self):
        base = {'vars': {'address-groups': {}}, 'rule-files': ['pbl4.rules'],
                'outputs': [{'eve-log': {'enabled': True, 'types': [{'http': {}}, {'alert': {}}]}}]}
        old = sensor.render(base)
        new = sensor.render(base, 'local-egress')
        self.assertEqual(old['af-packet'][0]['interface'], 'vmnet3')
        self.assertEqual(new['af-packet'][0]['interface'], 'lo')
        self.assertIn('src port 18080', new['af-packet'][0]['bpf-filter'])
        self.assertEqual(new['rule-files'], base['rule-files'])
        self.assertEqual(old['outputs'], new['outputs'])
        self.assertNotIn('af-packet', base)
        self.assertFalse(new['stream']['inline'])

    def test_local_sensor_syntax(self):
        import shutil
        import tempfile
        import yaml
        if not shutil.which('suricata'):
            self.skipTest('Suricata unavailable')
        base = yaml.safe_load((HERE.parent / 'config/suricata/suricata.yaml').read_text())
        config = sensor.render(base, 'local-egress')
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            config['default-log-dir'] = str(work)
            config['classification-file'] = '/etc/suricata/classification.config'
            config['reference-config-file'] = '/etc/suricata/reference.config'
            config['unix-command'] = {'enabled': False}
            path = work / 'suricata.yaml'
            path.write_text('%YAML 1.1\n---\n' + yaml.safe_dump(config))
            result = subprocess.run(['suricata', '-T', '-c', str(path), '-S',
                str(HERE.parent / 'suricata/pbl4.rules'), '-l', str(work)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

class EgressTests(host.HostConfigTests):
    @classmethod
    def config_snippet(cls):
        cert, key = cls.work / 'upstream.crt', cls.work / 'upstream.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-subj', '/CN=student.test', '-addext',
                        'subjectAltName=DNS:student.test,IP:127.0.0.1', '-keyout', str(key), '-out', str(cert)],
                        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        cls.upstream.socket = context.wrap_socket(cls.upstream.socket, server_side=True)
        site, formats = prepare.render(host='127.0.0.1', upstream='127.0.0.1',
            tls_cert=str(cert), tls_key=str(key), egress=prepare.egress_options(str(cert), 'student.test', cls.upstream.server_port))
        import socket
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            cls.egress_port = reservation.getsockname()[1]
        site = site.replace('127.77.0.2:18080', f'127.77.0.2:{cls.egress_port}')
        site = site.replace('listen 127.0.0.1:80;', f'listen 127.0.0.1:{cls.port};')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            cls.tls_port = reservation.getsockname()[1]
        cls.cert = cert
        site = site.replace('listen 127.0.0.1:443 ssl;', f'listen 127.0.0.1:{cls.tls_port} ssl;')
        site = site.replace('syslog:server=unix:/run/pbl4-ai-shadow/nginx.sock,tag=ai_shadow,nohostname', str(cls.work / 'telemetry.log'))
        site = site.replace('    location / {\n        proxy_pass https://',
            '    location = /bad-name { proxy_pass https://127.0.0.1:' + str(cls.upstream.server_port) + '; '
            'proxy_ssl_verify on; proxy_ssl_trusted_certificate ' + str(cert) + '; '
            'proxy_ssl_name wrong.test; }\n    location / {\n        proxy_pass https://')
        return formats + '\n' + site

    def test_https_both_segments(self):
        import http.client
        connection = http.client.HTTPSConnection('127.0.0.1', self.tls_port,
            context=ssl.create_default_context(cafile=str(self.cert)), timeout=3)
        connection.request('GET', '/api/probe')
        response = connection.getresponse()
        self.assertEqual(response.status, 204)
        self.assertEqual(self.upstream_headers[-1]['X-Forwarded-Proto'], 'https')
        self.assertEqual(self.upstream_headers[-1]['X-Request-Id'], response.getheader('X-Request-Id'))
        response.read()
        connection.close()

    def test_identity_reaches_tls_upstream(self):
        status, ids, _, _ = self.request('/api/probe', headers={'X-Forwarded-For':'203.0.113.99', 'X-Request-Id':'forged'})
        self.assertEqual(status, 204)
        headers = self.upstream_headers[-1]
        self.assertEqual(headers['X-Forwarded-For'], '127.0.0.1')
        self.assertEqual(headers['X-Request-Id'], ids[0])
        self.assertEqual(headers['X-Forwarded-Proto'], 'http')

    def test_bound_source_can_forge_identity_security_finding(self):
        # This is a vulnerability reproduction, NOT an acceptance PASS.
        import http.client
        forged_id = 'b' * 32
        connection = http.client.HTTPConnection('127.77.0.2', self.egress_port,
            source_address=('127.77.0.1', 0), timeout=3)
        connection.request('GET', '/api/probe?q=%3Cscript%3Ealert(1)%3C/script%3E',
            headers={'X-Request-Id': forged_id, 'X-Forwarded-Proto': 'https',
                     'X-Forwarded-For': '192.168.10.99', 'X-Real-IP': '192.168.10.99'})
        response = connection.getresponse()
        status = response.status
        response.read()
        connection.close()
        observed = self.upstream_headers[-1]
        self.assertEqual(status, 204)
        self.assertEqual(observed['X-Forwarded-For'], '192.168.10.99')
        self.assertEqual(observed['X-Request-Id'], forged_id)
        print('SECURITY_FINDING ' + json.dumps({'boundary': 'FAIL',
            'source': '127.77.0.1', 'egress_status': status,
            'upstream_xff': observed['X-Forwarded-For'],
            'upstream_request_id': observed['X-Request-Id'],
            'scope': 'temporary TLS mock; no Suricata capture'}), flush=True)

    def test_wrong_tls_identity_fails_closed(self):
        before = len(self.upstream_headers)
        self.assertEqual(self.request('/bad-name')[0], 502)
        self.assertEqual(len(self.upstream_headers), before)

    def test_local_acl_rejects_other_source(self):
        import http.client
        connection = http.client.HTTPConnection('127.77.0.2', self.egress_port, timeout=3)
        connection.request('GET', '/', headers={'X-Request-Id':'a'*32, 'X-Forwarded-Proto':'https', 'X-Forwarded-For':'192.168.10.10'})
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        connection.close()

if __name__ == '__main__': unittest.main(verbosity=2)

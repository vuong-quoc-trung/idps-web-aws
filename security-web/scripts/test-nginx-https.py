#!/usr/bin/env python3
"""Disposable TLS proxy tests; no production service, certificate or traffic changes."""
import http.client
import importlib.util
from pathlib import Path
import ssl
import subprocess
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('host_tests', HERE / 'test-nginx-host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class TLSRenderingTests(unittest.TestCase):
    def test_sync_roundtrip_and_ai_preservation(self):
        site, formats = host.prepare.render(tls_cert='/etc/pbl4/tls/lab.crt', tls_key='/etc/pbl4/tls/lab.key')
        self.assertEqual(host.prepare.existing_tls(site), ('/etc/pbl4/tls/lab.crt', '/etc/pbl4/tls/lab.key'))
        cert, key = host.prepare.existing_tls(site)
        self.assertEqual(host.prepare.render(tls_cert=cert, tls_key=key), (site, formats))
        self.assertEqual(host.installer.patch_site(site), site)
        self.assertIn('listen 192.168.10.1:80;', site)
        self.assertIn('listen 192.168.10.1:443 ssl;', site)
        self.assertIn('proxy_pass http://192.168.20.10:80;', site)
        self.assertNotIn('Strict-Transport-Security', site)
        self.assertNotIn('return 301', site)
        self.assertEqual(host.prepare.existing_tls(host.prepare.render()[0]), (None, None))

    def test_invalid_and_unmanaged_tls(self):
        for cert, key in [('/tmp/a', None), ('/tmp/a;include', '/tmp/key'), ('relative', '/tmp/key')]:
            with self.assertRaises(ValueError):
                host.prepare.render(tls_cert=cert, tls_key=key)
        with self.assertRaises(ValueError):
            host.prepare.existing_tls('listen 192.168.10.1:443 ssl;')
        site, _ = host.prepare.render(lan='192.168.50.8', tls_cert='/tmp/a', tls_key='/tmp/b')
        self.assertIn('listen 192.168.50.8:443 ssl;', site)


class HTTPSConfigTests(host.HostConfigTests):
    @classmethod
    def config_snippet(cls):
        cls.cert = cls.work / 'lab.crt'
        key = cls.work / 'lab.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-subj', '/CN=WebSentinel test',
                        '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(key), '-out', str(cls.cert)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        site = super().config_snippet()
        rendered, _ = host.prepare.render(host='127.0.0.1', tls_cert=str(cls.cert), tls_key=str(key))
        tls = rendered.split('# PBL4 HTTPS BEGIN', 1)[1].split('# PBL4 HTTPS END', 1)[0]
        import socket
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            cls.http_port = reservation.getsockname()[1]
        site = site.replace(f'listen 127.0.0.1:{cls.port};', f'listen 127.0.0.1:{cls.http_port};')
        site = site.replace('# HTTPS disabled (HTTP retained)',
                            tls.replace('127.0.0.1:443', f'127.0.0.1:{cls.port}'))
        return site.replace('location / {', 'location = /health { return 200 "ok"; }\nlocation / {')

    def request(self, *args, **kwargs):
        # Reuse the same HTTP/identity/logging assertions over verified TLS.
        factory = lambda address, port, timeout: http.client.HTTPSConnection(
            address, port, timeout=timeout, context=ssl.create_default_context(cafile=str(self.cert)))
        with patch.object(host.contracts.http.client, 'HTTPConnection', side_effect=factory):
            return super().request(*args, **kwargs)

    def test_http_retained_without_redirect(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.http_port, timeout=3)
        connection.request('GET', '/health')
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.getheader('Location'))
        self.assertIsNone(response.getheader('Strict-Transport-Security'))
        response.read()
        connection.close()

    def test_tls_versions_and_ip_validation(self):
        import socket
        for version in [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3]:
            ctx = ssl.create_default_context(cafile=str(self.cert))
            ctx.minimum_version = ctx.maximum_version = version
            with socket.create_connection(('127.0.0.1', self.port)) as raw:
                with ctx.wrap_socket(raw, server_hostname='127.0.0.1') as secure:
                    self.assertIn(secure.version(), ['TLSv1.2', 'TLSv1.3'])
        ctx = ssl.create_default_context(cafile=str(self.cert))
        with socket.create_connection(('127.0.0.1', self.port)) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):
                ctx.wrap_socket(raw, server_hostname='192.168.10.1')
        self.assertEqual(self.request('/health')[0], 200)
        self.assertEqual(self.request('/api/auth/login')[0], 401)
        self.assertEqual(self.upstream_headers[-1]['X-Forwarded-Proto'], 'https')


if __name__ == '__main__':
    unittest.main(verbosity=2)

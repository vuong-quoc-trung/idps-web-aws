import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('proof', Path(__file__).with_name('prepare-proof-egress.py'))
proof = importlib.util.module_from_spec(spec); spec.loader.exec_module(proof)

class CandidateTests(unittest.TestCase):
    def candidate(self):
        return proof.render('/tmp/edge.crt','/tmp/edge.key','/tmp/ca.crt','student.lab',
                            '/etc/nginx/proof/proof.js','/etc/nginx/proof/key.json',991)
    def test_proof_and_tls_and_identity_preserved(self):
        site, formats = self.candidate()
        self.assertEqual(site.count('proxy_set_header X-WS-Proof $probe_signed;'),1)
        self.assertEqual(site.count('if ($probe_verified != ok) { return 403; }'),1)
        self.assertIn('proxy_set_header X-WS-Proof "";',site)
        self.assertIn('proxy_hide_header X-WS-Receipt;',site)
        self.assertIn('proxy_ssl_verify on;',site)
        self.assertIn('proxy_ssl_name student.lab;',site)
        self.assertIn('proxy_pass https://192.168.20.10:443;',site)
        self.assertEqual(site.count('tag=ai_shadow'),1)
        self.assertIn('limit_req zone=pbl4_requests',site)
        self.assertIn('js_var $probe_key_gid 991;',formats)
        self.assertIn('proxy_pass http://pbl4_proof_egress;', site)
        self.assertIn('keepalive 16;', formats)
        self.assertIn('proxy_set_header Connection "";', site)
        self.assertNotIn('X-Test-Worker',site)
        self.assertNotIn('/api/no-receipt',site)
    def test_deferred_ai_retains_restore_path_without_active_sink(self):
        site, formats = proof.render('/tmp/c','/tmp/k','/tmp/ca','student.lab',
                                     '/tmp/js','/tmp/key',991,'deferred')
        active = '\n'.join(line for line in site.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('tag=ai_shadow', active)
        self.assertIn('/run/pbl4-ai-shadow/nginx.sock', site)
        self.assertIn('access_log /var/log/nginx/access.log', active)
        self.assertIn('proxy_ssl_verify on;', active)
        self.assertIn('$probe_verified', active)
        self.assertIn('pbl4_ai_telemetry', formats)

    def test_legacy_sync_cannot_remove_proof(self):
        site,_ = self.candidate()
        args=SimpleNamespace(disable_egress=True,egress_ca=None,egress_name=None,egress_port=None)
        with self.assertRaises(ValueError): proof.host.select_egress(args,site)
    def test_unsafe_paths_and_identity_refused(self):
        with self.assertRaises(ValueError):
            proof.render('/tmp/a;bad','/tmp/k','/tmp/ca','student.lab','/tmp/js','/tmp/key',991)
        with self.assertRaises(ValueError):
            proof.render('/tmp/a','/tmp/k','/tmp/ca','student.lab','/tmp/js','/tmp/key',0)
if __name__=='__main__': unittest.main(verbosity=2)

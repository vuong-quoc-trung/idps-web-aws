#!/usr/bin/env python3
"""Offline adapter tests: no service operations, DB, network or model inference."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
def load(path, name):
    spec = importlib.util.spec_from_file_location(name,path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
installer = load(Path(__file__).with_name("install-ai-shadow-host.py"),"installer")
supervisor = load(ROOT/"scripts/ai-host-supervisor.py","supervisor")
SITE = """server {
 listen 192.168.10.1:80;
 access_log /var/log/nginx/access.log combined;
 location / {
 proxy_pass http://192.168.20.10;
 proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
 }
}
"""

class HostTests(unittest.TestCase):
    def test_patch_is_idempotent_and_preserves_vm(self):
        output=installer.patch_site(SITE)
        self.assertEqual(installer.patch_site(output),output)
        self.assertIn("listen 192.168.10.1:80;",output)
        self.assertIn("proxy_pass http://192.168.20.10;",output)
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;",output)
        self.assertIn("proxy_set_header X-Request-Id $request_id;",output)
        self.assertIn("proxy_set_header Forwarded '';",output)
        self.assertIn("/var/log/nginx/access.log pbl4_ai_access",output)
        self.assertNotIn("127.0.0.1:8080",output)

    def test_unknown_layout_is_rejected(self):
        for text in [SITE.replace("192.168.20.10","127.0.0.1:8080"),
                     SITE.replace("combined","custom"),SITE+"server {}",
                     SITE.replace("location / {","location /api/ {")]:
            with self.assertRaises(RuntimeError):
                installer.patch_site(text)

    def test_env_retains_unrelated_secrets_without_exposing_them(self):
        before="DATABASE_URL=private-fixture\nAUTO_BLOCK=true\n"
        after=installer.env_text(before)
        self.assertIn("DATABASE_URL=private-fixture",after)
        self.assertIn("AUTO_BLOCK=false",after)
        self.assertIn("ENFORCEMENT_MODE=OFF",after)
        self.assertEqual(installer.env_text(after),after)

    def test_unit_limits_permissions_and_restart(self):
        text=installer.unit("backend","www-data",Path("/venv/bin/python"),Path("/opt/package"))
        for expected in ["User=backend","Group=www-data","RuntimeDirectoryMode=0710",
                         "--socket-mode 620","RestartPreventExitStatus=78","MemoryMax=2G",
                         "RestrictAddressFamilies=AF_UNIX","NoNewPrivileges=true"]:
            self.assertIn(expected,text)
        self.assertNotIn("User=root",text)

    def test_formats_keep_rules_and_omit_sensitive_telemetry_fields(self):
        text=installer.formats()
        self.assertIn('"rule_signals"',text)
        telemetry=text.split("log_format pbl4_ai_telemetry",1)[1]
        for field in ["$request_body","$http_cookie","$http_authorization","$request_uri","$args"]:
            self.assertNotIn(field,telemetry)
        self.assertIn('"request_id":"$request_id"',telemetry)

    def test_backup_restore_preserves_bytes_and_mode(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); old=base/"old"; new=base/"new"; backup=base/"backup"
            backup.mkdir(); old.write_text("original"); old.chmod(0o600)
            records=installer.snapshot(backup,[old,new])
            installer.atomic(old,b"modified",0o644)
            installer.atomic(new,b"new",0o644)
            installer.restore(records)
            self.assertEqual(old.read_text(),"original")
            self.assertEqual(old.stat().st_mode & 0o777,0o600)
            self.assertFalse(new.exists())

    def test_heartbeat_reader_tolerates_rotation_and_partial_line(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"results.jsonl"
            self.assertIsNone(supervisor.latest(p))
            p.write_text('{"kind":"heartbeat","status":"READY"}\n{"broken"')
            self.assertEqual(supervisor.latest(p)["status"],"READY")

if __name__=="__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Isolated host config checks. No production requests/services/files."""
import importlib.util
from pathlib import Path
import json
import unittest

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare", "prepare-nginx-host.py")
installer = load("installer", "install-ai-shadow-host.py")
contracts = load("contracts", "test-config-contracts.py")


class RenderingTests(unittest.TestCase):
    def test_defaults_and_shared_formats(self):
        site, formats = prepare.render()
        self.assertIn("listen 192.168.10.1:80;", site)
        self.assertIn("proxy_pass http://192.168.20.10:80;", site)
        self.assertNotIn("127.0.0.1:8080", site)
        self.assertEqual(formats, installer.formats())
        self.assertEqual(installer.patch_site(site), site)
        self.assertEqual(prepare.render(), (site, formats))

    def test_lan_and_validation(self):
        site, _ = prepare.render(lan="192.168.50.8")
        self.assertIn("listen 192.168.50.8:80;", site)
        self.assertEqual(installer.patch_site(site), site)
        self.assertEqual(prepare.render(lan="192.168.10.1")[0].count("listen "), 1)
        for bad in ["0.0.0.0", "224.0.0.1", "lab; include /tmp/x;", "example.org"]:
            with self.assertRaises(ValueError):
                prepare.render(lan=bad)

    def test_local_signatures_remain_identical(self):
        local = (prepare.ROOT / "nginx/pbl4-local-demo.conf").read_text()
        local = local.split("\n", 1)[1].split("# Local services are preferred;")[0]
        local = local.replace("idps_", "pbl4_host_").replace("log_format pbl4_host_json", "log_format pbl4_ai_access")
        self.assertEqual(local, (prepare.ROOT / "nginx/pbl4-access.conf").read_text())


class HostConfigTests(contracts.EdgeConfigTests):
    @classmethod
    def config_snippet(cls):
        site, formats = prepare.render(host="127.0.0.1", upstream="127.0.0.1")
        site = site.replace("listen 127.0.0.1:80;", f"listen 127.0.0.1:{cls.port};")
        site = site.replace("http://127.0.0.1:80;", f"http://127.0.0.1:{cls.upstream.server_port};")
        # Same telemetry format/filter; disposable file sink instead of real worker.
        site = site.replace("syslog:server=unix:/run/pbl4-ai-shadow/nginx.sock,tag=ai_shadow,nohostname",
                            str(cls.work / "telemetry.log"))
        return formats + "\n" + site

    def test_local_first_then_backup_on_connection_refusal(self):
        # Host has exactly one VM upstream; local failover belongs to local-demo tests.
        site, _ = prepare.render()
        self.assertNotIn("backup;", site)
        self.assertEqual(site.count("proxy_pass"), 1)

    def test_method_and_sensitive_path_policy(self):
        for target, method, expected in [("/api/probe", "TRACE", 405), ("/.env", "GET", 403),
                                         ("/.git/config", "GET", 403), ("/actuator/env", "GET", 403)]:
            before = len(self.upstream_headers)
            status, ids, event, _ = self.request(target, method=method)
            self.assertEqual(status, expected)
            self.assertEqual(ids, [event["request_id"]])
            self.assertEqual(len(self.upstream_headers), before)

    def test_ai_metadata_identity_and_redaction(self):
        canary = "PRIVATE_CANARY"
        _, _, event, _ = self.request("/api/auth/me?token=" + canary, headers={
            "Cookie": canary, "Authorization": "Bearer " + canary,
            "Accept": "Bearer " + canary, "User-Agent": "Bearer " + canary})
        raw = (self.work / "telemetry.log").read_text().splitlines()[-1]
        telemetry = json.loads(raw)
        self.assertEqual(telemetry["request_id"], event["request_id"])
        self.assertEqual(telemetry["url"], "/api/redacted")
        self.assertEqual(telemetry["schema_version"], "nginx-ai-1")
        self.assertNotIn(canary, raw)
        self.assertEqual(set(telemetry["headers"]), {"User-Agent", "Accept", "Content-Type"})
        before = (self.work / "telemetry.log").read_text()
        self.request("/normal")
        self.assertEqual((self.work / "telemetry.log").read_text(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

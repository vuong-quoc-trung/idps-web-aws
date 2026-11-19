import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "render", Path(__file__).with_name("prepare-proof-egress.py")
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class ShadowTests(unittest.TestCase):
    args = (
        "/lab/cert",
        "/lab/key",
        "/lab/ca",
        "student.test",
        "/lab/proof.js",
        "/lab/key.json",
        991,
    )

    def test_optional_private_mirror_only_on_edge(self):
        site, formats = renderer.render(
            *self.args, shadow_socket="/run/private/model.sock"
        )
        self.assertEqual(site.count("mirror /_idps_https_projection;"), 1)
        self.assertIn("mirror_request_body off;", site)
        self.assertIn("proxy_pass_request_headers off;", site)
        self.assertIn("proxy_pass_request_body off;", site)
        self.assertIn("proxy_set_header X-WS-Proof $probe_signed;", site)
        self.assertIn("proxy_ssl_verify on;", site)
        self.assertIn("https:/api/", formats)
        self.assertNotIn("mirror /", renderer.render(*self.args)[0])
        for socket, mode in [
            ("/run/ok.sock", "deferred"),
            ("/run/bad;path", "enabled"),
        ]:
            with self.assertRaises(ValueError):
                renderer.render(*self.args, ai_mode=mode, shadow_socket=socket)


if __name__ == "__main__":
    unittest.main()

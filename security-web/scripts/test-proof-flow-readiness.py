import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "flow", Path(__file__).with_name("proof-flow-readiness.py")
)
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)


class RotationTests(unittest.TestCase):
    def test_only_private_leg_established_client_sockets_count(self):
        def endpoint(ip, port):
            raw = int.from_bytes(bytes(ip), sys.byteorder)
            return f"{raw:08X}:{port:04X}"

        a = endpoint((127, 77, 0, 1), 32100)
        b = endpoint((127, 77, 0, 2), 18080)

        def row(src, dst, state):
            return f"1: {src} {dst} {state} 0 0 0 0 0 123"

        rows = [
            "header",
            row(a, b, "01"),
            row(b, a, "01"),
            row(a, b, "06"),
            row(a, endpoint((127, 0, 0, 1), 443), "01"),
        ]
        self.assertEqual(
            flow.established(rows),
            {(("127.77.0.1", 32100), ("127.77.0.2", 18080), "123")},
        )

    def test_new_socket_does_not_extend_old_deadline(self):
        with patch.object(flow, "current", side_effect=[{"old"}, {"new"}]):
            result = flow.wait_for_rotation({"old"}, 1)
        self.assertEqual(result["remaining_old_connections"], 0)
        with patch.object(flow, "current", return_value={"old"}):
            with self.assertRaises(TimeoutError):
                flow.wait_for_rotation({"old"}, 0.001)


if __name__ == "__main__":
    unittest.main()

"""Defensive regressions for the ingress proof and its authorization lifetime."""

from unittest import TestCase, main
from unittest.mock import Mock, patch
import time

from r60_ingress import Ingress, PEER, PORT, PROOF_SECONDS, SERVER, established, same_request


class IngressProofTests(TestCase):
    local = SERVER, PORT
    remote = PEER, 49900
    row = f"0: 0138FE0A:{PORT:04X} 0238FE0A:C2EC 01 0:0 0:0 0 0 0 71"

    def test_exact_owned_socket_only(self):
        self.assertEqual(established([self.row], {71}, self.local, self.remote), 71)
        for rows, owned, remote in (
            ([self.row, self.row], {71}, self.remote),
            ([self.row], {70}, self.remote),
            ([self.row], {71}, (PEER, 49899)),
            ([self.row.replace(" 01 ", " 06 ")], {71}, self.remote),
            ([self.row[:-2] + "0"], {0}, self.remote),
        ):
            with self.subTest(rows=rows, owned=owned, remote=remote):
                self.assertIsNone(established(rows, owned, self.local, remote))

    def test_request_id_cannot_authorize_another_address_or_port(self):
        request_id = "a" * 32
        row = {"request_id": request_id, "peer": list(self.remote), "local": list(self.local), "status": 204}
        self.assertTrue(same_request(row, request_id, self.local, self.remote))
        self.assertFalse(same_request(row, request_id, self.local, ("192.0.2.60", 49900)))
        self.assertFalse(same_request(row, request_id, self.local, (PEER, 49899)))
        self.assertFalse(same_request(row, "b" * 32, self.local, self.remote))

    def test_block_requires_live_recent_socket_from_the_same_process(self):
        ingress = Ingress()
        self.assertFalse(ingress.authorized())
        ingress.nginx = Mock(pid=42)
        ingress.nginx.poll.return_value = None
        ingress.active = time.monotonic(), self.local, self.remote, 71
        with patch("r60_ingress.nginx_socket", return_value=71) as readback:
            self.assertTrue(ingress.authorized())
            readback.assert_called_once_with(42, self.local, self.remote)
            readback.return_value = 72
            self.assertFalse(ingress.authorized())
            readback.return_value = 71
            ingress.active = time.monotonic() - PROOF_SECONDS - 1, self.local, self.remote, 71
            self.assertFalse(ingress.authorized())
            ingress.active = time.monotonic(), self.local, self.remote, 71
            ingress.nginx.poll.return_value = 0
            self.assertFalse(ingress.authorized())


if __name__ == "__main__":
    main()

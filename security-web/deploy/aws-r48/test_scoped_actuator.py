import unittest
from unittest.mock import patch

import scoped_actuator as actuator


class FirewallFingerprintTests(unittest.TestCase):
    def test_lease_count_does_not_change_the_firewall_fingerprint(self):
        listing = "table inet ws_aws_prevention {\n\tset blocked_ips {\n\t\tsize 128\n\t}\n}\n"
        leased = listing.replace("size 128", "size 128\t# count 1")
        with patch.object(actuator, "nft", side_effect=[listing, leased, listing]):
            original = actuator.fingerprint()
            self.assertEqual(actuator.fingerprint(), original)
            self.assertEqual(actuator.fingerprint(), original)

    def test_configuration_changes_are_still_detected(self):
        base = "\t\tsize 128\n\t\tflags timeout\n\t\ttcp dport 443 drop\n"
        with patch.object(actuator, "nft", side_effect=[
            base,
            base.replace("128", "64\t# count 1"),
            base.replace("443", "80"),
        ]):
            original = actuator.fingerprint()
            self.assertNotEqual(actuator.fingerprint(), original)
            self.assertNotEqual(actuator.fingerprint(), original)

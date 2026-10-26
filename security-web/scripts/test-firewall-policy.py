#!/usr/bin/env python3
"""Pure safety tests; never invokes nftables or changes the network."""
import importlib.util
import ipaddress
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('actuator', Path(__file__).with_name('pbl4-firewall-policy.py'))
actuator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actuator)


class SafetyTests(unittest.TestCase):
    def test_private_networks_are_configurable(self):
        for value in ['192.168.2.50', '10.0.2.5', '172.31.0.2']:
            self.assertEqual(str(actuator.validate(value, actuator.DEFAULTS, set())), value)
        with self.assertRaises(ValueError):
            actuator.validate('8.8.8.8', actuator.DEFAULTS, set())
        configured = {'allowed_subnets':['203.0.113.0/24'], 'protected_ips':[]}
        self.assertEqual(str(actuator.validate('203.0.113.2', configured, set())), '203.0.113.2')

    def test_host_gateway_webvm_and_non_unicast_are_protected(self):
        discovered = {ipaddress.ip_address(value) for value in ['192.168.1.1','192.168.1.2','10.0.0.1']}
        for value in ['192.168.1.1','192.168.1.2','10.0.0.1','192.168.20.10','192.168.20.1','127.0.0.1','::1','224.0.0.1','0.0.0.0','169.254.0.1','255.255.255.255']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                actuator.validate(value, actuator.DEFAULTS, discovered)

    def test_literal_hosts_only_and_no_shell_fragments(self):
        for value in ['192.168.1.2/24', 'localhost', '192.168.1.2;id', '192.168.1.999', '010.0.0.1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                actuator.validate(value, actuator.DEFAULTS, set())


if __name__=='__main__':
    unittest.main(verbosity=2)

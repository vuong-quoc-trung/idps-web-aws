#!/usr/bin/env python3
"""No privileged calls: verify VM isolation gates and result completeness."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('vm', Path(__file__).with_name('test-proof-host-vm.py'))
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

class Gates(unittest.TestCase):
    def args(self):
        return dict(machine='a'*32, production='b'*32, actual='a'*32, vm=True,
                    pid1='systemd', links=[{'ifname':'lo', 'flags':['UP']}], cgroup=True)

    def test_disconnected_vm_accepted(self):
        vm.validate_isolation(**self.args())

    def test_production_id_refused(self):
        args = self.args(); args['production'] = args['machine']
        with self.assertRaises(ValueError): vm.validate_isolation(**args)

    def test_wrong_machine_refused(self):
        args = self.args(); args['actual'] = 'c'*32
        with self.assertRaises(ValueError): vm.validate_isolation(**args)

    def test_container_or_namespace_refused(self):
        args = self.args(); args['vm'] = False
        with self.assertRaises(ValueError): vm.validate_isolation(**args)

    def test_live_nic_refused(self):
        args = self.args(); args['links'].append({'ifname':'ens33', 'flags':['UP']})
        with self.assertRaises(ValueError): vm.validate_isolation(**args)

    def test_non_systemd_or_cgroup_v1_refused(self):
        for field, value in [('pid1','bash'), ('cgroup',False)]:
            args=self.args(); args[field]=value
            with self.assertRaises(ValueError): vm.validate_isolation(**args)

    def test_no_partial_pass(self):
        cases={name:{'status':'PASS'} for name in vm.CASES}
        self.assertEqual(vm.summary(cases)['result'], 'PASS')
        cases.pop(vm.CASES[-1])
        self.assertEqual(vm.summary(cases)['result'], 'FAIL')
        cases[vm.CASES[-1]]={'status':'NOT_RUN'}
        self.assertEqual(vm.summary(cases)['result'], 'FAIL')
        cases[vm.CASES[-1]]={'status':'FAIL'}
        self.assertEqual(vm.summary(cases)['result'], 'FAIL')
        cases[vm.CASES[-1]]={'status':'PASS'}
        cases['cleanup']={'status':'FAIL'}
        self.assertEqual(vm.summary(cases)['result'], 'FAIL')

if __name__ == '__main__': unittest.main(verbosity=2)

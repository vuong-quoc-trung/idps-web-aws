#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('stage',Path(__file__).with_name('stage-sensor-generation.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
    def exercise(self, drift=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); units=root/'units';units.mkdir()
            config=root/'config';lua=root/'lua';unit=units/'99-local.conf'
            config.write_text('outputs:\n- lua:\n    enabled: true\n    scripts-dir: /etc/suricata/pbl4\n    scripts: [transaction-evidence.lua]\n')
            lua.write_text('old lua')
            unit.write_text('ExecStart=/usr/bin/suricata -D --af-packet -c '+str(config)+' --pidfile /var/run/suricata/suricata.pid\n')
            with patch.multiple(m,CONFIG=str(config),LUA=str(lua),DROPIN=str(unit),NEW_UNIT=str(units/'zz-new.conf')):
                m.stage(root/'bundle');m.check(root/'bundle')
                if drift=='yaml':config.write_text('changed')
                if drift=='unit':(units/'new.conf').write_text('changed')
                if drift=='payload':(root/'bundle/transaction-evidence.lua').write_text('changed')
                if drift:
                    with self.assertRaises(AssertionError):m.check(root/'bundle')
    def test_stage_and_check(self):self.exercise()
    def test_config_drift(self):self.exercise('yaml')
    def test_extra_dropin(self):self.exercise('unit')
    def test_payload_tamper(self):self.exercise('payload')
if __name__=='__main__':unittest.main()

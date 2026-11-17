#!/usr/bin/env python3
"""Non-root real Suricata offline test. No sockets, services or production files."""
import importlib.util
import json
import os
from unittest.mock import patch
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

HERE=Path(__file__).resolve().parent

def load(name, file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

launcher=load('launcher','run-suricata-generation.py')
support=load('support','test-transaction-proof-support.py')

class Tests(unittest.TestCase):
    def test_new_generation_and_forbidden_override(self):
        a, env_a=launcher.launch_spec(['-T']);b, env_b=launcher.launch_spec(['-T'])
        self.assertNotEqual(env_a['WS_SENSOR_GENERATION'],env_b['WS_SENSOR_GENERATION'])
        self.assertIn('sensor-name=ws-generation-'+env_a['WS_SENSOR_GENERATION'],a)
        with self.assertRaises(ValueError): launcher.launch_spec(['--set','sensor-name=old'])

    def test_notify_environment_and_exec_are_preserved(self):
        # execve replaces the launcher without introducing a supervisor PID.
        with patch.dict(os.environ, {'NOTIFY_SOCKET': '/run/systemd/notify',
                                    'WATCHDOG_PID': '123', 'WS_SENSOR_GENERATION': '0'*32}):
            command, env = launcher.launch_spec(['-D', '--af-packet'])
        self.assertEqual(command[:3], ['/usr/bin/suricata', '-D', '--af-packet'])
        self.assertEqual(env['NOTIFY_SOCKET'], '/run/systemd/notify')
        self.assertEqual(env['WATCHDOG_PID'], '123')
        self.assertNotEqual(env['WS_SENSOR_GENERATION'], '0'*32)
        source = (HERE/'run-suricata-generation.py').read_text()
        self.assertIn('os.execve(command[0], command, environment)', source)
        self.assertNotIn('os.umask(', source)

    def test_real_suricata_restart_rotation_legacy(self):
        with tempfile.TemporaryDirectory(prefix='ws-generation-') as directory:
            w=Path(directory)
            (w/'transaction-evidence.lua').write_bytes((HERE.parent/'config/suricata/transaction-evidence.lua').read_bytes())
            support.pcap(w/'input.pcap')
            cfg=yaml.safe_load(Path('/etc/suricata/suricata.yaml').read_text())
            cfg.pop('run-as',None);cfg.pop('sensor-name',None)
            cfg.update({'default-log-dir':str(w),'unix-command':{'enabled':False},'rule-files':[],
                'logging':{'outputs':[{'console':{'enabled':True}}]},
                'outputs':[{'eve-log':{'enabled':True,'filetype':'regular','filename':'eve.json','types':['http']}},
                    {'lua':{'enabled':True,'scripts-dir':str(w),'scripts':['transaction-evidence.lua']}}]})
            path=w/'suricata.yaml';path.write_text('%YAML 1.1\n---\n'+yaml.safe_dump(cfg))
            args=['-c',str(path),'-r',str(w/'input.pcap'),'-l',str(w),'-k','none','--runmode','single']
            old_generation=None
            for run in range(3):
                command,env=launcher.launch_spec(args)
                if run==2:
                    command=command[:-2];env.pop('WS_SENSOR_GENERATION')
                result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,'Suricata offline failure (raw logs withheld)')
                rows=[line.split('\t') for line in (w/'chain.tsv').read_text().splitlines()]
                events=[json.loads(line) for line in (w/'eve.json').read_text().splitlines()]
                events=[e for e in events if e.get('event_type')=='http']
                self.assertEqual(len(rows),2);self.assertEqual(len(events),2)
                for row in rows:
                    self.assertEqual(len(row),9)
                    event=next(e for e in events if str(e['flow_id'])==row[0] and str(e['tx_id'])==row[1])
                    if run < 2:
                        self.assertEqual(event['host'],'ws-generation-'+row[8])
                        self.assertEqual(row[8],env['WS_SENSOR_GENERATION'])
                    else:
                        self.assertFalse(str(event.get('host','')).startswith('ws-generation-'))
                if old_generation: self.assertNotEqual(old_generation,rows[0][8])
                old_generation=rows[0][8]
                # Rotate before restart. Old bytes are immutable; no relabeling.
                (w/'eve.json').rename(w/f'eve.json.{run}')
                (w/'chain.tsv').rename(w/f'chain.tsv.{run}')
                if run:
                    old=json.loads((w/'eve.json.0').read_text().splitlines()[0])
                    self.assertNotEqual(old['host'],'ws-generation-'+old_generation)

if __name__=='__main__':unittest.main()

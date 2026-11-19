#!/usr/bin/env python3
"""No sockets/root: checkpoint rejection and fresh transaction matching."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('deploy', HERE/'deploy-proof-host.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Tests(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); bundle=root/'bundle';bundle.mkdir()
            (bundle/'suricata.yaml').write_text('default-log-dir: /logs\n')
            logs=root/'logs';logs.mkdir()
            generation='b'*32;rid='a'*32
            (logs/'proof-generation').write_text(generation)
            for name in ('eve.json','chain.tsv'): (logs/name).touch()
            def append(target):
                event={'host': 'ws-generation-'+('c'*32 if mode=='eve_wrong_generation' else generation), 'event_type':'http','in_iface':'lo','src_ip':'127.77.0.1','dest_ip':'127.77.0.2',
                    'flow_id':123,'tx_id':0,'timestamp':datetime.now(timezone.utc).isoformat(),
                    'http':{'url':target,'http_method':'GET'}}
                with (logs/'eve.json').open('a') as stream: stream.write(json.dumps(event)+'\n')
                fields=['123','1' if mode=='wrong_tx' else '0','proof','' if mode=='missing_receipt' else 'receipt',
                        '192.0.2.1',rid,'https','lab','c'*32 if mode=='wrong_generation' else generation]
                with (logs/'chain.tsv').open('a') as stream: stream.write('\t'.join(fields)+'\n')
            if mode=='stale': append('/api/auth/me?ws_capture_canary='+ 'd'*32)
            def runner(args):
                if mode!='stale': append(args[-1].split('192.168.10.1',1)[1])
                return 'HTTP/1.1 401 Unauthorized\r\nX-Request-Id: '+rid+'\r\n\r\n'
            deployment=m.Deployment(bundle,root/'backup',runner,root)
            deployment.require_eve_generation = True
            with patch.object(m.secrets,'token_hex',return_value='d'*32), patch.object(m.time,'monotonic',side_effect=[0,0,16]), patch.object(m.time,'sleep'):
                deployment.capture_health()
    def test_fresh_matching_evidence(self): self.exercise('valid')
    def test_reject_eve_wrong_generation(self):
        with self.assertRaises(RuntimeError): self.exercise('eve_wrong_generation')
    def test_reject_stale_logs(self):
        with self.assertRaises(RuntimeError): self.exercise('stale')
    def test_reject_missing_receipt(self):
        with self.assertRaises(RuntimeError): self.exercise('missing_receipt')
    def test_reject_wrong_transaction(self):
        with self.assertRaises(RuntimeError): self.exercise('wrong_tx')
    def test_reject_wrong_generation(self):
        with self.assertRaises(RuntimeError): self.exercise('wrong_generation')

if __name__=='__main__': unittest.main()

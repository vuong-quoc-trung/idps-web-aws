#!/usr/bin/env python3
"""Read-only verifier regression tests and firewall fail-closed checks (mock nft)."""
import importlib.machinery, importlib.util, json, pathlib, subprocess, tempfile, types, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
loader=importlib.machinery.SourceFileLoader('guard',str(ROOT/'deploy/rsyslog/pbl4-audit-guard'))
spec=importlib.util.spec_from_loader('guard',loader);guard=importlib.util.module_from_spec(spec);loader.exec_module(guard)
class ToolTests(unittest.TestCase):
    def test_verifier_replay_missing_and_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            a=pathlib.Path(temp)/'source';b=pathlib.Path(temp)/'dest'
            event=dict(schema_version='1.0',source='STUDENT_AUDIT',source_instance='web',event_id='id1',timestamp='2026-10-30T00:00:00Z')
            line=json.dumps(event)+'\n';a.write_text(line);b.write_text(line*2)
            command=['python3',str(ROOT/'scripts/verify-student-audit-forwarding.py'),'--source',str(a),'--destination',str(b)]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            b.write_text('');self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            event['timestamp']='2026-10-30T01:00:00Z';b.write_text(json.dumps(event)+'\n')
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            b.write_text(json.dumps({'message':line})+'\n');self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
    def test_guard_dry_run_does_not_apply(self):
        calls=[]
        def nft(*args,**kwargs):
            calls.append(args);return types.SimpleNamespace(stdout=json.dumps({'nftables':[]}))
        with patch.object(guard,'run',nft),patch('sys.argv',['guard']):guard.main()
        self.assertEqual(calls,[('-j','list','tables'),('-c','-f','-')])
    def test_guard_refuses_foreign_table(self):
        calls=[]
        def nft(*args,**kwargs):
            calls.append(args)
            value={'nftables':[{'table':{'name':'pbl4_audit_transport','family':'inet'}}]} if args[-1]=='tables' else {'nftables':[]}
            return types.SimpleNamespace(stdout=json.dumps(value))
        with patch.object(guard,'run',nft),patch('sys.argv',['guard','--apply']):
            with self.assertRaises(SystemExit):guard.main()
        self.assertTrue(all(x[0]=='-j' for x in calls))
if __name__=='__main__':unittest.main(verbosity=2)

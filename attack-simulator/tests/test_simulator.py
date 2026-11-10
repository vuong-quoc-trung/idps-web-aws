import json
import threading
import unittest
from unittest.mock import patch, MagicMock
from attack_simulator.config import Config
from attack_simulator.http_client import Target, ValidationError, Response, Client, parse_origin
from attack_simulator.runner import Runner
from attack_simulator.reports import render

RID = 'a'*32

def response(data=None, status=200, headers=None):
    return Response(status, headers or {'x-request-id': RID}, json.dumps(data or {}).encode())

class FakeClient:
    def __init__(self, result=None): self.calls=[]; self.result=result or response(status=401)
    def request(self, *args, **kwargs): self.calls.append((args, kwargs)); return self.result

class ScopeTests(unittest.TestCase):
    def test_private_and_pinned(self):
        t=Target.create('http://lab:8080', resolver=lambda *_:['192.168.1.2'])
        self.assertEqual(t.ip,'192.168.1.2')
        self.assertEqual(t.origin,'http://lab:8080')
    def test_public_and_mixed_dns_rejected(self):
        for ips in [['8.8.8.8'],['127.0.0.1','8.8.8.8'],['169.254.169.254'],['224.0.0.1']]:
            with self.subTest(ips=ips), self.assertRaises(ValidationError): Target.create('http://lab',resolver=lambda *_:ips)
    def test_explicit_origin_allowlist(self):
        self.assertEqual(Target.create('https://lab', ['https://lab'],lambda *_:['8.8.8.8']).ip,'8.8.8.8')
        with self.assertRaises(ValidationError): Target.create('http://lab',['https://lab'],lambda *_:['8.8.8.8'])
    def test_bad_origins(self):
        for url in ['file:///a','http://u:secret@localhost','http://localhost/a','http://localhost?x=1','http://localhost\\evil','http://localhost:99999','http://localhost\n']:
            with self.subTest(url=url), self.assertRaises(ValidationError): parse_origin(url)
    @patch('attack_simulator.http_client.PinnedHTTP')
    def test_redirect_never_followed_and_bounded_read(self, ctor):
        conn=ctor.return_value;conn.timeout=1
        raw=conn.getresponse.return_value;raw.status=302;raw.getheaders.return_value=[('Location','http://8.8.8.8/')];raw.read.return_value=b'x'*262145
        r=Client(Target('http','localhost',80,'http://localhost:80','127.0.0.1')).request('GET','/')
        self.assertEqual(r.status,302);self.assertTrue(r.truncated);self.assertEqual(conn.request.call_count,1);raw.read.assert_called_once_with(262145)

class ConfigTests(unittest.TestCase):
    def cfg(self, **kw): return Config.load({'target':'http://localhost','authorized':True,**kw})
    def test_consent(self):
        with self.assertRaises(ValidationError): Config.load({'target':'http://localhost'})
    def test_multi_requires_consent(self):
        with self.assertRaises(ValidationError): self.cfg(scenarios=['auth-get'])
    def test_behavior_requires_profile(self):
        with self.assertRaises(ValidationError): self.cfg(scenarios=['enumeration'],confirm_multiple=True)
    def test_budgets_and_types(self):
        for change in [{'rate':6},{'rate':float('nan')},{'duration':301},{'max_requests':True},{'max_requests':201},{'scenarios':['nope']},{'authorized':'yes'},{'allowlist':'all'}]:
            with self.subTest(change=change),self.assertRaises(ValidationError): self.cfg(**change)
    def test_burst_budget(self):
        with self.assertRaises(ValidationError): self.cfg(scenarios=['burst'],profile='behavior',confirm_multiple=True)
        self.assertEqual(self.cfg(scenarios=['burst'],profile='behavior',confirm_multiple=True,max_requests=180).max_requests,180)

class RunnerTests(unittest.TestCase):
    def runner(self, scenarios=None, **kw):
        c=Config.load({'target':'http://localhost','authorized':True,'scenarios':scenarios or ['baseline'],'confirm_multiple':True,**kw})
        client=FakeClient()
        return Runner(c,client=client),client
    def test_baseline_and_safe_report(self):
        run,client=self.runner();report=run.execute()
        self.assertEqual(report['scenarios'][0]['result'],'COMPLETED');self.assertEqual(report['http_count'],1)
        self.assertNotIn('Authorization',render(report));self.assertEqual(len(client.calls),1)
    def test_signature_http_execution_only(self):
        run,_=self.runner(['sqli']);self.assertEqual(run.execute()['scenarios'][0]['result'],'COMPLETED')
    def test_fixture_skipped(self):
        run,c=self.runner(['login-failure']);self.assertEqual(run.execute()['scenarios'][0]['result'],'SKIPPED');self.assertFalse(c.calls)
    def test_stop_before_run(self):
        run,c=self.runner();run.stop.set();self.assertEqual(run.execute()['state'],'CANCELLED');self.assertFalse(c.calls)
    def test_network_failure(self):
        run,c=self.runner();c.request=MagicMock(side_effect=OSError('SECRET'))
        r=run.execute();self.assertEqual(r['scenarios'][0]['result'],'FAILED');self.assertNotIn('SECRET',render(r))
    def test_untrusted_request_id_removed(self):
        run,c=self.runner();c.result=response(headers={'x-request-id':'=SECRET'})
        self.assertIsNone(run.execute()['requests'][0]['request_id'])
    def test_csv_formula_safety(self):
        self.assertIn("'=bad",render({'requests':[{'scenario':'=bad'}]},'csv'))

if __name__=='__main__': unittest.main()

class SchedulingTests(unittest.TestCase):
    def test_serial_rate_and_deadline(self):
        clock=[0.0]
        class Stop:
            def is_set(self): return False
            def wait(self, seconds): clock[0]+=seconds;return False
        class C:
            calls=[]
            def request(self,*a,**kw): self.calls.append((clock[0],kw['timeout']));return response()
        config=Config.load({'target':'http://localhost','authorized':True,'scenarios':['auth-get'],'confirm_multiple':True,'rate':2,'duration':1,'max_requests':10})
        client=C()
        with patch('attack_simulator.runner.time.monotonic',side_effect=lambda:clock[0]):
            r=Runner(config,client=client,stop=Stop()).execute()
        self.assertEqual([x[0] for x in client.calls],[0,.5]);self.assertEqual(r['state'],'CANCELLED');self.assertLessEqual(client.calls[-1][1],.5)
    def test_cancel_during_request_no_next(self):
        stop=threading.Event()
        class C:
            count=0
            def request(self,*a,**kw): self.count+=1;stop.set();return response()
        config=Config.load({'target':'http://localhost','authorized':True,'scenarios':['auth-get'],'confirm_multiple':True})
        c=C();r=Runner(config,client=c,stop=stop).execute()
        self.assertEqual(c.count,1);self.assertEqual(r['state'],'CANCELLED')
    def test_fixture_login_success_stops_and_redacts(self):
        class C:
            def request(self,method,path,*a,**kw):
                if path=='/api/auth/csrf': return response({'headerName':'X-CSRF-TOKEN','token':'SECRET_CSRF'},headers={'set-cookie':'JSESSIONID=SECRET_COOKIE'})
                return response(status=204)
        config=Config.load({'target':'http://localhost','authorized':True,'scenarios':['login-failure'],'confirm_multiple':True,'fixture_confirmed':True,'lab_username':'PRIVATE_USERNAME'})
        r=Runner(config,client=C()).execute()
        self.assertEqual(r['state'],'FAILED');self.assertEqual(r['scenarios'][0]['result'],'FAILED')
        for secret in ('SECRET_CSRF','SECRET_COOKIE','PRIVATE_USERNAME'):self.assertNotIn(secret,render(r))

class AttackerOnlyTests(unittest.TestCase):
    def test_removed_config_fields_rejected(self):
        for key in ('security_url', 'security_token'):
            with self.assertRaises(ValidationError):
                Config.load({'target':'http://localhost','authorized':True,key:'unused'})
    def test_all_http_responses_are_execution_completion(self):
        for status in (200,302,401,403,404,500,502):
            with self.subTest(status=status):
                c=Config.load({'target':'http://localhost','authorized':True,'scenarios':['ai-shadow']})
                client=FakeClient(response(status=status))
                result=Runner(c,client=client).execute()
                self.assertEqual(result['state'],'COMPLETED')
                self.assertEqual(result['scenarios'][0]['result'],'COMPLETED')
                self.assertEqual(len(client.calls),1)
                self.assertEqual(client.calls[0][0][1],'/api/auth/me')
                for fmt in ('json','csv'):
                    data=render(result,fmt)
                    for forbidden in ('score','severity','evidence','threshold','security_url','suricata_alert'):
                        self.assertNotIn(forbidden,data)
    def test_catalog_and_request_contract(self):
        from attack_simulator.scenarios import CATALOG, catalog, request_spec
        counts={'baseline':1,'sqli':1,'xss':1,'traversal':1,'command':1,'scanner':1,'method':1,'auth-get':10,'login-failure':10,'csrf':5,'enumeration':20,'burst':120,'ai-shadow':1}
        self.assertEqual({k:v.count for k,v in CATALOG.items()},counts)
        for row in catalog():
            self.assertFalse(set(row)&{'expected','rule_name','severity'})
        self.assertEqual(request_spec(CATALOG['sqli'],0,'run')[1],'/api/auth/me?pbl4_probe=%27+OR+%271%27%3D%271')
        self.assertEqual(request_spec(CATALOG['xss'],0,'run')[1],'/api/auth/me?pbl4_probe=%3Cscript%3Evoid%280%29%3C%2Fscript%3E')
        self.assertEqual(request_spec(CATALOG['scanner'],0,'run')[2]['User-Agent'],'PBL4-Lab nikto signature-test')
        self.assertEqual(request_spec(CATALOG['method'],0,'run')[0],'PROPFIND')
    def test_cli_removed_options_and_no_external_dependencies(self):
        import subprocess,sys
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-S','-m','attack_simulator','--list'],cwd=root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertNotIn('SID',result.stdout)
        rejected=subprocess.run([sys.executable,'-S','-m','attack_simulator','--security-url','http://localhost'],cwd=root,capture_output=True,text=True)
        self.assertNotEqual(rejected.returncode,0)
    def test_stop_marks_remaining_skipped(self):
        c=Config.load({'target':'http://localhost','authorized':True,'scenarios':['baseline','sqli'],'confirm_multiple':True})
        stop=threading.Event();stop.set()
        r=Runner(c,client=FakeClient(),stop=stop).execute()
        self.assertEqual([s['result'] for s in r['scenarios']],['CANCELLED','SKIPPED'])

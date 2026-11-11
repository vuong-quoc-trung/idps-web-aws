import json
import re
import unittest
from unittest.mock import patch
try:
    from attack_simulator.web import create_app
except ImportError:
    create_app = None

@unittest.skipIf(create_app is None, 'Install optional web dependencies')
class WebTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app();self.client=self.app.test_client();self.base='http://127.0.0.1:8765'
        page=self.client.get('/',base_url=self.base)
        self.token=re.search(r'name="simulator-token" content="([^"]+)"',page.text).group(1)
        self.h={'X-Simulator-Token':self.token}
    def test_page_and_security_headers(self):
        r=self.client.get('/',base_url=self.base)
        self.assertEqual(r.status_code,200);self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
        self.assertIn('id="stop"',r.text);self.assertIn('fixture lab',r.text)
    def test_api_requires_csrf(self):
        self.assertEqual(self.client.post('/api/run',base_url=self.base,json={}).status_code,403)
    def test_host_and_origin(self):
        self.assertIn(self.client.get('/',base_url='http://evil.example:8765').status_code,(400,403))
        self.assertEqual(self.client.get('/',base_url=self.base,headers={'Origin':'https://evil.example'}).status_code,403)
    def test_validation_no_network(self):
        for data in [{},{'authorized':True,'target':'http://localhost','max_requests':999},{'allowlist':['http://evil.example']}]:
            r=self.client.post('/api/run',base_url=self.base,headers=self.h,json=data)
            self.assertEqual(r.status_code,400)
    def test_body_limit(self):
        r=self.client.post('/api/run',base_url=self.base,headers=self.h,json={'x':'a'*17000})
        self.assertEqual(r.status_code,413)
    def test_state_stop_and_report(self):
        self.assertFalse(self.client.get('/api/state',base_url=self.base,headers=self.h).json['active'])
        self.assertEqual(self.client.post('/api/stop',base_url=self.base,headers=self.h).status_code,200)
        self.assertEqual(self.client.get('/api/report/json',base_url=self.base,headers=self.h).status_code,404)
    def test_single_job_and_sanitized_export(self):
        import threading
        from attack_simulator.runner import Runner
        from attack_simulator.http_client import Response
        class MockClient:
            def request(self,*a,**kw): return Response(401,{'x-request-id':'a'*32},b'PRIVATE_BODY')
        def factory(config,**kw): return Runner(config,client=MockClient(),**kw)
        app=create_app(runner_factory=factory);c=app.test_client()
        t=re.search(r'name="simulator-token" content="([^"]+)"',c.get('/',base_url=self.base).text).group(1)
        h={'X-Simulator-Token':t}
        with patch('attack_simulator.web.threading.Thread') as th:
            r=c.post('/api/run',base_url=self.base,headers=h,json={'target':'http://localhost','authorized':True})
            self.assertEqual(r.status_code,202)
            self.assertEqual(c.post('/api/run',base_url=self.base,headers=h,json={'target':'http://localhost','authorized':True}).status_code,409)
            th.call_args.kwargs['target']()
        r=c.get('/api/report/json',base_url=self.base,headers=h)
        self.assertEqual(r.status_code,200);self.assertNotIn('SECRET',r.text);self.assertNotIn('PRIVATE_BODY',r.text)
        self.assertFalse(c.get('/api/state',base_url=self.base,headers=h).json['active'])

    def test_no_defender_fields_or_request_options(self):
        page=self.client.get('/',base_url=self.base)
        for forbidden in ('security_url','security_token','severity','SID','AI score'):
            self.assertNotIn(forbidden,page.text)
        for key in ('security_url','security_token'):
            r=self.client.post('/api/run',base_url=self.base,headers=self.h,json={'target':'http://localhost','authorized':True,key:'unused'})
            self.assertEqual(r.status_code,400)

    def test_authenticated_form_and_credentials_not_persisted(self):
        from test_authenticated import MockClient, sequence
        from attack_simulator.runner import Runner
        def factory(config, **kwargs): return Runner(config,client=MockClient(sequence()),**kwargs)
        app=create_app(runner_factory=factory);c=app.test_client()
        page=c.get('/',base_url=self.base)
        self.assertIn('name="auth_password"',page.text)
        t=re.search(r'name="simulator-token" content="([^"]+)"',page.text).group(1)
        h={'X-Simulator-Token':t}
        with patch('attack_simulator.web.threading.Thread') as thread:
            result=c.post('/api/run',base_url=self.base,headers=h,json={'target':'http://lab','authorized':True,'confirm_multiple':True,'auth_confirmed':True,'auth_role':'STUDENT','scenarios':['student-users'],'rate':5,'credentials':{'username':'lab-private','password':'SECRET_PASSWORD'}})
            self.assertEqual(result.status_code,202)
            thread.call_args.kwargs['target']()
        state=c.get('/api/state',base_url=self.base,headers=h)
        self.assertEqual(state.json['report']['state'],'COMPLETED')
        for secret in ('SECRET_PASSWORD','lab-private','SECRET_NEW','rotated'):
            self.assertNotIn(secret,state.text)

    def test_fixture_confirmation_bound_to_active_run(self):
        r=self.client.post('/api/fixture-confirm',base_url=self.base,headers=self.h,json={'run_id':'old','confirmed':True})
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.client.post('/api/fixture-confirm',base_url=self.base,json={'run_id':'old','confirmed':True}).status_code,403)
        self.assertEqual(self.client.post('/api/fixture-confirm',base_url=self.base,headers=self.h,json={'run_id':'old','confirmed':'yes'}).status_code,400)

    def test_mock_flask_workflow_roundtrip(self):
        import time
        from test_authenticated import MockClient, sequence, reply
        from attack_simulator.runner import Runner
        q=sequence();q[4]=reply(401)
        target=MockClient(q)
        def factory(config,**kwargs):return Runner(config,client=target,**kwargs)
        app=create_app(runner_factory=factory);c=app.test_client()
        t=re.search(r'name="simulator-token" content="([^"]+)"',c.get('/',base_url=self.base).text).group(1)
        h={'X-Simulator-Token':t}
        try:
            started=c.post('/api/run',base_url=self.base,headers=h,json={'target':'http://lab','authorized':True,'confirm_multiple':True,'auth_confirmed':True,'auth_role':'STUDENT','scenarios':['workflow-abuse'],'write_confirmed':True,'safety_contract_confirmed':True,'rate':5,'credentials':{'username':'lab-private','password':'SECRET_PASSWORD'}})
            self.assertEqual(started.status_code,202)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                report=c.get('/api/state',base_url=self.base,headers=h).json['report']
                if report.get('phase')=='awaiting_fixture':break
                time.sleep(.02)
            self.assertEqual(report['phase'],'awaiting_fixture');self.assertEqual(len(target.calls),4)
            self.assertEqual(c.post('/api/fixture-confirm',base_url=self.base,headers=h,json={'run_id':'wrong','confirmed':True}).status_code,409)
            self.assertEqual(c.post('/api/fixture-confirm',base_url=self.base,headers=h,json={'run_id':report['run_id'],'confirmed':True}).status_code,200)
            while time.monotonic()<deadline:
                state=c.get('/api/state',base_url=self.base,headers=h).json
                if not state['active']:break
                time.sleep(.02)
            self.assertFalse(state['active']);self.assertEqual(state['report']['state'],'COMPLETED')
            self.assertNotIn('SECRET',json.dumps(state));self.assertEqual(target.calls[-1][0],'PUT')
        finally:app.extensions['simulator_shutdown']()

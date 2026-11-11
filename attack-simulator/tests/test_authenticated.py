import json
import threading
import unittest
from unittest.mock import patch
from attack_simulator.config import Config
from attack_simulator.http_client import Response, Target, ValidationError
from attack_simulator.runner import Runner
from attack_simulator.authenticated import Session
from attack_simulator.reports import render

def reply(status=200,data=None,cookie=None):
    return Response(status,{'x-request-id':'a'*32},json.dumps(data or {}).encode(),False,[cookie] if cookie else [])

def sequence():
    return [reply(data={'headerName':'X-CSRF-TOKEN','token':'SECRET_OLD'},cookie='JSESSIONID=old; Path=/; HttpOnly'),
            reply(204,cookie='JSESSIONID=rotated; Path=/; HttpOnly'),
            reply(data={'headerName':'X-CSRF-TOKEN','token':'SECRET_NEW'}),
            reply(data={'username':'lab-private','role':'STUDENT','enabled':True,'passwordSetupRequired':False}),
            reply(403),reply(204,cookie='JSESSIONID=; Max-Age=0; Path=/')]

class MockClient:
    target=Target('http','lab',80,'http://lab:80','127.0.0.1')
    def __init__(self, responses): self.responses=responses;self.calls=[]
    def request(self,method,path,headers=None,body=None,**kw):
        self.calls.append((method,path,dict(headers or {}),body))
        return self.responses.pop(0)

class AuthTests(unittest.TestCase):
    def run_case(self, responses, **changes):
        c=Config.load({'target':'http://lab','authorized':True,'confirm_multiple':True,'scenarios':['student-users'],'auth_role':'STUDENT','auth_confirmed':True,**changes})
        client=MockClient(responses)
        runner=Runner(c,client=client,credentials=('lab-private','SECRET_PASSWORD'))
        session=runner.session
        with patch('attack_simulator.runner.time.monotonic',return_value=1):
            runner.next_at=-1
            # Simulate pacing without wall-clock waits; budget tests cover real schedule separately.
            runner.stop.wait=lambda _:False
            with patch('attack_simulator.runner.time.sleep'):
                result=runner.execute()
        return result,client,session
    def test_success_rotation_csrf_logout_and_redaction(self):
        r,c,s=self.run_case(sequence())
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['logout'],'COMPLETED');self.assertEqual(r['http_count'],6)
        self.assertEqual(c.calls[1][2]['Cookie'],'JSESSIONID=old')
        self.assertEqual(c.calls[2][2]['Cookie'],'JSESSIONID=rotated')
        self.assertEqual(c.calls[-1][2]['X-CSRF-TOKEN'],'SECRET_NEW')
        self.assertEqual(c.calls[-1][1],'/api/auth/logout')
        self.assertEqual((s.cookie,s.csrf,s.password,s.username),('','','',''))
        for fmt in ('json','csv'):
            for secret in ('SECRET_PASSWORD','SECRET_OLD','SECRET_NEW','lab-private','rotated'):
                self.assertNotIn(secret,render(r,fmt))
    def test_login_failure_no_retry(self):
        q=sequence();q[1]=reply(401)
        r,c,s=self.run_case(q)
        self.assertEqual(r['state'],'FAILED');self.assertEqual(len(c.calls),2);self.assertEqual(s.password,'')
    def test_role_mismatch_no_probe_logout(self):
        q=sequence();q[3]=reply(data={'username':'lab-private','role':'ADMIN','enabled':True,'passwordSetupRequired':False});q[4]=reply(204)
        r,c,s=self.run_case(q)
        self.assertEqual(r['state'],'FAILED');self.assertNotIn('/api/users',[x[1] for x in c.calls]);self.assertEqual(c.calls[-1][1],'/api/auth/logout')
    def test_bad_csrf(self):
        q=sequence();q[0]=reply(data={'headerName':'Authorization','token':'SECRET'})
        r,c,s=self.run_case(q);self.assertEqual(r['state'],'FAILED');self.assertEqual(len(c.calls),1)
    def test_expiry_stops_without_relogin(self):
        q=sequence();q[4]=reply(401)
        r,c,s=self.run_case(q,scenarios=['student-users','student-students'])
        self.assertEqual(r['state'],'FAILED');self.assertEqual(r['logout'],'SKIPPED');self.assertEqual(len(c.calls),5)
        self.assertEqual(r['scenarios'][-1]['result'],'SKIPPED')
    def test_logout_failure_does_not_keep_secrets(self):
        q=sequence();q[-1]=reply(403)
        r,c,s=self.run_case(q);self.assertEqual(r['logout'],'FAILED');self.assertEqual(s.cookie,'')
    def test_only_supplied_object_ids(self):
        q=sequence();q.insert(-1,reply(404))
        r,c,s=self.run_case(q,scenarios=['idor-get'],object_ids=[31,42])
        paths=[x[1] for x in c.calls]
        self.assertIn('/api/me/family-members/31',paths);self.assertIn('/api/me/family-members/42',paths);self.assertEqual(len(paths),7)
    def test_cookie_scope_and_secure(self):
        s=Session('lab','pass',MockClient.target)
        s.accept(reply(cookie='JSESSIONID=bad; Domain=evil.example; Path=/'));self.assertEqual(s.cookie,'')
        s.accept(reply(cookie='JSESSIONID=secure; Secure; Path=/'));self.assertEqual(s.cookie,'')
        s.accept(reply(cookie='JSESSIONID=ok; Path=/api/auth'))
        self.assertNotIn('Cookie',s.headers('/api/users'));self.assertIn('Cookie',s.headers('/api/auth/me'))
    def test_config_requires_fixture_role_ids_budget(self):
        base={'target':'http://lab','authorized':True,'confirm_multiple':True,'scenarios':['idor-get'],'auth_role':'STUDENT','auth_confirmed':True,'object_ids':[1]}
        for changes in ({'auth_role':'ADMIN'},{'auth_confirmed':False},{'object_ids':[]},{'object_ids':[1,1]},{'object_ids':['../']},{'max_requests':5},{'scenarios':['baseline','student-users']}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError): Config.load({**base,**changes})

    def test_staff_and_csrf_request_headers(self):
        q=sequence();q[3]=reply(data={'username':'lab-private','role':'STAFF','enabled':True,'passwordSetupRequired':False})
        r,c,s=self.run_case(q,scenarios=['staff-users'],auth_role='STAFF')
        self.assertEqual(r['state'],'COMPLETED')
        self.assertEqual(c.calls[1][2]['X-CSRF-TOKEN'],'SECRET_OLD')
        self.assertNotIn('X-CSRF-TOKEN',c.calls[4][2])
    def test_expired_cookie_removed(self):
        s=Session('lab','pass',MockClient.target)
        s.accept(reply(cookie='JSESSIONID=old; Path=/'))
        s.accept(reply(cookie='JSESSIONID=old; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT'))
        self.assertNotIn('Cookie',s.headers('/api/users'))
    def test_stop_after_probe_still_logs_out(self):
        c=Config.load({'target':'http://lab','authorized':True,'confirm_multiple':True,'scenarios':['student-users','student-students'],'auth_role':'STUDENT','auth_confirmed':True})
        client=MockClient(sequence());stop=threading.Event()
        def callback(report):
            if any(row['stage']=='probe' for row in report['requests']): stop.set()
        runner=Runner(c,client=client,stop=stop,callback=callback,credentials=('lab-private','SECRET_PASSWORD'))
        with patch('attack_simulator.runner.time.sleep'):
            r=runner.execute()
        self.assertEqual(r['state'],'CANCELLED');self.assertEqual(r['logout'],'COMPLETED')
        self.assertEqual(client.calls[-1][1],'/api/auth/logout');self.assertEqual(len(client.calls),6)

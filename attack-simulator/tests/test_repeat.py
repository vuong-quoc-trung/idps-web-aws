import unittest
from unittest.mock import patch
from attack_simulator.config import Config
from attack_simulator.runner import Runner
from attack_simulator.http_client import ValidationError
from test_authenticated import MockClient, sequence, reply

class RepeatTests(unittest.TestCase):
    def config(self, **kw):
        return Config.load({'target':'http://lab','authorized':True,'confirm_multiple':True,'auth_role':'STUDENT','auth_confirmed':True,'scenarios':['student-users'],'repeat':8,**kw})
    def run_mock(self, config, replies):
        clock=[0.0]
        class Stop:
            def is_set(self):return False
            def wait(self,t):clock[0]+=t;return False
        client=MockClient(replies);times=[]
        original=client.request
        def request(*args,**kwargs):
            times.append(clock[0]);clock[0]+=.1
            return original(*args,**kwargs)
        client.request=request
        with patch('attack_simulator.runner.time.monotonic',side_effect=lambda:clock[0]),patch('attack_simulator.runner.time.sleep',side_effect=lambda t:clock.__setitem__(0,clock[0]+t)):
            result=Runner(config,client=client,credentials=('lab-private','SECRET_PASSWORD'),stop=Stop()).execute()
        return result,client,times
    def test_eight_in_one_session_under_sixty_seconds(self):
        for sid,role in [('student-users','STUDENT'),('student-students','STUDENT'),('staff-users','STAFF')]:
            with self.subTest(sid=sid):
                q=sequence()[:4];q[3]=reply(data={'username':'lab-private','role':role,'enabled':True,'passwordSetupRequired':False})
                r,c,t=self.run_mock(self.config(scenarios=[sid],auth_role=role,max_requests=13),q+[reply(403) for _ in range(8)]+[reply(204)])
                self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['http_count'],13)
                self.assertEqual(sum(x[1]=='/api/auth/login' for x in c.calls),1)
                self.assertEqual(sum(x[1]=='/api/auth/logout' for x in c.calls),1)
                probes=[x for x in r['requests'] if x['stage']=='probe']
                self.assertEqual([x['index'] for x in probes],list(range(1,9)))
                self.assertEqual({x[2]['Cookie'] for x in c.calls[4:12]},{'JSESSIONID=rotated'})
                self.assertLess(t[11]-t[4]+.1,60)
                self.assertTrue(all(b-a>=.5-1e-9 for a,b in zip(t,t[1:])))
    def test_401_stops_without_relogin(self):
        r,c,t=self.run_mock(self.config(),sequence()[:4]+[reply(403),reply(401)])
        self.assertEqual(r['state'],'FAILED');self.assertEqual(len(c.calls),6)
        self.assertEqual(sum(x[1]=='/api/auth/login' for x in c.calls),1)
    def test_repeat_validation_and_budget(self):
        for value in (0,9,True,1.5,'8'):
            with self.assertRaises(ValidationError):self.config(repeat=value)
        with self.assertRaises(ValidationError):self.config(max_requests=12)
        with self.assertRaises(ValidationError):self.config(rate=.1)
        self.assertEqual(self.config(rate=5).rate,2)
        self.assertEqual(self.config(repeat=1).repeat,1)
    def test_idor_not_multiplied(self):
        c=self.config(scenarios=['student-users','idor-get'],object_ids=[41,42],max_requests=15)
        r,client,t=self.run_mock(c,sequence()[:4]+[reply(403) for _ in range(8)]+[reply(404),reply(404),reply(204)])
        self.assertEqual(r['http_count'],15)
        self.assertEqual(len([x for x in r['requests'] if x['scenario']=='idor-get' and x['stage']=='probe']),2)
    def test_cli_help_and_ui_field(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-m','attack_simulator','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0);self.assertIn('--repeat',result.stdout)
        from attack_simulator.web import create_app
        page=create_app().test_client().get('/',base_url='http://127.0.0.1:8765')
        self.assertIn('name="repeat"',page.text)

    def test_flask_repeat_budget_and_range_before_network(self):
        import re
        from attack_simulator.web import create_app
        client=create_app().test_client()
        origin='http://127.0.0.1:8765'
        page=client.get('/',base_url=origin)
        token=re.search(r'name="simulator-token" content="([^"]+)"',page.text).group(1)
        base={'target':'http://lab','authorized':True,'confirm_multiple':True,'auth_role':'STUDENT','auth_confirmed':True,'scenarios':['student-users'],'repeat':8,'max_requests':12}
        with patch('attack_simulator.config.Target.create') as connect:
            result=client.post('/api/run',base_url=origin,headers={'X-Simulator-Token':token},json=base)
            self.assertEqual(result.status_code,400)
            self.assertIn('13',result.json['error'])
            for repeat in (0,9,1.5,True):
                result=client.post('/api/run',base_url=origin,headers={'X-Simulator-Token':token},json={**base,'max_requests':60,'repeat':repeat})
                self.assertEqual(result.status_code,400)
            connect.assert_not_called()

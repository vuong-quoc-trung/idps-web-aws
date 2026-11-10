"""Controlled in-process HTTP mocks only. Not live Defender acceptance."""
import json
import threading
import unittest
from unittest.mock import patch
from attack_simulator.config import Config
from attack_simulator.runner import Runner
from attack_simulator.fixture_gate import FixtureGate
from attack_simulator.reports import render
from attack_simulator.http_client import ValidationError
from test_authenticated import MockClient, sequence, reply

class WriteFixtureTests(unittest.TestCase):
    def config(self, **kw):
        return Config.load({'target':'http://lab','authorized':True,'confirm_multiple':True,'auth_role':'STUDENT','auth_confirmed':True,'scenarios':['mass-assignment'],'write_confirmed':True,'safety_contract_confirmed':True,'rate':5,**kw})
    def run_case(self, responses, prompt=None, **kw):
        client=MockClient(responses)
        runner=Runner(self.config(**kw),client=client,credentials=('lab-private','SECRET_PASSWORD'),fixture_prompt=prompt)
        with patch('attack_simulator.runner.time.sleep'):
            result=runner.execute()
        return result,client
    def test_mass_assignment_controlled_payload(self):
        q=sequence();q[4]=reply(400)
        r,c=self.run_case(q)
        put=c.calls[4]
        self.assertEqual(put[:2],('PUT','/api/me/profile'))
        self.assertEqual(put[2]['Content-Type'],'application/json')
        self.assertEqual(put[2]['Cookie'],'JSESSIONID=rotated')
        self.assertEqual(put[2]['X-CSRF-TOKEN'],'SECRET_NEW')
        body=json.loads(put[3]);self.assertEqual(set(body),{'role','placeOfBirth'})
        self.assertEqual(body['role'],'STUDENT');self.assertEqual(len(body['placeOfBirth']),151)
        self.assertTrue(r['scenarios'][0]['http_expectation_met']);self.assertEqual(r['logout'],'COMPLETED')
        self.assertNotIn('SECRET',render(r));self.assertNotIn('placeOfBirth',render(r))
    def test_no_contract_or_write_consent_no_put(self):
        for changes in ({'write_confirmed':False},{'safety_contract_confirmed':False}):
            q=sequence();q[4]=reply(204)
            r,c=self.run_case(q,**changes)
            self.assertEqual(r['scenarios'][0]['result'],'SKIPPED')
            self.assertNotIn('PUT',[x[0] for x in c.calls])
    def test_workflow_confirmed_after_login_no_intervening_get(self):
        q=sequence();q[4]=reply(401)
        r,c=self.run_case(q,prompt=lambda gate:gate.confirm(True),scenarios=['workflow-abuse'])
        self.assertEqual(r['scenarios'][0]['result'],'COMPLETED');self.assertTrue(r['scenarios'][0]['http_expectation_met'])
        self.assertEqual(r['logout'],'SKIPPED');self.assertEqual(len(c.calls),5)
        self.assertEqual(c.calls[3][1],'/api/auth/me');self.assertEqual(c.calls[4][:2],('PUT','/api/me/profile'))
    def test_workflow_declined(self):
        q=sequence();q[4]=reply(204)
        r,c=self.run_case(q,prompt=lambda gate:gate.confirm(False),scenarios=['workflow-abuse'])
        self.assertEqual(r['scenarios'][0]['result'],'SKIPPED');self.assertNotIn('PUT',[x[0] for x in c.calls])
    def test_workflow_not_disabled_fallback400(self):
        q=sequence();q[4]=reply(400)
        r,c=self.run_case(q,prompt=lambda gate:gate.confirm(True),scenarios=['workflow-abuse'])
        self.assertFalse(r['scenarios'][0]['http_expectation_met']);self.assertEqual(r['logout'],'COMPLETED')
    def test_unexpected_success_stops_next_probe(self):
        q=sequence();q[4]=reply(200)
        r,c=self.run_case(q,scenarios=['mass-assignment','student-users'])
        self.assertEqual(r['state'],'FAILED');self.assertEqual(r['scenarios'][1]['result'],'SKIPPED')
        self.assertEqual(len([x for x in c.calls if x[0]=='PUT']),1)
    def test_combined_batch(self):
        q=sequence()[:4]+[reply(400),reply(401)]
        r,c=self.run_case(q,prompt=lambda gate:gate.confirm(True),scenarios=['mass-assignment','workflow-abuse'])
        self.assertEqual(r['state'],'COMPLETED');self.assertEqual(r['http_count'],6)
        self.assertEqual([x['result'] for x in r['scenarios']],['COMPLETED','COMPLETED'])
    def test_gate_timeout_stop_and_no_preconfirmation(self):
        gate=FixtureGate();self.assertFalse(gate.confirm(True));gate.open()
        self.assertFalse(gate.wait(.01,threading.Event()));self.assertFalse(gate.confirm(True))
        gate.open();stop=threading.Event();stop.set();self.assertFalse(gate.wait(20,stop))
    def test_roles_and_workflow_order(self):
        for kw in ({'auth_role':'STAFF'},{'scenarios':['workflow-abuse','mass-assignment']}):
            with self.assertRaises(ValidationError):self.config(**kw)

    def test_workflow_timeout_runner_skips_without_put(self):
        q=sequence();q[4]=reply(204)
        with patch('attack_simulator.fixture_gate.FixtureGate.wait',return_value=False):
            r,c=self.run_case(q,scenarios=['workflow-abuse'])
        self.assertEqual(r['scenarios'][0]['result'],'SKIPPED')
        self.assertNotIn('PUT',[x[0] for x in c.calls]);self.assertEqual(r['logout'],'COMPLETED')
    def test_stop_while_waiting_no_put_cleanup(self):
        q=sequence();q[4]=reply(204);client=MockClient(q);stop=threading.Event()
        runner=Runner(self.config(scenarios=['workflow-abuse']),client=client,stop=stop,credentials=('lab-private','SECRET_PASSWORD'),fixture_prompt=lambda gate:stop.set())
        r=runner.execute()
        self.assertEqual(r['state'],'CANCELLED');self.assertEqual(r['logout'],'COMPLETED')
        self.assertNotIn('PUT',[x[0] for x in client.calls])

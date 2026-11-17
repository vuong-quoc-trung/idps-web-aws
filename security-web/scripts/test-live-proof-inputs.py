#!/usr/bin/env python3
"""Nonprivileged validation of observed EVE input; no sockets or fixtures with keys."""
import importlib.util
from pathlib import Path
import unittest
from contextlib import redirect_stdout
import io

spec = importlib.util.spec_from_file_location('live', Path(__file__).with_name('test-live-transaction-proof.py'))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

class ObservedInputTests(unittest.TestCase):
    def event(self):
        return {'event_type': 'http', 'flow_id': 123, 'tx_id': 0}

    def test_duplicate_http_is_not_silently_overwritten(self):
        with self.assertRaises(ValueError):
            live.index_http([self.event(), self.event()])

    def test_distinct_keepalive_transactions_preserved(self):
        second = dict(self.event(), tx_id=1)
        self.assertEqual(len(live.index_http([self.event(), second])), 2)

    def test_alert_and_fileinfo_not_used_as_http_observation(self):
        self.assertEqual(live.index_http([dict(self.event(), event_type='alert'),
                                         dict(self.event(), event_type='fileinfo')]), {})

class ResultGateTests(unittest.TestCase):
    def test_reserved_status_cannot_overwrite_execution_result(self):
        result = live.Results()
        with self.assertRaises(ValueError):
            result.passed('fake_after_deletion', status=403)
        self.assertEqual(result.cases['fake_after_deletion']['status'], 'NOT_RUN')

    def test_http_codes_do_not_prevent_overall_pass(self):
        result = live.Results()
        with redirect_stdout(io.StringIO()):
            for index, name in enumerate(live.REQUIRED_CASES):
                result.passed(name, http_status=(403, 204, 200)[index % 3])
        self.assertEqual(result.summary()['result'], 'PASS')
        self.assertEqual(result.summary()['pending'], [])
        self.assertTrue(all(case['status'] == 'PASS' for case in result.cases.values()))
        self.assertEqual(result.cases['key_dac']['http_status'], 403)
        result.start('nginx_crash')
        result.failed(AssertionError())
        self.assertEqual(result.summary()['result'], 'FAIL')

    def test_failed_case_cannot_be_overwritten_as_pass(self):
        result = live.Results()
        result.start('nginx_crash')
        result.failed(AssertionError())
        with self.assertRaises(ValueError):
            result.passed('nginx_crash', http_status=403)
        self.assertEqual(result.summary()['result'], 'FAIL')

    def test_unexecuted_cases_cannot_pass(self):
        report = live.Results().summary()
        self.assertEqual(report['result'], 'INCOMPLETE')
        self.assertEqual(set(report['pending']), set(live.REQUIRED_CASES))

    def test_one_missing_required_case_cannot_pass(self):
        result = live.Results()
        for name in live.REQUIRED_CASES[:-1]:
            result.cases[name] = {'status': 'PASS'}
        self.assertEqual(result.summary()['result'], 'INCOMPLETE')

    def test_failure_overrides_pass(self):
        result = live.Results()
        for name in live.REQUIRED_CASES:
            result.cases[name] = {'status': 'PASS'}
        result.start('nginx_crash')
        result.failed(AssertionError())
        self.assertEqual(result.summary()['result'], 'FAIL')
        self.assertEqual(result.summary()['cases']['nginx_crash']['status'], 'FAIL')

    def test_all_required_pass_has_no_stale_pending(self):
        result = live.Results()
        for name in live.REQUIRED_CASES:
            result.cases[name] = {'status': 'PASS'}
        self.assertEqual(result.summary()['result'], 'PASS')
        self.assertEqual(result.summary()['pending'], [])

if __name__ == '__main__': unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Nonprivileged validation of observed EVE input; no sockets or fixtures with keys."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
from contextlib import redirect_stdout
import io

spec = importlib.util.spec_from_file_location('live', Path(__file__).with_name('test-live-transaction-proof.py'))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

class RecoveryTests(unittest.TestCase):
    def run_probe(self, outcomes, invariant=lambda: None):
        from unittest.mock import Mock
        ticks = iter([0] + [0.1] * 20)
        return live.wait_replay_denied(Mock(side_effect=outcomes), invariant,
                                      clock=lambda: next(ticks), sleep=lambda _: None)

    def test_reset_refused_then_explicit_403(self):
        result = self.run_probe([ConnectionResetError(), ConnectionRefusedError(), (403, None)])
        self.assertEqual(result, {'ConnectionResetError': 1, 'ConnectionRefusedError': 1})

    def test_immediate_403(self):
        self.assertEqual(self.run_probe([(403, None)]), {})

    def test_reset_or_refused_alone_never_pass(self):
        from unittest.mock import Mock
        for error in (ConnectionResetError, ConnectionRefusedError):
            with self.subTest(error=error):
                ticks = iter([0, 6])
                with self.assertRaises(TimeoutError):
                    live.wait_replay_denied(Mock(side_effect=error()), lambda: None,
                                           clock=lambda: next(ticks), sleep=lambda _: None)

    def test_http_acceptance_or_receipt_is_not_retried(self):
        for outcome in ((200, None), (204, None), (403, 'receipt'), (500, None)):
            with self.subTest(outcome=outcome), self.assertRaises(AssertionError):
                self.run_probe([outcome, (403, None)])

    def test_invariant_failure_not_hidden_by_reset(self):
        from unittest.mock import Mock
        with self.assertRaises(AssertionError):
            self.run_probe([ConnectionResetError(), (403, None)],
                           Mock(side_effect=[None, AssertionError('upstream or process failure')]))

    def test_unexpected_transport_failure_not_retried(self):
        with self.assertRaises(TimeoutError):
            self.run_probe([TimeoutError(), (403, None)])

    def test_crash_diagnostics_not_baseline_failure(self):
        with tempfile.TemporaryDirectory() as work:
            report = live.capture_diagnostics(work, case='nginx_crash', error=ConnectionResetError())
            self.assertEqual(report['classification'], 'NGINX_RECOVERY_FAILED')
            self.assertEqual(report['exception_type'], 'ConnectionResetError')


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

class LuaEvidenceTests(unittest.TestCase):
    def row(self):
        return ['123', '0', 'SECRET_PROOF', 'SECRET_RECEIPT', '192.0.2.1', 'a'*32, 'https', 'lab', 'b'*32]

    def test_nine_field_baseline_is_found(self):
        row = self.row()
        self.assertEqual(live.find_baseline(['\t'.join(row)], 'a'*32, 'b'*32), row)

    def test_legacy_eight_fields_not_accepted(self):
        self.assertIsNone(live.find_baseline(['\t'.join(self.row()[:8])], 'a'*32, 'b'*32))

    def test_wrong_generation_or_request_or_missing_receipt(self):
        for index, value in [(8, 'c'*32), (5, 'c'*32), (3, '')]:
            row = self.row(); row[index] = value
            self.assertIsNone(live.find_baseline(['\t'.join(row)], 'a'*32, 'b'*32))

    def test_diagnostics_never_print_sensitive_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work/'chain.tsv').write_text('\t'.join(self.row())+'\n')
            (work/'proof-generation').write_text('b'*32)
            (work/'sensor-console.log').write_text('Engine started\nLua error SECRET_KEY SECRET_PROOF\n')
            (work/'live-eve.json').write_text(json.dumps({'event_type':'http','flow_id':123,'tx_id':0})+'\n')
            report = live.capture_diagnostics(work, 'a'*32)
            self.assertEqual(report['baseline_correlated'], 1)
            self.assertEqual(report['field_counts'], {'9': 1})
            self.assertNotIn('SECRET', json.dumps(report))

    def test_harness_lua_is_production_source(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            live.bridge.write_lua(work)
            self.assertEqual((work/'chain.lua').read_bytes(),
                (Path(__file__).resolve().parent.parent/'config/suricata/transaction-evidence.lua').read_bytes())

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

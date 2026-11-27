import json
import re
import unittest
from unittest.mock import patch

from attack_simulator import aws_canary

try:
    from attack_simulator.web import create_app
except ImportError:
    create_app = None


class CanaryTests(unittest.TestCase):
    @patch.object(aws_canary, 'identity', return_value={'Account': 'other', 'Arn': 'other'})
    @patch.object(aws_canary, 'session')
    def test_wrong_identity_cannot_dispatch(self, session, identity):
        with self.assertRaises(aws_canary.CanaryError):
            aws_canary.run()
        identity.assert_called_once_with()
        session.assert_not_called()

    def test_readback_rejects_wrong_peer_and_missing_cleanup(self):
        rows = [
            {'source': 'CANARY_RULE', 'rule_sid': 161001, 'status': 204, 'action_id': 1, 'request_id': 'a' * 32},
            {'source': 'CANARY_HYBRID', 'rule_sid': 161002, 'status': 403, 'action_id': 3, 'request_id': 'b' * 32},
        ]
        for row in rows:
            row.update(peer=['10.254.56.2', 41234], local=['10.254.56.1', 18456])
        record = {'automatic': rows, 'db_kernel': 'SYNCED_EMPTY', 'manual_unblock': 2,
                  'max_ttl_seconds': 6, 'audit': '3 SUCCESS', 'protected_scope': 'PASS'}
        cleanup = '\nR60_HOST_READBACK_AND_CLEANUP=PASS\n'
        raw = 'R61_CANARY=' + json.dumps(record)
        result = aws_canary.readback(raw + cleanup)
        self.assertEqual([row['action_id'] for row in result['observations']], [1, 3])
        with self.assertRaises(aws_canary.CanaryError):
            aws_canary.readback(raw)
        rows[0]['peer'][0] = '10.254.56.3'
        with self.assertRaises(aws_canary.CanaryError):
            aws_canary.readback('R61_CANARY=' + json.dumps(record) + cleanup)

    @unittest.skipIf(create_app is None, 'Install optional web dependencies')
    @patch.object(aws_canary, 'run', return_value={'observations': []})
    def test_live_route_requires_opt_in_session_and_fixed_scope(self, run):
        base = 'http://127.0.0.1:8765'
        target = '/api/pbl4-canary'
        enabled = create_app(demo_only=True, live_key='test-key').test_client()
        page = enabled.get('/pbl4', base_url=base)
        token = re.search(r'name="simulator-token" content="([^"]+)"', page.text)[1]
        self.assertNotIn('test-key', page.text)
        self.assertEqual(enabled.post(target, base_url=base, headers={'X-Simulator-Token': token}).status_code, 403)
        headers = {'X-Simulator-Token': token, 'X-PBL4-Session': 'test-key'}
        self.assertEqual(enabled.post(f'{target}?instance=other', base_url=base, headers=headers).status_code, 400)
        self.assertEqual(enabled.post(target, base_url=base, headers=headers, json={'target': 'other'}).status_code, 400)
        disabled = create_app(demo_only=True)
        self.assertNotIn(target, {rule.rule for rule in disabled.url_map.iter_rules()})
        run.assert_not_called()
        self.assertEqual(enabled.post(target, base_url=base, headers=headers).status_code, 200)
        run.assert_called_once_with()

import re
import unittest
from unittest.mock import MagicMock, call, patch

from attack_simulator import aws_smoke
try:
    from attack_simulator.web import create_app
except ImportError:
    create_app = None


class AwsSmokeTests(unittest.TestCase):
    @patch('attack_simulator.aws_smoke.resolve', return_value=['93.184.215.14'])
    @patch('attack_simulator.aws_smoke.PinnedHTTP')
    def test_only_fixed_gets_and_safe_metadata(self, connect, resolve):
        first, second = MagicMock(), MagicMock()
        connect.side_effect = [first, second]
        for connection, status, rid in [(first, 200, 'a' * 32), (second, 301, 'invalid value')]:
            response = connection.getresponse.return_value.__enter__.return_value
            response.status = status
            response.getheader.return_value = rid

        student, security = aws_smoke.check()

        self.assertEqual(resolve.call_args_list, [call('student-dut.duckdns.org', 443), call('websentinal.duckdns.org', 443)])
        self.assertEqual([(target.scheme, target.host, target.port, target.ip) for target, in
                          (entry.args for entry in connect.call_args_list)],
                         [('https', 'student-dut.duckdns.org', 443, '93.184.215.14'),
                          ('https', 'websentinal.duckdns.org', 443, '93.184.215.14')])
        self.assertEqual(first.request.call_args, call('GET', '/api/auth/csrf', headers={'Connection': 'close'}))
        self.assertEqual(second.request.call_args, call('GET', '/', headers={'Connection': 'close'}))
        first.getresponse.return_value.__enter__.return_value.read.assert_not_called()
        self.assertEqual(student['request_id'], 'a' * 32)
        self.assertTrue(student['pass'])
        self.assertIsNone(security['request_id'])
        self.assertFalse(security['pass'])

    @patch('attack_simulator.aws_smoke.resolve', return_value=['127.0.0.1'])
    @patch('attack_simulator.aws_smoke.PinnedHTTP')
    def test_private_dns_resolution_is_refused(self, connect, _):
        self.assertTrue(all(not result['pass'] for result in aws_smoke.check()))
        connect.assert_not_called()

    @unittest.skipIf(create_app is None, 'Install optional web dependencies')
    @patch('attack_simulator.web.aws_smoke.check', return_value=[])
    def test_ui_endpoint_does_not_accept_a_target(self, check):
        client = create_app().test_client()
        base = 'http://127.0.0.1:8765'
        page = client.get('/', base_url=base)
        self.assertIn('id="aws-smoke"', page.text)
        token = re.search(r'name="simulator-token" content="([^"]+)"', page.text)[1]
        headers = {'X-Simulator-Token': token}
        self.assertEqual(client.post('/api/aws-smoke', base_url=base).status_code, 403)
        self.assertEqual(client.post('/api/aws-smoke?target=example.test', base_url=base, headers=headers).status_code, 400)
        self.assertEqual(client.post('/api/aws-smoke', base_url=base, headers=headers, json={}).status_code, 400)
        check.assert_not_called()
        self.assertEqual(client.post('/api/aws-smoke', base_url=base, headers=headers).status_code, 200)
        self.assertEqual(client.post('/api/aws-smoke', base_url=base, headers=headers).status_code, 429)
        check.assert_called_once_with()

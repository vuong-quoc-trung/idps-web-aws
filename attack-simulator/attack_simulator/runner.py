"""Single serial runner shared by CLI and UI. All HTTP shares one finite budget."""
import copy
import json
import http.client
from http.cookies import CookieError
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from urllib.parse import urlencode
from .http_client import Client
from .scenarios import CATALOG, request_spec


def now():
    return datetime.now(timezone.utc).isoformat()

class Halt(Exception):
    pass

class Runner:
    def __init__(self, config, stop=None, callback=None, client=None):
        self.config = config
        self.client = client if client is not None else Client(config.target_endpoint(), config.timeout)
        self.stop = stop or threading.Event()
        self.callback = callback or (lambda r: None)
        self.report = {'run_id': uuid.uuid4().hex, 'started_at': now(), 'state': None, 'phase': 'requests', 'http_count': 0, 'requests': [], 'scenarios': [], 'target': config.target, 'limits': {'max_requests': config.max_requests, 'rate': config.rate, 'duration': config.duration, 'timeout': config.timeout}}
        self.next_at = 0

    def publish(self):
        self.callback(copy.deepcopy(self.report))

    def send(self, client, method, path, headers=None, body=None):
        c = self.config
        if self.stop.is_set() or self.report['http_count'] >= c.max_requests:
            raise Halt()
        wait = max(0, self.next_at - time.monotonic())
        if time.monotonic() + wait >= self.deadline or self.stop.wait(wait): raise Halt()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise Halt()
        self.next_at = time.monotonic() + 1 / c.rate
        self.report['http_count'] += 1
        try:
            return client.request(method, path, headers, body, timeout=min(c.timeout, remaining))
        except (OSError, ValueError, TimeoutError, http.client.HTTPException):
            return None

    def receipt(self, s, index, method, path, headers=None, body=None, stage='probe'):
        started = time.monotonic()
        response = self.send(self.client, method, path, headers, body)
        rid = response.headers.get('x-request-id', '') if response else ''
        row = {'scenario': s.id, 'stage': stage, 'index': index, 'method': method, 'status_code': response.status if response else None, 'request_id': rid.lower() if re.fullmatch(r'[a-fA-F0-9]{32}', rid) else None, 'duration_ms': round((time.monotonic()-started)*1000, 2), 'timestamp': now(), 'error': None if response else 'TRANSPORT_ERROR', 'request_sent': 'CONFIRMED_RESPONSE' if response else 'UNCONFIRMED_TRANSPORT_ERROR', 'result': 'COMPLETED' if response else 'FAILED'}
        self.report['requests'].append(row)
        self.publish()
        return response

    def execute(self):
        self.deadline = time.monotonic() + self.config.duration
        try:
            for sid in self.config.scenarios:
                s = CATALOG[sid]
                result = {'id': sid, 'name': s.name, 'result': None, 'planned_requests': s.count + int(s.fixture), 'reason': ''}
                self.report['scenarios'].append(result)
                if s.fixture and not (self.config.fixture_confirmed and self.config.lab_username):
                    result.update(result='SKIPPED', reason='Cần tài khoản lab riêng và xác nhận fixture.')
                    continue
                headers, body = {}, None
                if s.fixture:
                    setup = self.receipt(s, 0, 'GET', '/api/auth/csrf', stage='setup')
                    try:
                        data = json.loads(setup.body) if setup and setup.status == 200 and not setup.truncated else {}
                        token = data.get('token', '')
                        if data.get('headerName') != 'X-CSRF-TOKEN' or not isinstance(token, str) or not 1 <= len(token) <= 4096 or '\r' in token or '\n' in token: raise ValueError()
                        cookies = SimpleCookie()
                        cookies.load(setup.headers.get('set-cookie', ''))
                        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                        if 'JSESSIONID' in cookies: headers['Cookie'] = 'JSESSIONID=' + cookies['JSESSIONID'].value
                        if sid == 'login-failure': headers['X-CSRF-TOKEN'] = token
                        body = urlencode({'username': self.config.lab_username, 'password': secrets.token_urlsafe(32)})
                    except (ValueError, AttributeError, TypeError, CookieError):
                        result.update(result='FAILED' if setup is None else 'SKIPPED', reason='Không kết nối được để lấy CSRF.' if setup is None else 'CSRF fixture không phù hợp.')
                        continue
                for i in range(s.count):
                    method, path, specific = request_spec(s, i, self.report['run_id'])
                    response = self.receipt(s, i+1, method, path, {**headers, **specific}, body)
                    if s.fixture and response and 200 <= response.status < 300:
                        result.update(result='FAILED', reason='Login được chấp nhận ngoài dự kiến; dừng để kiểm tra fixture.')
                        self.stop.set()
                        raise Halt()
                rows = [r for r in self.report['requests'] if r['scenario'] == sid and r['stage'] == 'probe']
                result.update(result='FAILED' if any(r['error'] for r in rows) else 'COMPLETED',
                              reason='Có request lỗi truyền tải.' if any(r['error'] for r in rows) else 'Đã hoàn tất các HTTP request.')
            self.report['state'] = ('FAILED' if any(s['result'] == 'FAILED' for s in self.report['scenarios'])
                                    else 'SKIPPED' if all(s['result'] == 'SKIPPED' for s in self.report['scenarios']) else 'COMPLETED')
        except Halt:
            reason = 'Người dùng yêu cầu dừng.' if self.stop.is_set() else 'Đã đạt giới hạn request hoặc thời gian.'
            self.report['state'] = 'CANCELLED'
            self.report['reason'] = reason
            for item in self.report['scenarios']:
                if item['result'] is None:
                    item.update(result='CANCELLED', reason=reason)
            if any(s['result'] == 'FAILED' for s in self.report['scenarios']):
                self.report['state'] = 'FAILED'
        finally:
            present = {s['id'] for s in self.report['scenarios']}
            for sid in self.config.scenarios:
                if sid not in present: self.report['scenarios'].append({'id': sid, 'name': CATALOG[sid].name, 'result': 'SKIPPED', 'reason': 'Run đã dừng.'})
            self.report['finished_at'] = now()
            self.report['phase'] = 'finished'
            self.publish()
        return self.report

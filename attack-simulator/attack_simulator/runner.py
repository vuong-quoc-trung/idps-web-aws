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
from .authenticated import Session, AuthFailure, AUTH_SCENARIOS, WRITE_SCENARIOS, guarded_profile_payload, REPEATABLE
from .fixture_gate import FixtureGate
from .scenarios import CATALOG, request_spec


def now():
    return datetime.now(timezone.utc).isoformat()

class Halt(Exception):
    pass

class Runner:
    def __init__(self, config, stop=None, callback=None, client=None, credentials=None, fixture_gate=None, fixture_prompt=None):
        self.config = config
        self.client = client if client is not None else Client(config.target_endpoint(), config.timeout)
        self.session = Session(*credentials, self.client.target) if credentials is not None and any(s in AUTH_SCENARIOS for s in config.scenarios) else None
        self.fixture_gate = fixture_gate or FixtureGate()
        self.fixture_prompt = fixture_prompt
        self.cleanup = False
        self.stop = stop or threading.Event()
        self.callback = callback or (lambda r: None)
        self.report = {'run_id': uuid.uuid4().hex, 'started_at': now(), 'state': None, 'phase': 'requests', 'http_count': 0, 'requests': [], 'scenarios': [], 'target': config.target, 'limits': {'max_requests': config.max_requests, 'rate': config.rate, 'duration': config.duration, 'timeout': config.timeout}}
        self.next_at = 0

    def publish(self):
        self.callback(copy.deepcopy(self.report))

    def send(self, client, method, path, headers=None, body=None):
        c = self.config
        reserve = 1 if self.session and not self.cleanup else 0
        if (self.stop.is_set() and not self.cleanup) or self.report['http_count'] >= c.max_requests - reserve:
            raise Halt()
        wait = max(0, self.next_at - time.monotonic())
        deadline = self.deadline - (c.timeout + 1/c.rate if self.session and not self.cleanup else 0)
        if time.monotonic() + wait >= deadline: raise Halt()
        if self.cleanup: time.sleep(wait)
        elif self.stop.wait(wait): raise Halt()
        remaining = deadline - time.monotonic()
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
        if any(s in AUTH_SCENARIOS for s in self.config.scenarios):
            return self.execute_authenticated()
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

    def execute_authenticated(self):
        self.deadline = time.monotonic() + self.config.duration
        session = self.session
        first = CATALOG[self.config.scenarios[0]]
        current = None
        def request(s, method, path, stage='setup', body=None, index=0, json_body=False):
            headers = session.headers(path, write=method in ('POST','PUT'))
            if body is not None: headers['Content-Type'] = 'application/json' if json_body else 'application/x-www-form-urlencoded'
            response = self.receipt(s, index, method, path, headers, body, stage)
            session.accept(response)
            return response
        try:
            if session is None: raise AuthFailure('Cần credentials lab qua prompt hoặc UI.')
            session.csrf_from(request(first, 'GET', '/api/auth/csrf'))
            if not session.headers('/api/auth/login').get('Cookie'): raise AuthFailure('Không nhận được session cookie hợp lệ.')
            login = request(first, 'POST', '/api/auth/login', body=session.login_body())
            if login is None or login.status != 204: raise AuthFailure('Đăng nhập không thành công; không thử lại.')
            session.authenticated = True
            session.csrf = ''
            session.csrf_from(request(first, 'GET', '/api/auth/csrf'))
            session.verify(request(first, 'GET', '/api/auth/me'), self.config.auth_role)
            for sid in self.config.scenarios:
                s = CATALOG[sid]
                current = {'id': sid, 'name': s.name, 'result': None, 'reason': ''}
                self.report['scenarios'].append(current)
                if sid in WRITE_SCENARIOS:
                    if not (self.config.write_confirmed and self.config.safety_contract_confirmed):
                        current.update(result='SKIPPED', reason='Thiếu xác nhận riêng cho PUT lab hoặc contract validation an toàn.')
                        self.publish()
                        continue
                    if sid == 'workflow-abuse':
                        self.fixture_gate.open()
                        self.report['phase'] = 'awaiting_fixture'
                        self.publish()
                        if self.fixture_prompt: self.fixture_prompt(self.fixture_gate)
                        remaining = self.deadline - time.monotonic() - (2*self.config.timeout + 2/self.config.rate)
                        accepted = self.fixture_gate.wait(min(self.config.fixture_wait, max(0, remaining)), self.stop)
                        self.report['phase'] = 'requests'
                        if self.stop.is_set(): raise Halt()
                        if not accepted:
                            current.update(result='SKIPPED', reason='Không có xác nhận fixture sau login trong thời gian cho phép.')
                            self.publish()
                            continue
                    path = '/api/me/profile'
                    if not session.headers(path).get('Cookie') or not session.csrf:
                        current.update(result='SKIPPED', reason='Không còn session/CSRF hợp lệ để gửi PUT có kiểm soát.')
                        continue
                    response = request(s, 'PUT', path, stage='probe', body=guarded_profile_payload(), index=1, json_body=True)
                    if response is None: raise AuthFailure('PUT fixture có lỗi truyền tải; cần đối chiếu dữ liệu lab phía Defender.')
                    expected = 400 if sid == 'mass-assignment' else 401
                    if response.status == 401: session.authenticated = False
                    current['expected_http_status'] = expected
                    current['http_expectation_met'] = response.status == expected
                    if 200 <= response.status < 300:
                        raise AuthFailure('PUT bất ngờ được chấp nhận; dừng, không retry/rollback tự động; kiểm tra dữ liệu lab.')
                    current.update(result='COMPLETED', reason='Đã nhận HTTP response; không suy luận signal hoặc dữ liệu không đổi.')
                    self.publish()
                    if response.status == 401 and sid != 'workflow-abuse':
                        raise AuthFailure('Phiên hết hạn trước bài fixture; không tự đăng nhập lại.')
                    if 300 <= response.status < 400: raise AuthFailure('Nhận redirect; dừng và không theo redirect.')
                    continue
                paths = ([f'/api/me/{self.config.object_type}/{i}' for i in self.config.object_ids]
                         if sid == 'idor-get' else [AUTH_SCENARIOS[sid][1]] * (self.config.repeat if sid in REPEATABLE else 1))
                current['planned_requests'] = len(paths)
                for index, path in enumerate(paths):
                    if not session.headers(path).get('Cookie'): raise AuthFailure('Cookie không còn hợp lệ cho endpoint; dừng.')
                    response = request(s, 'GET', path, stage='probe', index=index+1)
                    if response is None: raise AuthFailure('Request có lỗi truyền tải; dừng phiên.')
                    if response.status == 401:
                        session.authenticated = False
                        raise AuthFailure('Phiên hết hạn hoặc bị thu hồi; không tự đăng nhập lại.')
                    if 300 <= response.status < 400:
                        raise AuthFailure('Nhận redirect; không theo redirect hoặc đăng nhập lại.')
                current.update(result='COMPLETED', reason='Đã nhận HTTP response cho các GET fixture.')
                self.publish()
            self.report['state'] = 'SKIPPED' if all(s['result']=='SKIPPED' for s in self.report['scenarios']) else 'COMPLETED'
        except AuthFailure as error:
            self.report.update(state='FAILED', reason=str(error))
            if current is not None: current.update(result='FAILED', reason=str(error))
            else: self.report['scenarios'].append({'id':first.id, 'name':first.name, 'result':'FAILED', 'reason':str(error)})
        except Halt:
            self.report.update(state='CANCELLED', reason='Đã dừng hoặc đạt giới hạn; không gửi thêm probe.')
            if current is not None and current['result'] is None: current.update(result='CANCELLED', reason=self.report['reason'])
        finally:
            try:
                self.cleanup = True
                if session and session.authenticated and session.cookie:
                    logout = request(first, 'POST', '/api/auth/logout', stage='logout')
                    self.report['logout'] = 'COMPLETED' if logout and logout.status == 204 else 'FAILED'
                else: self.report['logout'] = 'SKIPPED'
            except Halt:
                self.report['logout'] = 'SKIPPED'
            finally:
                if session: session.clear()
                self.session = None
                self.cleanup = False
            present = {s['id'] for s in self.report['scenarios']}
            for sid in self.config.scenarios:
                if sid not in present: self.report['scenarios'].append({'id':sid,'name':CATALOG[sid].name,'result':'SKIPPED','reason':'Chưa chạy.'})
            self.report.update(finished_at=now(), phase='finished')
            self.publish()
        return self.report

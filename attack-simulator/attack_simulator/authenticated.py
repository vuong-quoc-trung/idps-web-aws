"""Run-local Spring form session. No persistence or Defender access."""
import json
import re
import time
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlencode
from .http_client import ValidationError

REPEATABLE = frozenset(('student-users', 'student-students', 'staff-users'))

AUTH_SCENARIOS = {
    'student-users': ('STUDENT', '/api/users'),
    'student-students': ('STUDENT', '/api/students'),
    'staff-users': ('STAFF', '/api/users'),
    'idor-get': ('STUDENT', None),
    'mass-assignment': ('STUDENT', '/api/me/profile'),
    'workflow-abuse': ('STUDENT', '/api/me/profile'),
}
UNSUPPORTED = ('privilege-change', 'authenticated-csrf')
WRITE_SCENARIOS = frozenset(('mass-assignment', 'workflow-abuse'))

def guarded_profile_payload():
    # ProtectedFieldAdvice rejects role before binding; @Valid also rejects >150 chars.
    # Never send a DTO which could pass validation if the forbidden-field check is absent.
    return json.dumps({'role': 'STUDENT', 'placeOfBirth': 'L' * 151})

class AuthFailure(Exception):
    """Only fixed, non-sensitive messages may be raised."""

class Session:
    def __init__(self, username, password, target):
        if not isinstance(username, str) or not 1 <= len(username) <= 64 or any(ord(c)<32 for c in username):
            raise ValidationError('Cần username lab hợp lệ.')
        if not isinstance(password, str) or not 1 <= len(password) <= 256:
            raise ValidationError('Cần password lab, tối đa 256 ký tự.')
        self.username, self.password, self.target = username, password, target
        self.cookie = ''
        self.cookie_path = '/'
        self.cookie_secure = False
        self.expires_at = None
        self.csrf = ''
        self.authenticated = False

    def headers(self, path, write=False):
        headers = {}
        if self.expires_at is not None and time.time() >= self.expires_at:
            self.cookie = ''
        path_matches = path == self.cookie_path or path.startswith(self.cookie_path.rstrip('/') + '/')
        if self.cookie and path_matches and (not self.cookie_secure or self.target.scheme == 'https'):
            headers['Cookie'] = 'JSESSIONID=' + self.cookie
        if write and self.csrf: headers['X-CSRF-TOKEN'] = self.csrf
        return headers

    def accept(self, response):
        if response is None: return
        values = response.set_cookies or [response.headers.get('set-cookie', '')]
        for raw in values:
            if len(raw)>8192: continue
            jar = SimpleCookie()
            try: jar.load(raw)
            except CookieError: continue
            if 'JSESSIONID' not in jar: continue
            item = jar['JSESSIONID']
            domain = item['domain'].lstrip('.').lower()
            if domain and domain != self.target.host: continue
            if item['secure'] and self.target.scheme != 'https': continue
            expires_at = None
            if item['expires']:
                try: expires_at = parsedate_to_datetime(item['expires']).timestamp()
                except (ValueError, TypeError, OverflowError): continue
            if item['max-age']:
                try:
                    expires_at = time.time() + int(item['max-age'])
                    if int(item['max-age']) <= 0:
                        self.cookie = ''; continue
                except ValueError: continue
            if expires_at is not None and expires_at <= time.time():
                self.cookie = ''; continue
            if not re.fullmatch(r'[A-Za-z0-9._~-]{1,256}', item.value): continue
            self.expires_at = expires_at
            self.cookie, self.cookie_path, self.cookie_secure = item.value, item['path'] or '/api/auth', bool(item['secure'])

    def csrf_from(self, response):
        try:
            if response is None or response.status != 200 or response.truncated: raise ValueError()
            data = json.loads(response.body)
            token = data.get('token')
            if data.get('headerName') != 'X-CSRF-TOKEN' or not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<32 or ord(c)>126 for c in token): raise ValueError()
            self.csrf = token
        except (ValueError, AttributeError, TypeError):
            raise AuthFailure('Không lấy được CSRF hợp lệ.') from None

    def login_body(self):
        body = urlencode({'username':self.username, 'password':self.password})
        self.password = ''
        return body

    def verify(self, response, expected_role):
        try:
            if response is None or response.status != 200 or response.truncated: raise ValueError()
            data = json.loads(response.body)
            valid = (data.get('username') == self.username and data.get('role') == expected_role
                     and expected_role in ('STUDENT','STAFF') and data.get('enabled') is True
                     and data.get('passwordSetupRequired') is False)
            if not valid: raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise AuthFailure('Không xác minh được tài khoản/role lab; không gửi probe.') from None
        self.username = ''

    def clear(self):
        self.username = self.password = self.cookie = self.csrf = ''
        self.expires_at = None
        self.authenticated = False

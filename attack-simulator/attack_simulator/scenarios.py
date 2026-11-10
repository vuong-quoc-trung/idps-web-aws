"""Static lab markers; no arbitrary payload upload or destructive endpoints."""
from dataclasses import dataclass, asdict
from urllib.parse import urlencode

@dataclass(frozen=True)
class Scenario:
    id: str
    group: str
    name: str
    count: int
    profile: str = 'safe'
    fixture: bool = False
    method: str = 'GET'
    marker: str = ''

SCENARIOS = [
    Scenario('baseline', 'Baseline', 'HTTP bình thường', 1, profile='safe', fixture=False, method='GET', marker=''),
    Scenario('sqli', 'Signature', 'SQLi query marker', 1, profile='safe', fixture=False, method='GET', marker="' OR '1'='1"),
    Scenario('xss', 'Signature', 'XSS query marker', 1, profile='safe', fixture=False, method='GET', marker='<script>void(0)</script>'),
    Scenario('traversal', 'Signature', 'Traversal query marker', 1, profile='safe', fixture=False, method='GET', marker='../../pbl4-nonexistent'),
    Scenario('command', 'Signature', 'Command query marker', 1, profile='safe', fixture=False, method='GET', marker=';whoami'),
    Scenario('scanner', 'Signature', 'Scanner User-Agent', 1, profile='safe', fixture=False, method='GET', marker=''),
    Scenario('method', 'Signature', 'WebDAV method observation', 1, profile='safe', fixture=False, method='PROPFIND', marker=''),
    Scenario('auth-get', 'Authentication', '10 GET auth không có phiên', 10, profile='bounded', fixture=False, method='GET', marker=''),
    Scenario('login-failure', 'Authentication', '10 login failure tài khoản lab', 10, profile='bounded', fixture=True, method='POST', marker=''),
    Scenario('csrf', 'Authentication', '5 POST thiếu CSRF với fixture lab', 5, profile='bounded', fixture=True, method='POST', marker=''),
    Scenario('enumeration', 'Behavior', '20 path không tồn tại', 20, profile='behavior', fixture=False, method='GET', marker=''),
    Scenario('burst', 'Behavior', '120 request có giới hạn', 120, profile='behavior', fixture=False, method='GET', marker=''),
    Scenario('ai-shadow', 'AI Shadow', 'AI Shadow · HTTP probe', 1, profile='safe', fixture=False, method='GET', marker=''),
]
CATALOG = {s.id: s for s in SCENARIOS}

def catalog():
    return [asdict(s) for s in SCENARIOS]

def request_spec(s, index, run_id):
    path = '/api/auth/me'
    headers = {}
    if s.marker:
        path += '?' + urlencode({'pbl4_probe': s.marker})
    if s.id == 'scanner':
        headers['User-Agent'] = 'PBL4-Lab nikto signature-test'
    if s.id == 'enumeration':
        path = f'/api/pbl4-simulator-missing/{run_id}/{index}'
    if s.id in ('login-failure', 'csrf'):
        path = '/api/auth/login'
    return s.method, path, headers

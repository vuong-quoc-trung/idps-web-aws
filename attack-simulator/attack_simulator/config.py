"""Strict run configuration. Secrets are never configuration/report fields."""
from dataclasses import dataclass, field
from .http_client import ValidationError, Target
from .scenarios import CATALOG
from .authenticated import AUTH_SCENARIOS

@dataclass
class Config:
    target: str = ''
    auth_role: str = ''
    auth_confirmed: bool = False
    write_confirmed: bool = False
    safety_contract_confirmed: bool = False
    fixture_wait: float = 90
    object_type: str = 'family-members'
    object_ids: list = field(default_factory=list)
    scenarios: list = field(default_factory=lambda: ['baseline'])
    authorized: bool = False
    confirm_multiple: bool = False
    profile: str = 'safe'
    fixture_confirmed: bool = False
    lab_username: str = ''
    max_requests: int = 60
    rate: float = 2
    timeout: float = 5
    duration: float = 120
    allowlist: list = field(default_factory=list)

    @classmethod
    def load(cls, values):
        if not isinstance(values, dict) or set(values) - set(cls.__dataclass_fields__):
            raise ValidationError('Config có trường không hỗ trợ.')
        c = cls(**values)
        for name in ('authorized', 'confirm_multiple', 'fixture_confirmed', 'auth_confirmed', 'write_confirmed', 'safety_contract_confirmed'):
            if type(getattr(c, name)) is not bool:
                raise ValidationError('Confirmation phải là boolean.')
        for name in ('target', 'lab_username', 'profile', 'auth_role', 'object_type'):
            if not isinstance(getattr(c, name), str):
                raise ValidationError('Trường URL/profile/username phải là chuỗi.')
        if not c.authorized:
            raise ValidationError('Cần xác nhận mục tiêu lab được phép kiểm thử.')
        if not isinstance(c.scenarios, list) or not c.scenarios or len(c.scenarios) > len(CATALOG) or any(not isinstance(s, str) or s not in CATALOG for s in c.scenarios) or len(set(c.scenarios)) != len(c.scenarios):
            raise ValidationError('Scenario không hợp lệ hoặc bị trùng.')
        if not isinstance(c.allowlist, list) or len(c.allowlist) > 16 or any(not isinstance(s, str) for s in c.allowlist):
            raise ValidationError('Allowlist tối đa 16 origin.')
        if len(c.lab_username) > 64 or any(ord(x) < 32 for x in c.lab_username):
            raise ValidationError('Username fixture không hợp lệ.')
        for name, low, high in [('max_requests', 1, 200), ('rate', .1, 5), ('timeout', .1, 10), ('duration', 1, 300), ('fixture_wait', 1, 180)]:
            v = getattr(c, name)
            if type(v) not in (int, float) or not low <= v <= high or name == 'max_requests' and type(v) is not int:
                raise ValidationError(f'{name} phải trong [{low}, {high}].')
        auth = [sid for sid in c.scenarios if sid in AUTH_SCENARIOS]
        if c.auth_role not in ('', 'STUDENT', 'STAFF'):
            raise ValidationError('Chỉ hỗ trợ STUDENT hoặc STAFF.')
        if c.object_type not in ('family-members', 'emergency-contacts', 'post-graduation-contacts'):
            raise ValidationError('Object type không được hỗ trợ.')
        if not isinstance(c.object_ids, list) or len(c.object_ids)>20 or any(type(i) is not int or not 1<=i<=9007199254740991 for i in c.object_ids) or len(set(c.object_ids))!=len(c.object_ids):
            raise ValidationError('Fixture tối đa 20 ID dương duy nhất.')
        if not auth and c.auth_role: raise ValidationError('Chỉ chọn auth role cho authenticated scenario.')
        if auth:
            if len(auth)!=len(c.scenarios): raise ValidationError('Chạy authenticated và 13 scenario cũ trong các run riêng.')
            if not c.auth_confirmed: raise ValidationError('Cần xác nhận tài khoản và object fixture lab riêng.')
            if any(AUTH_SCENARIOS[sid][0]!=c.auth_role for sid in auth): raise ValidationError('Scenario không phù hợp role đã chọn.')
            if 'idor-get' in auth and not c.object_ids: raise ValidationError('IDOR chỉ dùng ID fixture được cung cấp trước.')
            if c.duration < 2*c.timeout + 2/c.rate: raise ValidationError('Duration cần đủ thời gian dành riêng cho logout.')
        if 'workflow-abuse' in c.scenarios and c.scenarios[-1] != 'workflow-abuse':
            raise ValidationError('Workflow phải là scenario cuối vì có thể thu hồi phiên.')
        planned = sum(len(c.object_ids) if sid == 'idor-get' else CATALOG[sid].count + int(CATALOG[sid].fixture) for sid in c.scenarios) + (5 if auth else 0)
        if planned > 1 and not c.confirm_multiple:
            raise ValidationError('Nhiều request cần confirm_multiple rõ ràng.')
        if c.profile not in ('safe', 'behavior') or any(CATALOG[s].profile == 'behavior' for s in c.scenarios) and c.profile != 'behavior':
            raise ValidationError('Enumeration/burst cần profile behavior.')
        if planned > c.max_requests:
            raise ValidationError(f'Cần budget ít nhất {planned} request (gồm setup).')
        return c

    def target_endpoint(self):
        return Target.create(self.target, self.allowlist)

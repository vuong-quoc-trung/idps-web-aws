"""Strict run configuration. Secrets are never configuration/report fields."""
from dataclasses import dataclass, field
from .http_client import ValidationError, Target
from .scenarios import CATALOG

@dataclass
class Config:
    target: str = ''
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
        for name in ('authorized', 'confirm_multiple', 'fixture_confirmed'):
            if type(getattr(c, name)) is not bool:
                raise ValidationError('Confirmation phải là boolean.')
        for name in ('target', 'lab_username', 'profile'):
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
        for name, low, high in [('max_requests', 1, 200), ('rate', .1, 5), ('timeout', .1, 10), ('duration', 1, 300)]:
            v = getattr(c, name)
            if type(v) not in (int, float) or not low <= v <= high or name == 'max_requests' and type(v) is not int:
                raise ValidationError(f'{name} phải trong [{low}, {high}].')
        planned = sum(CATALOG[s].count + int(CATALOG[s].fixture) for s in c.scenarios)
        if planned > 1 and not c.confirm_multiple:
            raise ValidationError('Nhiều request cần confirm_multiple rõ ràng.')
        if c.profile not in ('safe', 'behavior') or any(CATALOG[s].profile == 'behavior' for s in c.scenarios) and c.profile != 'behavior':
            raise ValidationError('Enumeration/burst cần profile behavior.')
        if planned > c.max_requests:
            raise ValidationError(f'Cần budget ít nhất {planned} request (gồm setup).')
        return c

    def target_endpoint(self):
        return Target.create(self.target, self.allowlist)

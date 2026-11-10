import argparse
import json
import getpass
import warnings
import signal
import threading
from .config import Config
from .http_client import ValidationError
from .scenarios import catalog
from .reports import save
from .runner import Runner


def main(argv=None):
    p = argparse.ArgumentParser(description='Authorized lab Attacker: HTTP request/response only')
    p.add_argument('--list', action='store_true')
    p.add_argument('--config')
    p.add_argument('--target')
    p.add_argument('--scenario', action='append', choices=[s['id'] for s in catalog()])
    p.add_argument('--authorized', action='store_true', default=None)
    p.add_argument('--confirm-multiple', action='store_true', default=None)
    p.add_argument('--fixture-confirmed', action='store_true', default=None)
    p.add_argument('--lab-username')
    p.add_argument('--auth-role', choices=['STUDENT','STAFF'])
    p.add_argument('--auth-confirmed', action='store_true', default=None)
    p.add_argument('--write-confirmed', action='store_true', default=None, help='Cho phép PUT cố định trên dữ liệu lab riêng')
    p.add_argument('--safety-contract-confirmed', action='store_true', default=None, help='Đã đối chiếu backend: protected fields và @Valid placeOfBirth max150 trước ghi')
    p.add_argument('--fixture-wait', type=float, help='Thời gian chờ xác nhận workflow sau login (1–180s)')
    p.add_argument('--object-type', choices=['family-members','emergency-contacts','post-graduation-contacts'])
    p.add_argument('--object-ids', type=lambda v: [int(x) for x in v.split(',')])
    p.add_argument('--profile', choices=['safe', 'behavior'])
    p.add_argument('--max-requests', type=int)
    p.add_argument('--repeat', type=int, default=None, help='1–8 GET mỗi scenario student-users/student-students/staff-users; mặc định1, rate tối đa2/s')
    for name in ('rate', 'timeout', 'duration'): p.add_argument('--'+name, type=float)
    p.add_argument('--report', default='reports/latest.json')
    p.add_argument('--web', action='store_true')
    p.add_argument('--port', type=int, default=8765)
    args = p.parse_args(argv)
    if args.list:
        for s in catalog(): print(f"{s['id']:16} {s['count']:3} requests | {s['name']}")
        return 0
    try:
        values = {}
        if args.config:
            with open(args.config, encoding='utf-8') as f: values = json.load(f)
            if not isinstance(values, dict): raise ValidationError('Config phải là JSON object.')
        for k in Config.__dataclass_fields__:
            value = getattr(args, 'scenario' if k == 'scenarios' else k, None)
            if value is not None: values[k] = value
        if args.web:
            if not 1024 <= args.port <= 65535: raise ValidationError('Port phải trong 1024–65535.')
            try:
                from .web import serve
            except ImportError:
                p.error('Web UI cần: python -m pip install -e ".[web]"')
            serve(values, args.port)
            return 0
        config = Config.load(values)
        stop = threading.Event()
        old = signal.signal(signal.SIGINT, lambda *_: stop.set())
        try:
            credentials = None
            if config.auth_role:
                username = input('Lab username: ')
                with warnings.catch_warnings():
                    warnings.simplefilter('error', getpass.GetPassWarning)
                    try: password = getpass.getpass('Lab password: ')
                    except getpass.GetPassWarning: raise ValidationError('Cần terminal hỗ trợ nhập password ẩn.') from None
                credentials = (username, password)
                username = password = ''
            try:
                def fixture_prompt(gate):
                    def read_confirmation():
                        try:
                            answer = input('Phiên đã đăng nhập. Trên Defender chỉ vô hiệu hóa tài khoản LAB của run này; không gửi request bằng phiên này. Nhập DISABLED để xác nhận fixture, hoặc Enter để bỏ qua: ')
                            gate.confirm(answer == 'DISABLED')
                        except (EOFError, OSError): gate.confirm(False)
                    threading.Thread(target=read_confirmation, daemon=True).start()
                runner = Runner(config, stop=stop, credentials=credentials, fixture_prompt=fixture_prompt)
            finally:
                credentials = None
            result = runner.execute()
        finally:
            signal.signal(signal.SIGINT, old)
        save(result, args.report)
        for s in result['scenarios']: print(f"{s['id']}: {s['result']} — {s['reason']}")
        print(f"{result['http_count']} HTTP requests (including fixture setup); report: {args.report}")
        return 1 if result['state'] == 'FAILED' else 130 if result['state'] == 'CANCELLED' else 0
    except (ValidationError, OSError, ValueError) as e:
        # Configuration errors are local; no response bodies/credentials are printed.
        p.error(str(e) if isinstance(e, ValidationError) else 'Không khởi chạy được: kiểm tra config/report, quyền mở cổng và cổng đang sử dụng.')

if __name__ == '__main__':
    raise SystemExit(main())

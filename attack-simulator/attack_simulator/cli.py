import argparse
import json
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
    p.add_argument('--profile', choices=['safe', 'behavior'])
    p.add_argument('--max-requests', type=int)
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
            runner = Runner(config, stop=stop)
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

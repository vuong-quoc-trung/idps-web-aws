"""Local-only control plane; one bounded job, no persistent credentials."""
import copy
import secrets
import threading
from time import monotonic
from flask import Flask, jsonify, request, render_template, Response
from . import aws_canary, aws_smoke
from .config import Config
from .http_client import ValidationError
from .runner import Runner
from .fixture_gate import FixtureGate
from .scenarios import catalog
from .reports import render


def create_app(defaults=None, port=8765, runner_factory=Runner, *, demo_only=False, live_key=None):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 16384
    app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '::1']
    csrf = secrets.token_urlsafe(32)
    aws_lock = threading.Lock()
    aws_next_run = 0.0

    @app.before_request
    def protect():
        if request.host not in (f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'):
            return jsonify(error='Invalid host'), 403
        if request.headers.get('Sec-Fetch-Site') == 'cross-site': return jsonify(error='Cross-site blocked'), 403
        if request.headers.get('Origin') and request.headers['Origin'] != f'http://{request.host}': return jsonify(error='Origin blocked'), 403
        if request.path.startswith('/api/') and not secrets.compare_digest(request.headers.get('X-Simulator-Token', ''), csrf):
            return jsonify(error='CSRF token required'), 403

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/pbl4')
    def pbl4():
        return render_template('pbl4.html', csrf=csrf, live_enabled=live_key is not None)

    @app.post('/api/aws-smoke')
    def aws_health():
        nonlocal aws_next_run
        if request.query_string or request.get_data():
            return jsonify(error='Kiểm tra AWS không nhận URL hoặc tham số.'), 400
        if not aws_lock.acquire(blocking=False):
            return jsonify(error='Đang kiểm tra AWS.'), 409
        try:
            if monotonic() < aws_next_run:
                return jsonify(error='Vui lòng đợi 5 giây trước khi chạy lại.'), 429
            try:
                return jsonify(results=aws_smoke.check())
            finally:
                aws_next_run = monotonic() + 5
        finally:
            aws_lock.release()

    if demo_only and live_key is not None:
        live_lock = threading.Lock()
        live_next_run = 0.0

        @app.post('/api/pbl4-canary')
        def pbl4_canary():
            nonlocal live_next_run
            access_key = request.headers.get('X-PBL4-Session', '')
            if not secrets.compare_digest(access_key.encode(), live_key.encode()):
                return jsonify(error='Mở liên kết phiên live đã in trong Terminal.'), 403
            if request.query_string or request.get_data():
                return jsonify(error='Canary chỉ dùng cấu hình EC2 cố định.'), 400
            if not live_lock.acquire(blocking=False):
                return jsonify(error='Canary đang chạy.'), 409
            try:
                if monotonic() < live_next_run:
                    return jsonify(error='Chờ hết thời hạn lượt trước rồi chạy lại.'), 429
                live_next_run = monotonic() + 260
                try:
                    result = aws_canary.run()
                except aws_canary.CanaryError as error:
                    return jsonify(error=str(error)), 503
                live_next_run = monotonic() + 10
                return jsonify(result=result)
            finally:
                live_lock.release()

    if demo_only:
        app.add_url_rule('/', view_func=pbl4)
        return app

    lock = threading.Lock()
    state = {'active': False, 'report': None, 'stop': None, 'thread': None, 'gate': None}
    defaults = dict(defaults or {})
    if set(defaults) - set(Config.__dataclass_fields__):
        raise ValidationError("Config có trường không hỗ trợ.")
    # Consent must be explicitly given for each UI run, never inherited.
    for key in ('authorized', 'confirm_multiple', 'fixture_confirmed', 'auth_confirmed', 'write_confirmed', 'safety_contract_confirmed'): defaults.pop(key, None)

    @app.get('/')
    def home():
        return render_template('index.html', csrf=csrf, scenarios=catalog(), defaults=defaults)

    @app.get('/api/state')
    def status():
        with lock: return jsonify(active=state['active'], report=state['report'])

    def publish(report):
        with lock: state['report'] = report

    @app.post('/api/run')
    def run():
        data = request.get_json(silent=True)
        if not isinstance(data, dict): return jsonify(error='JSON object required'), 400
        credentials = data.pop('credentials', None)
        if credentials is not None:
            if not isinstance(credentials, dict) or set(credentials) != {'username','password'}:
                return jsonify(error='Credentials không hợp lệ.'), 400
            credentials = (credentials['username'], credentials['password'])
        if 'allowlist' in data: return jsonify(error='Allowlist chỉ cấu hình lúc khởi động.'), 400
        try:
            config = Config.load({**defaults, **data})
        except ValidationError as e: return jsonify(error=str(e)), 400
        with lock:
            if state['active']: return jsonify(error='Một run đang hoạt động.'), 409
            state['active'] = True
            state['stop'] = threading.Event()
            state['gate'] = FixtureGate()
        try:
            runner = runner_factory(config, credentials=credentials, fixture_gate=state['gate'], stop=state['stop'], callback=publish)
        except ValidationError as e:
            with lock: state['active'] = False
            return jsonify(error=str(e)), 400
        credentials = None
        def work():
            try:
                runner.execute()
            except Exception:
                # No raw exceptions (may contain secrets) in API or logs.
                publish({'state': 'FAILED', 'requests': [], 'scenarios': [], 'http_count': 0})
            finally:
                with lock: state['active'] = False
        with lock: state['report'] = copy.deepcopy(runner.report)
        worker = threading.Thread(target=work, daemon=True)
        with lock: state['thread'] = worker
        worker.start()
        return jsonify(started=True), 202

    @app.post('/api/fixture-confirm')
    def fixture_confirm():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'run_id', 'confirmed'} or type(data['confirmed']) is not bool:
            return jsonify(error='Cần run_id và xác nhận boolean.'), 400
        with lock:
            report = state['report'] or {}
            if not state['active'] or report.get('run_id') != data['run_id'] or report.get('phase') != 'awaiting_fixture':
                return jsonify(error='Không có run tương ứng đang chờ fixture.'), 409
            accepted = state['gate'].confirm(data['confirmed'])
        if not accepted: return jsonify(error='Xác nhận đã hết hạn hoặc đã dùng.'), 409
        return jsonify(accepted=True)

    @app.post('/api/stop')
    def stop():
        with lock:
            if state['stop']: state['stop'].set()
        return jsonify(stopping=True)

    @app.get('/api/report/<fmt>')
    def download(fmt):
        if fmt not in ('json', 'csv'): return jsonify(error='Unknown format'), 404
        with lock: report = copy.deepcopy(state['report'])
        if not report: return jsonify(error='No report'), 404
        return Response(render(report, fmt), mimetype='application/json' if fmt == 'json' else 'text/csv', headers={'Content-Disposition': f'attachment; filename="simulator-report.{fmt}"'})
    def shutdown():
        with lock:
            if state['stop']: state['stop'].set()
            worker = state['thread']
        if worker: worker.join(timeout=35)
    app.extensions['simulator_shutdown'] = shutdown
    return app


def serve(defaults, port, *, demo_only=False, live=False):
    from werkzeug.serving import make_server
    live_key = secrets.token_urlsafe(32) if live else None
    app = create_app(defaults, port, demo_only=demo_only, live_key=live_key)
    fragment = f'#live={live_key}' if live_key else ''
    with make_server('127.0.0.1', port, app, threaded=True) as server:
        print(f'Trình diễn PBL4: http://127.0.0.1:{port}/pbl4{fragment} (Ctrl+C để dừng)', flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally:
            shutdown = app.extensions.get('simulator_shutdown')
            if shutdown is not None:
                shutdown()

"""Local-only control plane; one bounded job, no persistent credentials."""
import copy
import secrets
import threading
from flask import Flask, jsonify, request, render_template, Response
from .config import Config
from .http_client import ValidationError
from .runner import Runner
from .fixture_gate import FixtureGate
from .scenarios import catalog
from .reports import render


def create_app(defaults=None, port=8765, runner_factory=Runner):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 16384
    app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '::1']
    csrf = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state = {'active': False, 'report': None, 'stop': None, 'thread': None, 'gate': None}
    defaults = dict(defaults or {})
    if set(defaults) - set(Config.__dataclass_fields__):
        raise ValidationError("Config có trường không hỗ trợ.")
    # Consent must be explicitly given for each UI run, never inherited.
    for key in ('authorized', 'confirm_multiple', 'fixture_confirmed', 'auth_confirmed', 'write_confirmed', 'safety_contract_confirmed'): defaults.pop(key, None)

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


def serve(defaults, port):
    from werkzeug.serving import make_server
    app = create_app(defaults, port)
    print(f'Attack Simulator: http://127.0.0.1:{port} (Ctrl+C to stop)')
    with make_server('127.0.0.1', port, app, threaded=True) as server:
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: app.extensions['simulator_shutdown']()

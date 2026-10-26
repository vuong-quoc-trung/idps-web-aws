#!/usr/bin/env python3
"""Isolated local foundation stack. Never installs services or changes host firewall.

Default ports differ from existing Compose instances; volumes survive --stop.
All generated credentials and logs live in an ignored, private runtime directory.
"""
import argparse
import hashlib
import http.cookiejar
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.local-dev' / 'foundation'
STATE = RUNTIME / 'processes.json'


def run(command, *, cwd=ROOT, env=None, capture=False):
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def sql(container, database, statement):
    return run(['docker', 'exec', container, 'psql', '-U', 'postgres', '-d', database,
                '-At', '-v', 'ON_ERROR_STOP=1', '-c', statement], capture=True).stdout.strip()


def process_token(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def start(name, command, cwd, environment):
    state = load_state()
    old = state.get(name, {})
    if old and process_token(old['pid']) == old['start_token']:
        print(f'{name}: already running ({old["pid"]})', flush=True)
        return
    with (RUNTIME / f'{name}.log').open('ab') as output:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=output, start_new_session=True)
    state[name] = {'pid': process.pid, 'start_token': process_token(process.pid)}
    STATE.write_text(json.dumps(state, indent=2) + '\n')
    print(f'{name}: started ({process.pid})', flush=True)


def stop():
    for name, item in load_state().items():
        if process_token(item['pid']) == item['start_token']:
            os.killpg(item['pid'], signal.SIGTERM)
            print(f'{name}: stopping')
    for name in ['idps-foundation-student', 'idps-foundation-security']:
        subprocess.run(['docker', 'stop', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if STATE.exists():
        STATE.unlink()
    print('Stopped only foundation processes/containers; volumes and credentials retained.')


def free_port(port, address="127.0.0.1"):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((address, port))


def wait_http(url, expected=(200,), timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status in expected:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(.5)
    raise RuntimeError(f'timed out waiting for {url}; inspect private runtime logs')


def postgres(name, image, port, database, password):
    exists = subprocess.run(['docker', 'container', 'inspect', name], capture_output=True).returncode == 0
    if exists:
        run(['docker', 'start', name], capture=True)
        # Refuse to claim readiness for an unrelated container/port.
        mapping = run(['docker', 'port', name, '5432/tcp'], capture=True).stdout.strip()
        if mapping != f'127.0.0.1:{port}':
            raise RuntimeError(f'{name} port mapping differs; use its existing DEV_* port or --stop')
    else:
        free_port(port)
        environment = os.environ | {'POSTGRES_PASSWORD': password}
        run(['docker', 'run', '-d', '--name', name, '--label', 'idps.foundation=true',
             '-e', 'POSTGRES_PASSWORD', '-e', f'POSTGRES_DB={database}',
             '-p', f'127.0.0.1:{port}:5432', '-v', f'{name}-data:/var/lib/postgresql/data', image], env=environment, capture=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres'], capture_output=True).returncode == 0:
            return
        time.sleep(.5)
    raise RuntimeError(f'{name} did not become ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--expose-lan', action='store_true', help='bind only the dev edge to 0.0.0.0; API/frontend remain loopback')
    parser.add_argument('--bootstrap-nginx', action='store_true', help='extract Ubuntu nginx .deb locally without sudo/installing a system service')
    parser.add_argument('--skip-build', action='store_true', help='use already built Java/Rust/frontend dependencies')
    args = parser.parse_args()
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.stop:
        stop()
        return
    nginx = os.environ.get('NGINX_BIN') or shutil.which('nginx')
    if not nginx and args.bootstrap_nginx:
        tools = RUNTIME / 'tools'
        tools.mkdir(exist_ok=True)
        run(['apt-get', 'download', 'nginx', 'nginx-common'], cwd=tools, capture=True)
        for package in tools.glob('*.deb'):
            run(['dpkg-deb', '-x', str(package), str(tools / 'runtime')], capture=True)
        nginx = str(tools / 'runtime/usr/sbin/nginx')
    if not nginx:
        raise RuntimeError('nginx unavailable: set NGINX_BIN or use --bootstrap-nginx on Ubuntu')
    credentials = RUNTIME / 'credentials.json'
    if credentials.exists():
        secret = json.loads(credentials.read_text())
    else:
        secret = {name: secrets.token_hex(24) for name in ['student_db_password', 'security_db_password', 'hmac_key', 'security_admin_password']}
        credentials.write_text(json.dumps(secret, indent=2) + '\n')
    if 'student_admin_password' not in secret:
        secret['student_admin_password'] = 'Dev-' + secrets.token_urlsafe(24) + '!9Aa'
        credentials.write_text(json.dumps(secret,indent=2)+'\n')
    ports = {'student_db': int(os.environ.get('DEV_STUDENT_DB_PORT', '55433')),
             'security_db': int(os.environ.get('DEV_SECURITY_DB_PORT', '55434')),
             'api': int(os.environ.get('DEV_API_PORT', '8080')),
             'frontend': int(os.environ.get('DEV_FRONTEND_PORT', '5173')),
             'security': int(os.environ.get('DEV_SECURITY_PORT', '3001')),
             'edge': int(os.environ.get('DEV_EDGE_PORT', '18780'))}
    edge_bind = '0.0.0.0' if args.expose_lan else '127.0.0.1'
    configuration = RUNTIME/'configuration.json'
    desired = {'ports':ports,'edge_bind':edge_bind}
    if configuration.exists() and json.loads(configuration.read_text()) != desired:
        if any(process_token(v['pid'])==v['start_token'] for v in load_state().values()):
            raise RuntimeError('running foundation configuration differs; run --stop before changing ports/exposure')
    configuration.write_text(json.dumps(desired,indent=2)+'\n')
    for name in ['student_db', 'security_db']:
        postgres('idps-foundation-' + name.replace('_db', ''), 'postgres:16-alpine' if name == 'student_db' else 'postgres:17-alpine',
                 ports[name], 'student_db' if name == 'student_db' else 'security_db', secret[name + '_password'])
    if not args.skip_build:
        print('Building existing Java/Rust stack and preparing frontend...', flush=True)
        with (RUNTIME/'build.log').open('w') as output:
            subprocess.run(['./mvnw', '-q', 'package', '-DskipTests'], cwd=ROOT/'student-web/backend', stdout=output, stderr=output, check=True)
            subprocess.run(['cargo', 'build', '--locked', '-j', '2'], cwd=ROOT/'security-web', stdout=output, stderr=output, check=True)
            subprocess.run(['npm', 'ci'], cwd=ROOT/'security-web/frontend', stdout=output, stderr=output, check=True)
            subprocess.run(['npm', 'run', 'build'], cwd=ROOT/'security-web/frontend', stdout=output, stderr=output, check=True)
            subprocess.run(['npm', 'ci'], cwd=ROOT/'student-web/frontend', stdout=output, stderr=output, check=True)
            subprocess.run(['npm', 'run', 'build'], cwd=ROOT/'student-web/frontend', stdout=output, stderr=output, check=True)
    for name in ['student-audit', 'nginx', 'suricata']:
        (RUNTIME/name).mkdir(exist_ok=True, mode=0o700)
    audit = RUNTIME/'student-audit/student-audit.log'
    access = RUNTIME/'nginx/access.log'
    eve = RUNTIME/'suricata/eve.json'
    for path in [audit, access, eve]:
        path.touch(mode=0o600, exist_ok=True)
    # Only the designated private dev processes are reused. An unrelated listener causes failure.
    state = load_state()
    for name, port in [('student', ports['api']), ('frontend', ports['frontend']), ('security', ports['security']), ('nginx', ports['edge'])]:
        item = state.get(name, {})
        if not item or process_token(item['pid']) != item['start_token']:
            free_port(port, edge_bind if name == "nginx" else "127.0.0.1")
    environment = os.environ | {'DB_URL': f'jdbc:postgresql://127.0.0.1:{ports["student_db"]}/student_db',
        'DB_USERNAME': 'postgres', 'DB_PASSWORD': secret['student_db_password'], 'STUDENT_BIND_ADDRESS': '127.0.0.1',
        'SERVER_PORT': str(ports['api']), 'STUDENT_AUDIT_LOG_ENABLED': 'true', 'STUDENT_AUDIT_LOG_PATH': str(audit),
        'STUDENT_AUDIT_HMAC_KEY': secret['hmac_key'], 'AUDIT_INCLUDE_SUCCESSFUL_READS': 'true',
        'TRUSTED_PROXIES': '127.0.0.1/32,::1/128', 'BOOTSTRAP_ADMIN_ENABLED': 'true',
        'BOOTSTRAP_ADMIN_USERNAME': 'foundation-admin', 'BOOTSTRAP_ADMIN_PASSWORD': secret['student_admin_password'], 'SPRING_PROFILES_ACTIVE': ''}
    start('student', ['java', '-jar', str(ROOT/'student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar')], ROOT/'student-web/backend', environment)
    start('frontend', ['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(ports['frontend']), '--strictPort'], ROOT/'student-web/frontend', os.environ.copy())
    security = ROOT/'security-web/target/debug/pbl4-security-demo'
    if 'security_admin_hash' not in secret:
        hashed = subprocess.run([str(security), '--hash-password'], input=secret['security_admin_password'], text=True,
                                capture_output=True, check=True).stdout.strip()
        secret['security_admin_hash'] = hashed
        credentials.write_text(json.dumps(secret, indent=2) + '\n')
    security_environment = os.environ | {'DATABASE_URL': f'postgres://postgres:{secret["security_db_password"]}@127.0.0.1:{ports["security_db"]}/security_db',
        'APP_ADDR': f'127.0.0.1:{ports["security"]}', 'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD_HASH': secret['security_admin_hash'],
        'VIEWER_PASSWORD_HASH': '', 'STUDENT_AUDIT_LOG_PATH': str(audit), 'NGINX_ACCESS_PATH': str(access),
        'SURICATA_EVE_PATH': str(eve), 'COLLECT_ALL_EVENTS': 'true', 'ENFORCEMENT_MODE': 'OFF', 'AUTO_BLOCK': 'false',
        'PBL4_FIREWALL_CMD': '/bin/false'}
    start('security', [str(security)], ROOT/'security-web', security_environment)
    snippet = (ROOT/'security-web/nginx/pbl4-proxy.conf').read_text().replace('listen 0.0.0.0:80;', f'listen {edge_bind}:{ports["edge"]};')
    snippet = snippet.replace('127.0.0.1:8080', f'127.0.0.1:{ports["api"]}').replace('127.0.0.1:5173', f'127.0.0.1:{ports["frontend"]}')
    snippet = snippet.replace('/var/log/nginx/access.log', str(access))
    temp_paths = '\n'.join(f'{kind}_temp_path {RUNTIME/"nginx"/kind};' for kind in ['client_body','proxy','fastcgi','uwsgi','scgi'])
    config = RUNTIME/'nginx/nginx.conf'
    config.write_text(f'error_log /dev/null crit; pid {RUNTIME/"nginx/nginx.pid"};\nevents {{}}\nhttp {{\n{temp_paths}\n{snippet}\n}}\n')
    nginx_command = [nginx, '-p', str(RUNTIME/'nginx'), '-e', str(RUNTIME/'nginx/bootstrap.log'), '-c', str(config)]
    run(nginx_command + ['-t'], capture=True)
    start('nginx', nginx_command + ['-g', 'daemon off; master_process off;'], ROOT, os.environ.copy())
    wait_http(f'http://127.0.0.1:{ports["security"]}/health')
    wait_http(f'http://127.0.0.1:{ports["edge"]}/')
    wait_http(f'http://127.0.0.1:{ports["api"]}/api/auth/csrf')
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    with opener.open(f'http://127.0.0.1:{ports["edge"]}/api/auth/csrf', timeout=5) as response:
        request_id = response.headers['X-Request-Id']
        csrf = json.load(response)
        assert response.status == 200
    form = urllib.parse.urlencode({'username':'foundation-admin','password':secret['student_admin_password']}).encode()
    login = urllib.request.Request(f'http://127.0.0.1:{ports["edge"]}/api/auth/login', data=form,
        headers={'Content-Type':'application/x-www-form-urlencoded',csrf['headerName']:csrf['token']})
    with opener.open(login,timeout=5) as response:
        assert response.status == 204
    with opener.open(f'http://127.0.0.1:{ports["edge"]}/api/auth/me',timeout=5) as response:
        assert json.load(response)['role']=='ADMIN'
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        observations = sql('idps-foundation-security','security_db', f"SELECT count(DISTINCT source) FROM normalized_events WHERE request_id='{request_id}' AND source IN ('NGINX','STUDENT_AUDIT')")
        if observations == '2':
            break
        time.sleep(.5)
    else:
        raise RuntimeError('both correlated source observations did not reach normalized_events')
    # Verify actual socket binding, rather than only inspecting YAML.
    sockets = run(['ss','-lntH'],capture=True).stdout.splitlines()
    listeners = [line.split()[3] for line in sockets if line.split()[3].endswith(':'+str(ports['api']))]
    def is_loopback_listener(value):
        host = value.rsplit(':',1)[0].strip('[]')
        try:
            address = ipaddress.ip_address(host)
            return address.is_loopback or (address.version==6 and address.ipv4_mapped is not None and address.ipv4_mapped.is_loopback)
        except ValueError:
            return False
    assert listeners and all(is_loopback_listener(value) for value in listeners), listeners
    events = [json.loads(line) for line in audit.read_text().splitlines()]
    assert events and all(e['schema_version']=='1.0' and e['timestamp'].endswith('Z') for e in events)
    report = {'status':'PASS','ports':ports,'request_id':request_id,'correlated_sources':2,
              'student_audit_lines':len(events),'enforcement':'OFF','suricata':'fixture source only; no live capture launched',
              'edge':f'http://127.0.0.1:{ports["edge"]}', 'edge_bind':edge_bind, 'security':f'http://127.0.0.1:{ports["security"]}',
              'student_username':'foundation-admin','security_username':'admin','credentials_file':str(credentials),'runtime':str(RUNTIME)}
    (RUNTIME/'smoke-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        print(f'FAILED: {type(error).__name__}: {error}. Existing work/services were not reset.', flush=True)
        raise SystemExit(1)

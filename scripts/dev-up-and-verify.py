#!/usr/bin/env python3
"""Isolated local foundation stack. Never installs services or changes host firewall.

Default ports differ from existing Compose instances; volumes survive --stop.
All generated credentials and logs live in an ignored, private runtime directory.
"""
import argparse
import fcntl
import hashlib
import http.cookiejar
import ipaddress
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time
from datetime import datetime
import urllib.error
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('IDPS_DEMO_RUNTIME', ROOT / '.local-dev/foundation')).resolve()
CONTAINER_PREFIX = os.environ.get('IDPS_DEMO_CONTAINER_PREFIX', 'idps-foundation')
STATE = RUNTIME / 'processes.json'


def container_name(name):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,60}', CONTAINER_PREFIX):
        raise RuntimeError('Invalid local container prefix')
    return CONTAINER_PREFIX + '-' + name


def run(command, *, cwd=ROOT, env=None, capture=False):
    return subprocess.run(command, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def sql(container, database, statement):
    return run(['docker', 'exec', container, 'psql', '-U', 'postgres', '-d', database,
                '-At', '-v', 'ON_ERROR_STOP=1', '-c', statement], capture=True).stdout.strip()


def process_token(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return None


def owned_alive(item):
    token = item.get('start_token') if item else None
    return token is not None and process_token(item['pid']) == token


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def start(name, command, cwd, environment):
    state = load_state()
    old = state.get(name, {})
    if owned_alive(old):
        print(f'{name}: already running ({old["pid"]})', flush=True)
        return False
    unit = None
    if os.environ.get('DEV_LIMIT_SERVICES') == 'true' and name != 'ai':
        unit = 'idps-demo-'+name+'-'+secrets.token_hex(6)+'.scope'
        command = ['systemd-run','--user','--scope','--quiet','--unit',unit,'-p','CPUQuota=10%',
                   '-p','CPUQuotaPeriodSec=10ms','-p','MemoryMax=1G','-p','MemorySwapMax=0',*command]
    with (RUNTIME / f'{name}.log').open('ab') as output:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=output, start_new_session=True)
    state[name] = {'pid': process.pid, 'start_token': process_token(process.pid)}
    if unit:
        state[name]['unit'] = unit
    STATE.write_text(json.dumps(state, indent=2) + '\n')
    print(f'{name}: started ({process.pid})', flush=True)
    return True


def stop():
    state = load_state()
    for name in ['nginx','ai','frontend','security','student']:
        if name == 'ai':
            stop_ai()
        elif name in state:
            stop_process(name,state[name])
    for name in [container_name('student'), container_name('security')]:
        owned = subprocess.run(['docker','inspect','--format','{{index .Config.Labels "idps.foundation"}}',name],capture_output=True,text=True)
        if owned.returncode == 0:
            if owned.stdout.strip() != 'true':
                raise RuntimeError('Refusing to stop unrelated container: '+name)
            run(['docker','stop',name],capture=True)
    if STATE.exists():
        STATE.unlink()
    print('Stopped only foundation processes/containers; volumes and credentials retained.')


def stop_process(name,item):
    # PID start token protects against recycled PIDs; scope covers descendants
    # even when a service forks or uses start_new_session.
    if owned_alive(item):
        os.killpg(item['pid'],signal.SIGTERM)
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and owned_alive(item):
        time.sleep(.1)
    unit=item.get('unit')
    if unit:
        subprocess.run(['systemctl','--user','stop',unit],capture_output=True,timeout=25,check=False)
    if owned_alive(item):
        raise RuntimeError('Owned process did not stop cleanly: '+name)
    print(name+': stopped')


def free_port(port, address="127.0.0.1"):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((address, port))


def wait_http(url, expected=(200,), timeout=600):
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
        owned=run(['docker','inspect','--format','{{index .Config.Labels "idps.foundation"}}',name],capture=True)
        if owned.stdout.strip() != 'true':
            raise RuntimeError('Refusing to reuse unrelated container: '+name)
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


def wait_bootstrap_admin(timeout=120):
    # Tomcat accepts requests before CommandLineRunner commits the bootstrap
    # account. A successful public CSRF response alone is not auth readiness.
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        ready=sql(container_name('student'),'student_db',
                  "SELECT count(*) FROM users WHERE username='foundation-admin' AND role='ADMIN'")
        if ready == '1':
            return
        time.sleep(.5)
    raise RuntimeError('Student HTTP is up but local bootstrap admin is not ready; inspect private startup logs')


def start_ai():
    (RUNTIME/'ai').mkdir(mode=0o700, exist_ok=True)
    socket_path = RUNTIME/'ai/nginx.sock'
    if len(str(socket_path).encode()) >= 104 or any(c in str(socket_path) for c in ' \t\n\r;{},'):
        raise RuntimeError('Use a shorter checkout path without Nginx directive separators for the local Unix socket')
    bundle = ROOT/'ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle'
    if not (bundle/'manifest.json').exists():
        run([str(ROOT/'scripts/bootstrap-team.sh')])
    python = ROOT/'ai-training/.venv/bin/python'
    resources = RUNTIME/'ai'/('resources-'+str(time.time_ns()))
    began=time.time()
    spawned=start('ai', [str(python),str(ROOT/'ai-training/scripts/integration-guard.py'),
        '--output',str(resources),'--quota','10','--max-seconds','7200','--',
        str(python),str(ROOT/'scripts/ai-shadow-worker.py'),
        '--socket',str(socket_path),'--output',str(RUNTIME/'ai/results.jsonl')], ROOT, os.environ.copy())
    # A spawned supervisor PID is not proof that a model is ready.
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        item = load_state().get('ai', {})
        if not owned_alive(item):
            raise RuntimeError('AI supervisor exited; inspect private ai.log and resource reports')
        journal = RUNTIME/'ai/results.jsonl'
        if journal.exists():
            with journal.open('rb') as incoming:
                incoming.seek(max(0,journal.stat().st_size-8192))
                for line in reversed(incoming.read().splitlines()):
                    try:
                        record = json.loads(line)
                        stamp=datetime.fromisoformat(record['observed_at']).timestamp()
                        fresh = 0 <= time.time()-stamp < 5 and (not spawned or stamp >= began)
                    except (ValueError,KeyError,TypeError):
                        continue
                    if fresh and record['status'] in {'READY','SCORED'}:
                        delivery_probe(record['worker_id'])
                        state=load_state()
                        state['ai']['worker_id']=record['worker_id']
                        STATE.write_text(json.dumps(state,indent=2)+'\n')
                        return
                    if fresh and record['status'] in {'MODEL_UNAVAILABLE','THERMAL_STOP','RAM_STOP','THERMAL_CONTROL_NOT_VERIFIED'}:
                        raise RuntimeError('AI cannot start safely: '+record['status'])
                    break
        time.sleep(.2)
    raise RuntimeError('AI readiness timeout; no fresh model-ready heartbeat')


def recent_ai_records():
    journal=RUNTIME/'ai/results.jsonl'
    if not journal.exists():
        return []
    with journal.open('rb') as incoming:
        incoming.seek(max(0,journal.stat().st_size-65536))
        lines=incoming.read().splitlines()
    records=[]
    for line in lines:
        try:
            records.append(json.loads(line))
        except (ValueError,UnicodeError):
            continue
    return records


def delivery_probe(worker_id):
    """Warm/reconnect stale Nginx syslog peer using bounded real HTTP probes.

    This verifies delivery at startup only; it cannot make a datagram transport
    lossless. Probe IDs/loss are recorded as metadata and included in Nginx audit.
    """
    configuration=json.loads((RUNTIME/'configuration.json').read_text())
    port=configuration['ports']['edge']
    probes=[]
    for _ in range(3):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/auth/csrf?ai_delivery_probe=1',timeout=30) as response:
            rid=response.headers['X-Request-Id']
            response.read(16384)
        if not re.fullmatch('[a-f0-9]{32}',rid):
            raise RuntimeError('Nginx did not supply a valid request ID')
        probes.append(rid)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            records=recent_ai_records()
            found=next((r for r in reversed(records) if r.get('worker_id')==worker_id and r.get('request_id')==rid),None)
            if found and found['status']=='SCORED':
                scored={r.get('request_id') for r in records if r.get('worker_id')==worker_id and r.get('status')=='SCORED'}
                report={'status':'PASS','worker_id':worker_id,'verified_at':datetime.now().astimezone().isoformat(),
                        'probe_ids':probes,'probe_count':len(probes),'unscored_probe_ids':[p for p in probes if p not in scored],
                        'transport':'LOSSY_UNIX_DATAGRAM','scope':'Startup delivery check; not a lossless guarantee'}
                (RUNTIME/'ai/connection-check.json').write_text(json.dumps(report,indent=2)+'\n')
                return report
            time.sleep(.2)
    (RUNTIME/'ai/connection-check.json').write_text(json.dumps({'status':'FAIL','worker_id':worker_id,'probe_ids':probes,'transport':'LOSSY_UNIX_DATAGRAM'},indent=2)+'\n')
    raise RuntimeError('AI model is loaded but Nginx delivery has not recovered; check thermal/socket status')


def host_preflight(seconds=5):
    """Read-only, no system power/thermal configuration changes."""
    temperatures=[]
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        sensors=[]
        for directory in Path('/sys/class/hwmon').glob('hwmon*'):
            if (directory/'name').read_text().strip() in {'coretemp','k10temp','zenpower'}:
                sensors.extend(float(p.read_text())/1000 for p in directory.glob('temp*_input'))
        if not sensors or any(not 0 < v < 130 for v in sensors):
            raise RuntimeError('THERMAL_CONTROL_NOT_VERIFIED')
        temperatures.append(max(sensors))
        time.sleep(.2)
    memory={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    used=memory['MemTotal']-memory['MemAvailable']
    report={'CPU_C_max':max(temperatures),'CPU_C_last':temperatures[-1],'samples':len(temperatures),'system_used_bytes':used,
            'safe_to_build':max(temperatures)<65 and used<28_000_000_000,'scope':'Five-second sampled preflight; later external heat can still stop workload'}
    (RUNTIME/('preflight-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    if not report['safe_to_build']:
        raise RuntimeError('Host not thermally stable below65C or RAM headroom insufficient; wait, do not build')
    return report


def stop_ai():
    state = load_state()
    old = state.get('ai', {})
    if owned_alive(old):
        os.killpg(old['pid'], signal.SIGTERM)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and owned_alive(old):
            time.sleep(.2)
        if owned_alive(old):
            raise RuntimeError('AI supervisor did not stop; inspect watchdog, do not start another worker')
    state.pop('ai', None)
    STATE.write_text(json.dumps(state, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--status',action='store_true',help='read-only owned process/AI readiness summary')
    parser.add_argument('--expose-lan', action='store_true', help='bind only the dev edge to 0.0.0.0; API/frontend remain loopback')
    parser.add_argument('--bootstrap-nginx', action='store_true', help='extract Ubuntu nginx .deb locally without sudo/installing a system service')
    parser.add_argument('--skip-build', action='store_true', help='use already built Java/Rust/frontend dependencies')
    parser.add_argument('--ai-shadow', action='store_true', help='opt-in local transient Nginx telemetry and isolated frozen RIv2 worker; no enforcement')
    parser.add_argument('--ai-worker', choices=['start','stop'], help='operate only the AI worker after an --ai-shadow demo has been set up')
    args = parser.parse_args()
    if args.ai_shadow:
        os.environ['DEV_LIMIT_SERVICES'] = 'true'
    os.umask(0o077)
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock=(RUNTIME/'launcher.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError('Another demo launcher is already changing this runtime') from error
    if args.status:
        records=recent_ai_records()
        heartbeat=next((r for r in reversed(records) if r.get('kind')=='heartbeat'),None)
        print(json.dumps({'processes':{name:{'alive':owned_alive(item),'pid':item['pid']} for name,item in load_state().items()},
                          'AI':None if heartbeat is None else {'status':heartbeat['status'],'observed_at':heartbeat['observed_at'],
                          'fresh':0<=time.time()-datetime.fromisoformat(heartbeat['observed_at']).timestamp()<10},
                          'runtime':str(RUNTIME)},indent=2))
        return
    if args.ai_worker:
        config = RUNTIME/'configuration.json'
        if not config.exists() or not json.loads(config.read_text()).get('ai_shadow'):
            raise RuntimeError('First start the local demo with --ai-shadow')
        if args.ai_worker == 'start':
            start_ai()
        else:
            stop_ai()
        return
    if args.stop:
        stop()
        return
    nginx = os.environ.get('NGINX_BIN') or shutil.which('nginx')
    extracted_nginx = RUNTIME/'tools/runtime/usr/sbin/nginx'
    if not nginx and args.bootstrap_nginx and extracted_nginx.is_file():
        nginx = str(extracted_nginx)
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
    if args.ai_shadow:
        desired['ai_shadow'] = True
    if configuration.exists() and json.loads(configuration.read_text()) != desired:
        if any(owned_alive(v) for v in load_state().values()):
            raise RuntimeError('running foundation configuration differs; run --stop before changing ports/exposure')
    configuration.write_text(json.dumps(desired,indent=2)+'\n')
    for name in ['student_db', 'security_db']:
        postgres(container_name(name.replace('_db', '')), 'postgres:16-alpine' if name == 'student_db' else 'postgres:17-alpine',
                 ports[name], 'student_db' if name == 'student_db' else 'security_db', secret[name + '_password'])
    if not args.skip_build:
        print('Building existing Java/Rust stack and preparing frontend...', flush=True)
        with (RUNTIME/'build.log').open('w') as output:
            commands = [(['./mvnw', '-q', 'package', '-DskipTests'], ROOT/'student-web/backend'),
                        (['cargo', 'build', '--locked', '-j', '1' if args.ai_shadow else '2'], ROOT/'security-web'),
                        (['npm', 'ci'], ROOT/'security-web/frontend'),
                        (['npm', 'run', 'build'], ROOT/'security-web/frontend'),
                        (['npm', 'ci'], ROOT/'student-web/frontend'),
                        (['npm', 'run', 'build'], ROOT/'student-web/frontend')]
            for command, directory in commands:
                if args.ai_shadow:
                    host_preflight()
                    guard_python = ROOT/'ai-training/.venv/bin/python'
                    if not guard_python.is_file():
                        raise RuntimeError('First run scripts/bootstrap-team.sh for the pinned AI environment')
                    resources = RUNTIME/('build-resources-'+str(time.time_ns()))
                    # Forward only toolchain paths, never application credentials.
                    environment = ['PATH='+os.environ.get('PATH','/usr/bin:/bin'),
                                   'MAVEN_OPTS=-Xmx512m -XX:ActiveProcessorCount=1']
                    if os.environ.get('JAVA_HOME'):
                        environment.append('JAVA_HOME='+os.environ['JAVA_HOME'])
                    command = [str(guard_python),str(ROOT/'ai-training/scripts/integration-guard.py'),
                               '--output',str(resources),'--quota','10','--max-seconds','1800','--build-pause','--',
                               '/usr/bin/env',*environment,*command]
                subprocess.run(command,cwd=directory,stdout=output,stderr=output,check=True)
    for name in ['student-audit', 'nginx', 'suricata']:
        (RUNTIME/name).mkdir(exist_ok=True, mode=0o700)
    audit = RUNTIME/'student-audit/student-audit.log'
    access = RUNTIME/'nginx/access.log'
    eve = RUNTIME/'suricata/eve.json'
    for path in [audit, access, eve]:
        path.touch(mode=0o600, exist_ok=True)
    ai_results = RUNTIME/'ai/results.jsonl'
    ai_socket = RUNTIME/'ai/nginx.sock'
    if args.ai_shadow:
        (RUNTIME/'ai').mkdir(mode=0o700, exist_ok=True)
        ai_results.touch(mode=0o600, exist_ok=True)
    # Only the designated private dev processes are reused. An unrelated listener causes failure.
    state = load_state()
    for name, port in [('student', ports['api']), ('frontend', ports['frontend']), ('security', ports['security']), ('nginx', ports['edge'])]:
        item = state.get(name, {})
        if not owned_alive(item):
            free_port(port, edge_bind if name == "nginx" else "127.0.0.1")
    environment = os.environ | {'DB_URL': f'jdbc:postgresql://127.0.0.1:{ports["student_db"]}/student_db',
        'DB_USERNAME': 'postgres', 'DB_PASSWORD': secret['student_db_password'], 'STUDENT_BIND_ADDRESS': '127.0.0.1',
        'SERVER_PORT': str(ports['api']), 'STUDENT_AUDIT_LOG_ENABLED': 'true', 'STUDENT_AUDIT_LOG_PATH': str(audit),
        'STUDENT_AUDIT_HMAC_KEY': secret['hmac_key'], 'AUDIT_INCLUDE_SUCCESSFUL_READS': 'true',
        'TRUSTED_PROXIES': '127.0.0.1/32,::1/128', 'BOOTSTRAP_ADMIN_ENABLED': 'true',
        'BOOTSTRAP_ADMIN_USERNAME': 'foundation-admin', 'BOOTSTRAP_ADMIN_PASSWORD': secret['student_admin_password'], 'SPRING_PROFILES_ACTIVE': ''}
    java_limits = ['-XX:ActiveProcessorCount=1','-Xmx768m'] if args.ai_shadow else []
    start('student', ['java', *java_limits, '-jar', str(ROOT/'student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar')], ROOT/'student-web/backend', environment)
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
    if args.ai_shadow:
        security_environment['AI_SHADOW_RESULTS_PATH'] = str(ai_results)
        (RUNTIME/'correlation').mkdir(mode=0o700,exist_ok=True)
        (RUNTIME/'correlation/results.jsonl').touch(mode=0o600,exist_ok=True)
        security_environment['THREE_SOURCE_RESULTS_PATH'] = str(RUNTIME/'correlation/results.jsonl')
        (RUNTIME/'glu207').mkdir(mode=0o700,exist_ok=True)
        (RUNTIME/'glu207/results.jsonl').touch(mode=0o600,exist_ok=True)
        security_environment['GLU207_RESULTS_PATH'] = str(RUNTIME/'glu207/results.jsonl')
    else:
        security_environment.pop('AI_SHADOW_RESULTS_PATH', None)
    start('security', [str(security)], ROOT/'security-web', security_environment)
    snippet = (ROOT/'security-web/nginx/pbl4-proxy.conf').read_text().replace('listen 0.0.0.0:80;', f'listen {edge_bind}:{ports["edge"]};')
    snippet = snippet.replace('127.0.0.1:8080', f'127.0.0.1:{ports["api"]}').replace('127.0.0.1:5173', f'127.0.0.1:{ports["frontend"]}')
    snippet = snippet.replace('/var/log/nginx/access.log', str(access))
    if args.ai_shadow:
        snippet = ai_shadow_nginx(snippet, ai_socket)
        # The opt-in local AI demo must not fall back to a different Web VM.
        snippet = snippet.replace('    server 192.168.20.10:80 backup;\n', '')
    temp_paths = '\n'.join(f'{kind}_temp_path {RUNTIME/"nginx"/kind};' for kind in ['client_body','proxy','fastcgi','uwsgi','scgi'])
    config = RUNTIME/'nginx/nginx.conf'
    config.write_text(f'error_log /dev/null crit; pid {RUNTIME/"nginx/nginx.pid"};\nevents {{}}\nhttp {{\n{temp_paths}\n{snippet}\n}}\n')
    nginx_command = [nginx, '-p', str(RUNTIME/'nginx'), '-e', str(RUNTIME/'nginx/bootstrap.log'), '-c', str(config)]
    run(nginx_command + ['-t'], capture=True)
    start('nginx', nginx_command + ['-g', 'daemon off; master_process off;'], ROOT, os.environ.copy())
    wait_http(f'http://127.0.0.1:{ports["security"]}/health')
    wait_http(f'http://127.0.0.1:{ports["edge"]}/')
    wait_http(f'http://127.0.0.1:{ports["api"]}/api/auth/csrf')
    wait_bootstrap_admin()
    ai_startup = 'DISABLED'
    if args.ai_shadow:
        try:
            start_ai()
            ai_startup = 'READY'
        except (OSError, RuntimeError, subprocess.SubprocessError):
            # Optional AI failure must not keep the application stack offline.
            ai_startup = 'NOT_READY; inspect private ai.log/resource reports'
            print('AI is not ready; Student/Nginx/Security stay available. Check thermal/model status.',flush=True)
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    with opener.open(f'http://127.0.0.1:{ports["edge"]}/api/auth/csrf', timeout=30) as response:
        request_id = response.headers['X-Request-Id']
        csrf = json.load(response)
        assert response.status == 200
    form = urllib.parse.urlencode({'username':'foundation-admin','password':secret['student_admin_password']}).encode()
    login = urllib.request.Request(f'http://127.0.0.1:{ports["edge"]}/api/auth/login', data=form,
        headers={'Content-Type':'application/x-www-form-urlencoded',csrf['headerName']:csrf['token']})
    with opener.open(login,timeout=30) as response:
        assert response.status == 204
    with opener.open(f'http://127.0.0.1:{ports["edge"]}/api/auth/me',timeout=30) as response:
        assert json.load(response)['role']=='ADMIN'
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        observations = sql(container_name('security'),'security_db', f"SELECT count(DISTINCT source) FROM normalized_events WHERE request_id='{request_id}' AND source IN ('NGINX','STUDENT_AUDIT')")
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
    report = {'status':'PASS','scope':'FOUNDATION_HTTP_AUTH_AND_AUDIT; AI requires separate acceptance','ai_shadow_startup':ai_startup,'ports':ports,'request_id':request_id,'correlated_sources':2,
              'student_audit_lines':len(events),'enforcement':'OFF','suricata':'fixture source only; no live capture launched',
              'edge':f'http://127.0.0.1:{ports["edge"]}', 'edge_bind':edge_bind, 'security':f'http://127.0.0.1:{ports["security"]}',
              'student_username':'foundation-admin','security_username':'admin','credentials_file':str(credentials),'runtime':str(RUNTIME)}
    (RUNTIME/'smoke-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


def ai_shadow_nginx(snippet, socket_path):
    """Local-only second access sink. Never writes raw HTTP to an access file.

    Nginx syslog uses nonblocking Unix datagrams; no receiver/overload drops
    telemetry, never proxies requests to an AI service. Body remains unavailable.
    """
    log_format = '''log_format ai_shadow_json escape=json
    '{"schema_version":"nginx-ai-1","request_id":"$request_id",'
    '"timestamp":"$time_iso8601","method":"$request_method","url":"$request_uri",'
    '"headers":{"User-Agent":"$http_user_agent","Accept":"$http_accept","Content-Type":"$http_content_type"}}';
'''
    # Only observe /api/ application traffic, including normal/rule-negative HTTP.
    sink = f'access_log syslog:server=unix:{socket_path},tag=ai_shadow,nohostname ai_shadow_json;'
    return log_format + snippet.replace('location /api/ {', 'location /api/ {\n        '+sink+'\n        access_log '+str(RUNTIME/'nginx/access.log')+' idps_json;')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, AssertionError, subprocess.SubprocessError) as error:
        print(f'FAILED: {type(error).__name__}: {error}. Existing work/services were not reset.', flush=True)
        raise SystemExit(1)

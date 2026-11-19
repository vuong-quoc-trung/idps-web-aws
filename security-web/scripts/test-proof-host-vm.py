#!/usr/bin/env python3
"""DESTRUCTIVE DISPOSABLE-VM acceptance. Never run on Security Host.
Requires real VM, PID1 systemd, disconnected non-loopback NICs, explicit IDs/ack.
Uses the real installer, supervisor, systemd, nginx/njs, Suricata and nftables.
Cleanup is VM snapshot reversion; evidence is retained until exported.
"""
import argparse
import hashlib
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
WORK = Path('/root/ws-proof-vm-test')
KEY = Path('/etc/nginx/pbl4-proof/key.json')
STATE = Path('/var/lib/websentinel-egress')
CASES = ('identity', 'apply', 'key_permissions', 'module_permissions', 'ai_socket',
         'log_cache_site_permissions', 'restart_rotation', 'reload_refused',
         'master_crash', 'supervisor_crash', 'guard_deleted', 'key_missing',
         'bad_config', 'rollback', 'nginx_start_failure', 'suricata_start_failure')


def cmd(argv, check=True):
    return subprocess.run([str(v) for v in argv], check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)


def validate_isolation(machine, production, actual, vm, pid1, links, cgroup):
    if not re.fullmatch('[a-f0-9]{32}', machine) or not re.fullmatch('[a-f0-9]{32}', production):
        raise ValueError('Two explicit valid machine IDs required')
    if machine == production or actual != machine:
        raise ValueError('Machine ID mismatch or production machine')
    if not vm:
        raise ValueError('Full disposable VM required, not a namespace/container')
    if pid1 != 'systemd':
        raise ValueError('VM must have its own PID1 systemd')
    if any(v['ifname'] != 'lo' and 'UP' in v.get('flags', []) for v in links):
        raise ValueError('Disconnect/down ALL non-loopback NICs from VM console first')
    if not cgroup:
        raise ValueError('cgroup v2 required')


def isolation(machine, production, detector=cmd):
    validate_isolation(machine, production, Path('/etc/machine-id').read_text().strip(),
        detector(['systemd-detect-virt', '--vm'], check=False).returncode == 0,
        Path('/proc/1/comm').read_text().strip(),
        json.loads(detector(['ip', '-j', 'link']).stdout),
        Path('/sys/fs/cgroup/cgroup.controllers').exists())


def summary(results):
    return {'result': 'PASS' if set(CASES).issubset(results) and
            all(v['status'] == 'PASS' for v in results.values()) else 'FAIL',
        'cases': results, 'scope': 'disposable VM only', 'production_acceptance': 'NOT_RUN',
        'production_sites': 'NOT_RUN; fixture sites only', 'verified': False,
        'cleanup': 'Export report, then revert/delete entire VM snapshot'}


def wait(predicate, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.2)
    raise AssertionError('Condition did not become true before deadline')


def active():
    return cmd(['systemctl', 'is-active', 'nginx'], check=False).stdout.strip() == 'active'


def closed():
    # No listener + no readiness, rather than relying on systemd's Type=simple state.
    listeners = cmd(['ss', '-Hlnpt', 'sport = :18080']).stdout
    return not listeners.strip() and not (STATE/'status.json').exists()


def ready():
    try:
        value = json.loads((STATE/'status.json').read_text())
        return active() and 0 <= time.time()-value['checked_at'] < 3 and value['guard_snapshot']
    except (OSError, ValueError):
        return False


def fingerprint():
    value = json.loads(KEY.read_text())
    return value['epoch'], hashlib.sha256(value['key'].encode()).hexdigest()


def user_probe(user, code, *args):
    # Output never includes key contents.
    return cmd(['runuser', '-u', user, '--', sys.executable, '-c', code, *args], check=False)


def write(path, text, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def seal(bundle):
    value = json.loads((bundle/'manifest.json').read_text())
    for name in value['sha256']:
        value['sha256'][name] = hashlib.sha256((bundle/name).read_bytes()).hexdigest()
    write(bundle/'manifest.json', json.dumps(value), 0o600)


class Lab:
    def __init__(self, module):
        self.module = module
        self.bundle = WORK/'bundle'
        self.backup = WORK/'backup'
        self.telemetry = []
        self.leaks = []
        self.http = None
        self.mutated = False
        self.sock = None

    def deploy(self, action, bundle=None, backup=None, check=True):
        argv = [sys.executable, HERE/'deploy-proof-host.py', action,
                '--bundle', bundle or self.bundle, '--backup', backup or self.backup]
        if action in ('apply', 'rollback'):
            argv += ['--approve-host-change']
        return cmd(argv, check=check)

    def request(self, port=443, path='/', body=None):
        context = ssl.create_default_context(cafile=str(WORK/'cert.crt'))
        c = (http.client.HTTPSConnection('192.168.10.1', port, context=context, timeout=5)
             if port == 443 else http.client.HTTPConnection('127.0.0.1', port, timeout=5))
        c.request('POST' if body else 'GET', path, body=body)
        r = c.getresponse()
        data = r.read()
        result = r.status, r.getheader('X-Request-Id'), data
        assert r.getheader('X-WS-Proof') is None and r.getheader('X-WS-Receipt') is None
        c.close()
        return result

    def prepare(self):
        for service in ('nginx', 'suricata'):
            dropins = Path('/etc/systemd/system')/(service+'.service.d')
            if dropins.exists() and any(dropins.iterdir()):
                raise RuntimeError('Fresh VM must not contain custom service drop-ins')
        if WORK.exists() or STATE.exists() or KEY.exists():
            raise RuntimeError('Fresh VM snapshot required; refuse existing deployment state')
        if cmd(['getent', 'passwd', 'websentinel-edge'], check=False).returncode == 0:
            raise RuntimeError('Dedicated test account already exists; revert clean snapshot')
        if 'pbl4_local_egress' in cmd(['nft', 'list', 'tables']).stdout:
            raise RuntimeError('Reserved guard table exists')
        WORK.mkdir(mode=0o700)
        self.mutated = True
        cmd(['systemctl', 'stop', 'nginx', 'suricata'])
        cmd(['groupadd', '--system', 'websentinel-edge'])
        cmd(['useradd', '--system', '--gid', 'websentinel-edge', '--no-create-home',
             '--shell', '/usr/sbin/nologin', 'websentinel-edge'])
        self.account = pwd.getpwnam('websentinel-edge')
        # These addresses exist ONLY on this disconnected VM's loopback.
        for address in ('192.168.10.1/32', '192.168.20.10/32'):
            cmd(['ip', 'addr', 'add', address, 'dev', 'lo'])
        cmd(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-days', '2',
             '-subj', '/CN=student.lab', '-addext',
             'subjectAltName=DNS:student.lab,IP:192.168.10.1,IP:192.168.20.10',
             '-keyout', WORK/'cert.key', '-out', WORK/'cert.crt'])
        (WORK/'cert.key').chmod(0o600)
        for directory in ('/var/log/nginx', '/var/log/suricata', '/run/suricata'):
            Path(directory).mkdir(parents=True, exist_ok=True)
        # Production script paths and service names, but ONLY inside disposable VM.
        write('/etc/nginx/nginx.conf', '''user www-data;
worker_processes 2;
pid /run/nginx.pid;
error_log /var/log/nginx/error.log;
events { worker_connections 256; }
http {
 include /etc/nginx/mime.types;
 include /etc/nginx/conf.d/pbl4-ai-shadow.conf;
 include /etc/nginx/sites-available/pbl4-proxy;
 include /etc/nginx/ws-vm-sites.conf;
}
''')
        write('/etc/nginx/conf.d/pbl4-ai-shadow.conf', '')
        write('/etc/nginx/sites-available/pbl4-proxy', '''server {
 listen 192.168.10.1:80;
 location / { return 200 "baseline"; }
}
''')
        write('/etc/nginx/ws-vm-sites.conf', '')
        write('/etc/systemd/system/nginx.service', '''[Unit]
Description=Disposable VM baseline NGINX
[Service]
Type=forking
PIDFile=/run/nginx.pid
ExecStart=/usr/sbin/nginx
ExecReload=/usr/sbin/nginx -s reload
ExecStop=/usr/sbin/nginx -s quit
''')
        # Use repository rules and installed Suricata configuration; no real sensor logs.
        import yaml
        config = yaml.safe_load(Path('/etc/suricata/suricata.yaml').read_text())
        config['rule-files'] = [str(HERE.parent/'suricata/pbl4.rules')]
        config.pop('run-as', None)
        config['af-packet'] = [{'interface': 'lo'}]
        config['unix-command'] = {'enabled': False}
        config['outputs'] = [{'eve-log': {'enabled': True, 'filetype': 'regular',
            'filename': 'eve.json', 'types': [{'http': {}}, {'alert': {}}]}}]
        write(WORK/'base.yaml', '%YAML 1.1\n---\n'+yaml.safe_dump(config))
        write('/etc/systemd/system/suricata.service', f'''[Unit]
Description=Disposable VM baseline sensor
[Service]
Type=forking
PIDFile=/run/suricata/suricata.pid
ExecStart=/usr/bin/suricata -D --af-packet -c {WORK}/base.yaml --pidfile /run/suricata/suricata.pid
''')
        cmd(['systemctl', 'daemon-reload'])
        cmd(['systemctl', 'start', 'nginx', 'suricata'])
        self.start_mocks()
        cmd([sys.executable, HERE/'stage-proof-host.py', '--output', self.bundle,
             '--suricata-base', WORK/'base.yaml', '--student-ca', WORK/'cert.crt',
             '--edge-ca', WORK/'cert.crt', '--edge-cert', WORK/'cert.crt',
             '--edge-key', WORK/'cert.key', '--module', self.module,
             '--gid', str(self.account.pw_gid)])

    def start_mocks(self):
        lab = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if self.headers.get('X-WS-Proof') or self.headers.get('X-WS-Receipt'):
                    lab.leaks.append(True)
                status = 401 if self.path == '/api/auth/me' else 200
                self.send_response(status)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.do_GET()
        self.http = http.server.ThreadingHTTPServer(('192.168.20.10', 443), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(WORK/'cert.crt', WORK/'cert.key')
        self.http.socket = context.wrap_socket(self.http.socket, server_side=True)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        directory = Path('/run/pbl4-ai-shadow')
        directory.mkdir(mode=0o750)
        os.chown(directory, 0, self.account.pw_gid)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(directory/'nginx.sock'))
        os.chown(directory/'nginx.sock', 0, self.account.pw_gid)
        (directory/'nginx.sock').chmod(0o660)
        def receive():
            while True:
                try:
                    self.telemetry.append(self.sock.recv(65536).decode())
                except OSError:
                    return
        threading.Thread(target=receive, daemon=True).start()

    def restart(self):
        cmd(['systemctl', 'reset-failed', 'nginx'])
        cmd(['systemctl', 'start', 'nginx'])
        wait(ready)
        assert self.request()[0] == 200

    def recover_stale_guard(self):
        cmd(['systemctl', 'stop', 'nginx'])
        assert not cmd(['ss', '-Hlnpt', 'sport = :18080']).stdout.strip()
        # Deliberately named VM-only recovery, after kill of the whole service cgroup.
        cmd(['nft', 'delete', 'table', 'inet', 'pbl4_local_egress'])
        (STATE/'deny.json').unlink(missing_ok=True)
        self.restart()

    def stop(self):
        cmd(['systemctl', 'stop', 'nginx', 'suricata'], check=False)
        if self.http:
            self.http.shutdown()
            self.http.server_close()
        if self.sock:
            self.sock.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vm-machine-id', required=True)
    p.add_argument('--production-machine-id', required=True)
    p.add_argument('--module', type=Path, required=True)
    p.add_argument('--ack-disposable-vm-destruction', action='store_true')
    a = p.parse_args()
    if not a.ack_disposable_vm_destruction or os.geteuid() != 0:
        p.error('Root and explicit disposable-VM destruction acknowledgement required')
    isolation(a.vm_machine_id, a.production_machine_id)
    if not a.module.is_file(): p.error('Reviewed compatible module required')
    if sys.flags.optimize: p.error('Assertions must remain enabled')
    nginx_version = cmd(['/usr/sbin/nginx', '-v']).stderr.strip()
    suricata_version = cmd(['/usr/bin/suricata', '-V']).stdout.strip()
    if 'nginx/1.28.3' not in nginx_version or not re.search(r'\b8\.0\.3\b', suricata_version):
        p.error('Use the previously tested NGINX 1.28.3 and Suricata 8.0.3 in the test VM')
    results = {name: {'status': 'NOT_RUN'} for name in CASES}
    lab = Lab(a.module.resolve())
    current = 'identity'
    def passed(name):
        results[name] = {'status': 'PASS'}
        print(name + ': PASS', flush=True)
    try:
        lab.prepare()
        # Import the actual identity validation, without running its supervisor here.
        spec = importlib.util.spec_from_file_location('life', HERE/'proof-nginx-lifecycle.py')
        life = importlib.util.module_from_spec(spec); spec.loader.exec_module(life)
        assert life.identity('websentinel-edge').pw_uid == lab.account.pw_uid
        passed('identity')
        current = 'apply'
        lab.deploy('preflight'); lab.deploy('dry-run'); lab.deploy('apply')
        wait(ready); lab.deploy('health'); assert not lab.leaks
        passed(current)
        current = 'key_permissions'
        st = KEY.stat()
        assert st.st_uid == 0 and st.st_gid == lab.account.pw_gid and st.st_mode & 0o777 == 0o640
        probe = 'import sys; open(sys.argv[1], "rb").read(1)'
        assert user_probe('websentinel-edge', probe, str(KEY)).returncode == 0
        assert user_probe('nobody', probe, str(KEY)).returncode != 0
        assert user_probe('websentinel-edge', 'import sys; open(sys.argv[1],"ab")', str(KEY)).returncode != 0
        passed(current)
        current = 'module_permissions'
        assert user_probe('websentinel-edge', probe, str(lab.module)).returncode == 0
        assert lab.module.stat().st_uid == 0 and not (lab.module.stat().st_mode & 0o022)
        assert 'ngx_http_js_module' in cmd(['nginx', '-T']).stdout
        passed(current)
        current = 'ai_socket'
        _, rid, _ = lab.request()
        wait(lambda: sum(rid in line for line in lab.telemetry) == 1)
        assert sum(rid in line for line in lab.telemetry) == 1
        passed(current)
        current = 'log_cache_site_permissions'
        for name in ('/var/cache/nginx/ws-vm-body', '/var/lib/nginx/ws-vm-static'):
            Path(name).mkdir(parents=True, mode=0o750)
            os.chown(name, lab.account.pw_uid, lab.account.pw_gid)
        write('/var/lib/nginx/ws-vm-static/asset.txt', 'fixture-asset', 0o644)
        write('/etc/nginx/ws-vm-sites.conf', '''server {
 listen 127.0.0.1:18081;
 access_log /var/log/nginx/ws-vm-site.log;
 client_body_buffer_size 1k;
 client_body_temp_path /var/cache/nginx/ws-vm-body;
 location /static/ { alias /var/lib/nginx/ws-vm-static/; }
 location /upload {
  proxy_ssl_verify on;
  proxy_ssl_name student.lab;
  proxy_ssl_trusted_certificate /root/ws-proof-vm-test/cert.crt;
  proxy_pass https://192.168.20.10:443;
 }
}
''')
        cmd(['systemctl', 'restart', 'nginx']); wait(ready)
        assert lab.request(18081, '/static/asset.txt')[2] == b'fixture-asset'
        assert lab.request(18081, '/upload', b'x'*32768)[0] == 200
        assert 'POST /upload' in Path('/var/log/nginx/ws-vm-site.log').read_text()
        assert 'Permission denied' not in Path('/var/log/nginx/error.log').read_text()
        passed(current)
        current = 'restart_rotation'
        old = fingerprint(); cmd(['systemctl', 'restart', 'nginx']); wait(ready)
        assert all(x != y for x, y in zip(old, fingerprint()))
        assert lab.request()[0] == 200
        passed(current)
        current = 'reload_refused'
        old = fingerprint()
        assert cmd(['systemctl', 'reload', 'nginx'], check=False).returncode != 0
        assert ready() and old == fingerprint() and lab.request()[0] == 200
        passed(current)
        current = 'master_crash'
        old = fingerprint()
        os.kill(json.loads((STATE/'status.json').read_text())['pid'], signal.SIGKILL)
        wait(lambda: closed() and not KEY.exists())
        lab.restart(); assert all(x != y for x, y in zip(old, fingerprint()))
        passed(current)
        current = 'supervisor_crash'
        old = fingerprint()
        pid = int(cmd(['systemctl', 'show', 'nginx', '-p', 'MainPID', '--value']).stdout)
        os.kill(pid, signal.SIGKILL)
        wait(lambda: not cmd(['ss', '-Hlnpt', 'sport = :18080']).stdout.strip())
        # Stale heartbeat is not readiness; wait until TTL has expired.
        time.sleep(3.2)
        assert not ready()
        cmd(['systemctl', 'start', 'nginx'], check=False)
        wait(lambda: not active()); assert not ready()
        lab.recover_stale_guard(); assert all(x != y for x, y in zip(old, fingerprint()))
        passed(current)
        for name in ('guard_deleted', 'key_missing'):
            current = name
            if name == 'guard_deleted':
                cmd(['nft', 'delete', 'table', 'inet', 'pbl4_local_egress'])
            else:
                KEY.unlink()
            wait(lambda: closed() and not KEY.exists())
            table = cmd(['nft', 'list', 'table', 'inet', 'pbl4_local_egress']).stdout
            assert 'drop' in table and 'accept' not in table.split('chain egress')[1]
            lab.restart(); passed(current)
        current = 'bad_config'
        site = Path('/etc/nginx/sites-available/pbl4-proxy')
        original = site.read_text(); cmd(['systemctl', 'stop', 'nginx'])
        site.write_text(original+'\nINVALID_TEST_DIRECTIVE;\n')
        cmd(['systemctl', 'reset-failed', 'nginx'])
        cmd(['systemctl', 'start', 'nginx'], check=False)
        wait(lambda: not active()); wait(lambda: closed() and not KEY.exists())
        site.write_text(original); lab.restart(); passed(current)
        current = 'rollback'
        lab.deploy('rollback'); assert active()
        index = json.loads((lab.backup/'index.json').read_text())
        spec = importlib.util.spec_from_file_location('deploy', HERE/'deploy-proof-host.py')
        deploy = importlib.util.module_from_spec(spec); spec.loader.exec_module(deploy)
        for name, metadata in index['files'].items():
            path = Path(deploy.TARGETS[name])
            if metadata:
                assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata['sha256']
                st = path.stat()
                assert (st.st_uid, st.st_gid, st.st_mode & 0o777) == (metadata['uid'], metadata['gid'], metadata['mode'])
            else:
                assert not path.exists()
        passed(current)
        # Inject genuine service start failure, not a mocked command or syntax error.
        import shutil
        for service in ('nginx', 'suricata'):
            current = service+'_start_failure'
            bundle = WORK/('bundle-fail-'+service)
            shutil.copytree(lab.bundle, bundle)
            unit = bundle/(service+'.service.conf')
            unit.write_text(unit.read_text()+'\nExecStartPre=/usr/bin/false\n')
            seal(bundle)
            backup = WORK/('backup-fail-'+service)
            outcome = lab.deploy('apply', bundle, backup, check=False)
            assert outcome.returncode != 0 and 'original configuration restored' in outcome.stderr
            assert active() and cmd(['systemctl', 'is-active', 'suricata']).stdout.strip() == 'active'
            assert Path('/etc/nginx/sites-available/pbl4-proxy').read_text().find('baseline') != -1
            passed(current)
    except Exception as error:
        results[current] = {'status': 'FAIL', 'error_type': type(error).__name__}
        # No stderr/config dump: may contain sensitive data on a misprepared VM.
        print('FAILED: '+current+' ('+type(error).__name__+')', file=sys.stderr)
    finally:
        # On rejected preconditions do not stop any services; after mutation stop actors.
        if lab.mutated:
            try:
                lab.stop()
            except Exception:
                results['cleanup'] = {'status': 'FAIL'}
            report = summary(results)
            report['versions'] = {'nginx': nginx_version, 'suricata': suricata_version,
                'module_sha256': hashlib.sha256(lab.module.read_bytes()).hexdigest()}
            write(WORK/'results.json', json.dumps(report, indent=2), 0o600)
            print(json.dumps(report, indent=2))
    return 0 if summary(results)['result'] == 'PASS' else 1

if __name__ == '__main__': sys.exit(main())

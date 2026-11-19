#!/usr/bin/env python3
"""Reviewed bundle deployment; preflight/dry-run never write runtime or call sudo.
Bundle files are explicit; no account/module provisioning, no arbitrary shell hooks.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import time
import secrets
import tempfile
from datetime import datetime

spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).with_name('proof-nginx-lifecycle.py'))
life = importlib.util.module_from_spec(spec)
spec.loader.exec_module(life)

TARGETS = {
 'transaction-evidence.lua': '/etc/suricata/pbl4/transaction-evidence.lua',
 'nginx.conf': '/etc/nginx/nginx.conf',
 'site': '/etc/nginx/sites-available/pbl4-proxy',
 'formats': '/etc/nginx/conf.d/pbl4-ai-shadow.conf',
 'proof.js': '/etc/nginx/pbl4-proof/proof.js',
 'ca.crt': '/etc/nginx/pbl4-proof/student-ca.crt',
 'nginx.service.conf': '/etc/systemd/system/nginx.service.d/90-pbl4-proof.conf',
 'suricata.yaml': '/etc/suricata/pbl4/local-egress.yaml',
 'suricata.service.conf': '/etc/systemd/system/suricata.service.d/99-pbl4-local-egress.conf',
 'proof-nginx-lifecycle.py': '/usr/local/lib/websentinel/proof-nginx-lifecycle.py',
 'local-egress-guard.py': '/usr/local/lib/websentinel/local-egress-guard.py',
}


def command(args):
    return subprocess.run(args, check=True, timeout=45, text=True, capture_output=True).stdout


def read_bundle(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle/'manifest.json').read_text())
    if set(manifest['sha256']) != set(TARGETS):
        raise ValueError('Bundle must contain exactly the reviewed target set')
    for name, digest in manifest['sha256'].items():
        path = bundle/name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Bundle files must be regular files')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Bundle hash mismatch: ' + name)
    edge_ca = bundle/'edge-ca.crt'
    if edge_ca.is_symlink() or hashlib.sha256(edge_ca.read_bytes()).hexdigest() != manifest.get('edge_ca_sha256'):
        raise ValueError('Edge CA hash mismatch')
    return manifest


def validate(bundle):
    manifest = read_bundle(bundle)
    site = (bundle/'site').read_text()
    for marker in ('PBL4 TRANSACTION PROOF CANDIDATE v1', 'proxy_ssl_verify on;',
                   'proxy_ssl_name student.lab;', 'https://192.168.20.10:443',
                   '$probe_verified', '$probe_signed', 'tag=ai_shadow'):
        if marker not in site:
            raise ValueError('Candidate invariant missing: ' + marker)
    if 'proxy_ssl_verify off' in site:
        raise ValueError('TLS verification cannot be disabled')
    active_lines = [line.strip() for line in site.splitlines() if not line.lstrip().startswith('#')]
    sinks = [line for line in active_lines if 'access_log syslog:' in line and 'tag=ai_shadow' in line]
    mode = manifest.get('ai_mode', 'enabled')
    if mode not in ('enabled', 'deferred') or len(sinks) != (1 if mode == 'enabled' else 0):
        raise ValueError('AI mode and active telemetry configuration disagree')
    shadow = manifest.get('https_ml_shadow', False)
    mirror = [line for line in active_lines if line.startswith('mirror ')]
    if type(shadow) is not bool or mirror != (['mirror /_idps_https_projection;'] if shadow else []):
        raise ValueError('HTTPS shadow declaration and edge mirror disagree')
    if shadow:
        expected = (Path(__file__).resolve().parents[1]/'nginx/https-shadow-mirror.conf').read_text()
        if mode != 'enabled' or expected.replace('__SOCKET__','/run/websentinel-edge-shadow/receiver.sock') not in site:
            raise ValueError('HTTPS shadow requires the reviewed private receiver and enabled telemetry')
    if mode == 'deferred' and '# AI DEFERRED:' not in site:
        raise ValueError('Deferred telemetry must retain explicit restore marker')
    main = (bundle/'nginx.conf').read_text()
    if 'user websentinel-edge websentinel-edge;' not in main:
        raise ValueError('Dedicated worker identity missing')
    for kind in ('client_body', 'proxy', 'fastcgi', 'scgi', 'uwsgi'):
        if f'{kind}_temp_path /var/lib/websentinel-nginx/{kind};' not in main:
            raise ValueError('Dedicated temp path missing: ' + kind)
    unit = (bundle/'nginx.service.conf').read_text()
    for marker in ('Type=simple', 'KillMode=control-group', 'Restart=no',
                   '/usr/local/lib/websentinel/proof-nginx-lifecycle.py'):
        if marker not in unit:
            raise ValueError('Lifecycle unit missing: ' + marker)
    # YAML must remain passive, with the staged interface rather than CLI override.
    import yaml
    config = yaml.safe_load((bundle/'suricata.yaml').read_text())
    if config.get('stream', {}).get('inline') is not False:
        raise ValueError('Suricata must remain passive')
    captures = config.get('af-packet', [])
    if len(captures) != 1 or captures[0].get('interface') != 'lo':
        raise ValueError('Expected one loopback capture')
    if '18080' not in captures[0].get('bpf-filter', ''):
        raise ValueError('Local-egress BPF missing')
    lua = [entry['lua'] for entry in config.get('outputs', []) if 'lua' in entry]
    if lua != [{'enabled': True, 'scripts-dir': '/etc/suricata/pbl4', 'scripts': ['transaction-evidence.lua']}]:
        raise ValueError('Required transaction Lua output missing or misconfigured')
    if not (bundle/'transaction-evidence.lua').read_text().strip():
        raise ValueError('Lua script empty')
    eve = [entry['eve-log'] for entry in config.get('outputs', []) if 'eve-log' in entry and entry['eve-log'].get('enabled')]
    if len(eve) != 1 or eve[0].get('filetype', 'regular') != 'regular' or eve[0].get('filename') != 'eve.json':
        raise ValueError('Expected one regular eve.json output')
    if not any(t == 'http' or isinstance(t, dict) and 'http' in t for t in eve[0].get('types', [])):
        raise ValueError('HTTP EVE output required')
    return manifest


def check_sensor_config(bundle):
    """Same candidate Lua/rules, isolated output paths; no daemon/capture."""
    import yaml
    cfg = yaml.safe_load((bundle/'suricata.yaml').read_text())
    with tempfile.TemporaryDirectory(prefix='ws-suri-preflight-') as directory:
        work = Path(directory)
        shutil.copyfile(bundle/'transaction-evidence.lua', work/'transaction-evidence.lua')
        cfg.pop('run-as', None)  # Only syntax test identity; production config untouched.
        cfg['default-log-dir'] = str(work)
        cfg['unix-command'] = {'enabled': False}
        cfg['logging'] = {'outputs': [{'console': {'enabled': True}}]}
        for entry in cfg['outputs']:
            if 'lua' in entry:
                entry['lua']['scripts-dir'] = str(work)
        path = work/'suricata.yaml'
        path.write_text('%YAML 1.1\n---\n'+yaml.safe_dump(cfg))
        command(['/usr/bin/suricata', '-T', '-c', str(path), '-l', str(work)])


def safe_destination(path):
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('Resolve and review symlink destination first: ' + str(item))


class Deployment:
    def __init__(self, bundle, backup, runner=command, root=Path('/')):
        self.bundle, self.backup = Path(bundle), Path(backup)
        self.runner, self.root = runner, root

    def target(self, name):
        return self.root / TARGETS[name].lstrip('/')

    def snapshot(self):
        safe_destination(self.backup)
        self.backup.mkdir(mode=0o700, parents=False, exist_ok=False)
        index = {'files': {}, 'active': {}, 'verified': False}
        for service in ('nginx', 'suricata'):
            try:
                index['active'][service] = self.runner(['systemctl', 'is-active', service]).strip() == 'active'
            except subprocess.CalledProcessError:
                index['active'][service] = False
        for name in TARGETS:
            path = self.target(name)
            safe_destination(path)
            if path.exists():
                st = path.stat()
                if not stat.S_ISREG(st.st_mode):
                    raise ValueError('Non-regular destination')
                data = path.read_bytes()
                life.atomic(self.backup/name, data)
                index['files'][name] = {'mode': stat.S_IMODE(st.st_mode),
                    'uid': st.st_uid, 'gid': st.st_gid, 'sha256': hashlib.sha256(data).hexdigest()}
            else:
                index['files'][name] = None
        life.atomic(self.backup/'index.json', json.dumps(index).encode())

    def restore(self):
        safe_destination(self.backup)
        if os.geteuid() == 0:
            for item in (self.backup, *self.backup.iterdir()):
                st = item.lstat()
                if item.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
                    raise ValueError('Unsafe backup ownership/mode')
        index = json.loads((self.backup/'index.json').read_text())
        if set(index['files']) != set(TARGETS):
            raise ValueError('Incomplete backup')
        for name, metadata in index['files'].items():
            if metadata and hashlib.sha256((self.backup/name).read_bytes()).hexdigest() != metadata['sha256']:
                raise ValueError('Corrupt backup; refuse partial restore')
        for service in ('suricata', 'nginx'):
            self.runner(['systemctl', 'stop', service])
        for name, metadata in index['files'].items():
            path = self.target(name)
            safe_destination(path)
            if metadata is None:
                path.unlink(missing_ok=True)
            else:
                life.atomic(path, (self.backup/name).read_bytes(), metadata['mode'], metadata['gid'])
                if os.geteuid() == 0:
                    os.chown(path, metadata['uid'], metadata['gid'])
        if index.get('created_temp'):
            base = self.root/'var/lib/websentinel-nginx'
            safe_destination(base)
            for kind in ('client_body', 'proxy', 'fastcgi', 'scgi', 'uwsgi'):
                path = base/kind
                safe_destination(path)
                try:
                    path.rmdir()
                except FileNotFoundError:
                    pass
                except OSError:
                    print('RETAINED nonempty dedicated temp directory: ' + str(path))
            try:
                base.rmdir()
            except FileNotFoundError:
                pass
            except OSError:
                print('RETAINED dedicated temp root; old configuration does not use it')
        self.runner(['systemctl', 'daemon-reload'])
        self.runner(['/usr/sbin/nginx', '-t'])
        for service in ('nginx', 'suricata'):
            if index['active'][service]:
                self.runner(['systemctl', 'start', service])
                self.runner(['systemctl', 'is-active', service])
        if index['active']['nginx']:
            self.await_health(self.restored_http_health)

    def restored_http_health(self):
        for scheme in ('http', 'https'):
            for path, expected in (('/', '200'), ('/api/auth/me', '401')):
                argv = ['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '10',
                        '--output', '/dev/null', '--write-out', '%{http_code}']
                if scheme == 'https':
                    argv += ['--cacert', str(self.bundle/'edge-ca.crt')]
                if self.runner(argv + [scheme+'://192.168.10.1'+path]).strip() != expected:
                    raise RuntimeError('Restored HTTP/HTTPS checkpoint failed')

    def capture_health(self):
        import yaml
        cfg = yaml.safe_load((self.bundle/'suricata.yaml').read_text())
        logdir = self.root / cfg.get('default-log-dir', '/var/log/suricata').lstrip('/')
        generation = (logdir/'proof-generation').read_text().strip()
        if not re.fullmatch('[a-f0-9]{32}', generation):
            raise RuntimeError('Invalid sensor generation')
        if generation == getattr(self, 'previous_generation', None):
            raise RuntimeError('Sensor generation did not rotate')
        paths = [logdir/'eve.json', logdir/'chain.tsv']
        # Only inspect bytes appended after the canary checkpoint begins.
        offsets = [(p.stat().st_ino, p.stat().st_size) for p in paths]
        nonce = secrets.token_hex(16)
        target = '/api/auth/me?ws_capture_canary=' + nonce
        started = time.time()
        response = self.runner(['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '10',
            '--cacert', str(self.bundle/'edge-ca.crt'), '--dump-header', '-', '--output', '/dev/null',
            'https://192.168.10.1'+target])
        ids = re.findall(r'(?im)^X-Request-Id:\s*([a-f0-9]{32})\s*$', response)
        if len(ids) != 1 or not re.search(r'^HTTP/\S+ 401\b', response):
            raise RuntimeError('Canary status/request ID invalid')
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            data = []
            for path, (inode, offset) in zip(paths, offsets):
                if path.stat().st_ino != inode or path.stat().st_size < offset:
                    raise RuntimeError('Capture log rotated during checkpoint; retry explicitly')
                with path.open('rb') as stream:
                    stream.seek(offset)
                    chunk = stream.read(4*1024*1024+1)
                if len(chunk) > 4*1024*1024:
                    raise RuntimeError('Checkpoint log budget exceeded')
                data.append(chunk.decode('utf-8').splitlines())
            events = []
            for line in data[0]:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if (e.get('event_type') == 'http' and e.get('in_iface') == 'lo'
                    and e.get('src_ip') == '127.77.0.1' and e.get('dest_ip') == '127.77.0.2'
                    and (not getattr(self, 'require_eve_generation', False)
                         or e.get('host') == 'ws-generation-'+generation)
                    and e.get('http', {}).get('url') == target
                    and e.get('http', {}).get('http_method') == 'GET'
                    and datetime.fromisoformat(e['timestamp']).timestamp() >= started):
                    events.append(e)
            for line in data[1]:
                fields = line.split('\t')
                if len(fields) != 9:
                    continue
                flow, tx, proof, receipt, client, rid, scheme, host, gen = fields
                if (rid == ids[0] and gen == generation and proof and receipt and scheme == 'https'
                    and any(str(e.get('flow_id')) == flow and str(e.get('tx_id')) == tx for e in events)):
                    if (logdir/'proof-generation').read_text().strip() != generation:
                        raise RuntimeError('Sensor restarted during checkpoint')
                    return  # Presence/correlation only, NOT Rust Verified.
            time.sleep(0.25)
        raise RuntimeError('Fresh loopback HTTP/Lua evidence missing')

    def nginx_health(self):
        for service in ('nginx',):
            if self.runner(['systemctl', 'is-active', service]).strip() != 'active':
                raise RuntimeError(service + ' inactive')
        status = json.loads((self.root/'var/lib/websentinel-egress/status.json').read_text())
        if not 0 <= time.time() - status['checked_at'] <= 3 or not status['guard_snapshot'] or status['client_ip_verified']:
            raise RuntimeError('Stale/invalid guard status')
        for scheme in ('http', 'https'):
            for path, expected in (('/', '200'), ('/api/auth/me', '401')):
                argv = ['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '10',
                    '--output', '/dev/null', '--write-out', '%{http_code}']
                if scheme == 'https':
                    argv += ['--cacert', str(self.bundle/'edge-ca.crt')]
                code = self.runner(argv + [scheme+'://192.168.10.1'+path]).strip()
                if code != expected:
                    raise RuntimeError(scheme+' NGINX checkpoint status mismatch')

    def health(self):
        self.nginx_health()
        if self.runner(['systemctl', 'is-active', 'suricata']).strip() != 'active':
            raise RuntimeError('suricata inactive')
        self.capture_health()

    def await_health(self, check):
        for attempt in range(20):
            try:
                check()
                return
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                if attempt == 19:
                    raise
                time.sleep(0.5)

    def prepare_temp(self):
        """Only called after stop; never chmod existing production temp/log paths."""
        account = life.identity('websentinel-edge')
        base = self.root/'var/lib/websentinel-nginx'
        safe_destination(base)
        if base.exists():
            raise ValueError('Dedicated temp root already exists; review before apply')
        # Record intent before mutation so partial creation is rollback-safe.
        index = json.loads((self.backup/'index.json').read_text())
        index['created_temp'] = True
        life.atomic(self.backup/'index.json', json.dumps(index).encode())
        base.mkdir(mode=0o750)
        os.chown(base, 0, account.pw_gid)
        for kind in ('client_body', 'proxy', 'fastcgi', 'scgi', 'uwsgi'):
            path = base/kind
            path.mkdir(mode=0o700)
            os.chown(path, account.pw_uid, account.pw_gid)

    def apply(self):
        validate(self.bundle)
        self.snapshot()
        try:
            # Keep the old sensor running until the new HTTP/HTTPS path is healthy.
            self.runner(['systemctl', 'stop', 'nginx'])
            self.prepare_temp()
            for name in TARGETS:
                path = self.target(name)
                safe_destination(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                life.atomic(path, (self.bundle/name).read_bytes(), 0o644)
            self.runner(['systemctl', 'daemon-reload'])
            for service, expected in (('nginx', '/usr/local/lib/websentinel/proof-nginx-lifecycle.py'),
                                      ('suricata', '/etc/suricata/pbl4/local-egress.yaml')):
                actual = self.runner(['systemctl', 'show', service, '--property=ExecStart', '--value'])
                if expected not in actual:
                    raise RuntimeError('Conflicting systemd override: ' + service)
            self.runner(['/usr/sbin/nginx', '-t'])
            self.runner(['/usr/bin/suricata', '-T', '-c', TARGETS['suricata.yaml']])
            self.runner(['systemctl', 'start', 'nginx'])
            self.await_health(self.nginx_health)
            # Only now switch the sensor from its existing vmnet3 process to lo.
            import yaml
            cfg = yaml.safe_load((self.bundle/'suricata.yaml').read_text())
            marker = self.root / cfg.get('default-log-dir', '/var/log/suricata').lstrip('/') / 'proof-generation'
            self.previous_generation = marker.read_text().strip() if marker.exists() else None
            self.runner(['systemctl', 'stop', 'suricata'])
            self.runner(['systemctl', 'start', 'suricata'])
            self.await_health(self.health)
        except Exception as original:
            try:
                self.restore()
            except Exception as rollback:
                raise RuntimeError('APPLY FAILED; ROLLBACK ALSO FAILED; keep traffic closed and inspect services') from rollback
            raise RuntimeError('Apply failed; original configuration restored') from original


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['preflight', 'dry-run', 'apply', 'health', 'rollback'])
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--backup', type=Path, required=True, help='New root-only directory for apply; existing for rollback')
    p.add_argument('--approve-host-change', action='store_true')
    args = p.parse_args()
    if args.action in ('apply', 'rollback'):
        if not args.approve_host_change or os.geteuid() != 0:
            p.error('Explicit --approve-host-change and root required; script never invokes sudo')
        # Privileged execution must not consume caller-writable files or ancestors.
        for path in (args.bundle.resolve(), *args.bundle.resolve().parents):
            st = path.stat()
            if st.st_uid != 0 or st.st_mode & 0o022:
                p.error('Bundle and ancestors must be root-owned and not group/world writable')
        backup_parent = args.backup.resolve().parent
        for path in (backup_parent, *backup_parent.parents):
            st = path.stat()
            if st.st_uid != 0 or st.st_mode & 0o022:
                p.error('Backup parent and ancestors must be root-owned and not writable by others')
        for path in args.bundle.iterdir():
            if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
                p.error('Unsafe bundle entry')
    deployment = Deployment(args.bundle, args.backup)
    if args.action == 'rollback':
        deployment.restore()
    elif args.action == 'health':
        deployment.health()
    else:
        manifest = validate(args.bundle)
        if args.action == 'dry-run':
            print(json.dumps({'writes': False, 'ai_worker': manifest.get('ai_worker', 'ENABLED_NOT_ACCEPTED'), 'targets': TARGETS, 'steps': [
                'validate identity/module/CA and root-owned bundle', 'backup',
                'stop nginx; create dedicated temp directories (old paths unchanged)', 'install reviewed bundle', 'daemon-reload',
                'validate effective units and syntax', 'start supervisor and sensor',
                'health; rollback on failure'], 'runtime_verified': False}, indent=2))
            return
        check_sensor_config(args.bundle)
        account = life.identity('websentinel-edge')
        formats = (args.bundle/'formats').read_text()
        if f'js_var $probe_key_gid {account.pw_gid};' not in formats:
            p.error('Candidate key GID differs from dedicated account GID')
        for proc in Path('/proc').iterdir():
            if proc.name.isdigit():
                try:
                    if proc.stat().st_uid == account.pw_uid:
                        p.error('Dedicated UID already has processes; review/stop before initial apply')
                except FileNotFoundError:
                    pass
        main_config = (args.bundle/'nginx.conf').read_text()
        modules = re.findall(r'(?m)^load_module\s+([^;]*ngx_http_js_module\.so);', main_config)
        if not modules or any(not Path(module).is_file() for module in modules):
            p.error('Reviewed njs module must already exist; no module is installed by this tool')
        for module in modules:
            for path in (Path(module), *Path(module).parents):
                st = path.stat()
                if path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
                    p.error('Module/ancestors must be root-owned and not writable by others: ' + str(path))
        if (deployment.root/'var/lib/websentinel-nginx').exists():
            p.error('Dedicated temp root already exists; review before initial apply')
        if not (args.bundle/'edge-ca.crt').is_file():
            p.error('Public Edge CA required for HTTPS health; never use curl -k')
        command(['openssl', 'x509', '-in', str(args.bundle/'ca.crt'), '-noout', '-checkend', '86400'])
        if not Path('/sys/fs/cgroup/cgroup.controllers').exists():
            p.error('cgroup v2 required')
        for name in TARGETS:
            safe_destination(deployment.target(name))
        print(json.dumps({'action': args.action, 'targets': TARGETS,
            'runtime_verified': False, 'auto_block': False, 'writes': args.action == 'apply'}, indent=2))
        if args.action == 'apply':
            deployment.apply()

if __name__ == '__main__':
    main()

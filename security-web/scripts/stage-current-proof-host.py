#!/usr/bin/env python3
"""Stage current reviewed Host with real identity/public certificates, no sudo.
Missing prerequisites are reported together; no placeholder GID/CA or partial bundle.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def inspect(edge_ca, identity, module):
    blockers = []
    account = None
    try:
        account = identity('websentinel-edge')
    except (KeyError, ValueError) as error:
        blockers.append('Dedicated exclusive websentinel-edge account/group missing or invalid: '+type(error).__name__)
    paths = {'Student public CA': Path.home()/'ws-student-trust/ca.crt',
             'Edge public CA': edge_ca, 'installed njs module': module,
             'NGINX base': Path('/etc/nginx/nginx.conf'),
             'Suricata base': Path('/etc/suricata/pbl4/post-proxy.yaml')}
    for label, path in paths.items():
        try:
            with path.open('rb') as stream: stream.read(1)
        except OSError:
            blockers.append(label+' missing/unreadable: '+str(path))
    if module.exists():
        for path in (module, *module.parents):
            st = path.stat()
            if path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
                blockers.append('Module path must be root-owned, non-symlink and not writable by others')
                break
    return account, blockers


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--edge-ca', type=Path, required=True, help='Public Edge trust anchor; never Student CA substituted')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location('life', HERE/'proof-nginx-lifecycle.py')
    life = importlib.util.module_from_spec(spec); spec.loader.exec_module(life)
    module = Path('/usr/lib/nginx/modules/ngx_http_js_module.so')
    account, blockers = inspect(a.edge_ca, life.identity, module)
    print(json.dumps({'status': 'BLOCKED' if blockers else 'PASS_INPUTS_ONLY',
        'ai_worker':'DEFERRED', 'blockers':blockers, 'runtime_verified':False}, indent=2), flush=True)
    if blockers: return 2
    if a.check_only: return 0
    subprocess.run([sys.executable, HERE/'check-njs-abi.py', '--module', module], check=True)
    subprocess.run([sys.executable, HERE/'stage-proof-host.py', '--output', a.output,
        '--suricata-base','/etc/suricata/pbl4/post-proxy.yaml',
        '--student-ca',Path.home()/'ws-student-trust/ca.crt', '--edge-ca',a.edge_ca,
        '--edge-cert','/etc/nginx/pbl4-tls/lab.crt', '--edge-key','/etc/nginx/pbl4-tls/lab.key',
        '--module',module,'--gid',str(account.pw_gid),'--ai-mode','deferred'], check=True)
    for action in ('preflight','dry-run'):
        subprocess.run([sys.executable,HERE/'deploy-proof-host.py',action,
            '--bundle',a.output,'--backup','/var/backups/ws-proof-before'],check=True)
    return 0

if __name__ == '__main__': sys.exit(main())

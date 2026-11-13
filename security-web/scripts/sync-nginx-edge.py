#!/usr/bin/env python3
"""Review/render by default; --apply validates, backs up and reloads NGINX only."""
import argparse
import datetime
import importlib.util
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-ip', default='192.168.10.1')
    parser.add_argument('--upstream-ip', default='192.168.20.10')
    parser.add_argument('--lan-ip')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    installer = load('installer', 'install-ai-shadow-host.py')
    if args.rollback:
        if os.geteuid() != 0:
            parser.error('Rollback requires sudo')
        installer.restore(json.loads(args.rollback.read_text()))
        installer.run(['/usr/sbin/nginx', '-t'])
        installer.run(['systemctl', 'reload', 'nginx'])
        return
    site, formats = load('prepare', 'prepare-nginx-host.py').render(args.host_ip, args.upstream_ip, args.lan_ip)
    if not args.apply:
        print(site)
        print('Review HTTP-context limits in nginx/pbl4-edge-limits.conf. Use --apply to install.')
        return
    if os.geteuid() != 0:
        parser.error('--apply requires sudo')
    addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr'], text=True))
    assigned = {a['local'] for interface in addresses for a in interface.get('addr_info', [])}
    for address in [args.host_ip, args.lan_ip]:
        if address and address not in assigned:
            parser.error('Listener IP is not assigned on this host: ' + address)
    target = Path('/etc/nginx/sites-available/pbl4-proxy').resolve()
    config = Path('/etc/nginx/conf.d/pbl4-ai-shadow.conf')
    installer.syntax(target, site, formats)
    if target.read_text() == site and config.read_text() == formats:
        print('Already synchronized; no reload.')
        return
    backup = Path('/var/backups/pbl4-nginx-edge') / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    records = installer.snapshot(backup, [target, config])
    manifest = backup / 'rollback.json'
    installer.atomic(manifest, json.dumps(records).encode(), 0o600)
    try:
        installer.atomic(target, site.encode(), 0o644)
        installer.atomic(config, formats.encode(), 0o644)
        installer.run(['/usr/sbin/nginx', '-t'])
        installer.run(['systemctl', 'reload', 'nginx'])
    except BaseException:
        installer.restore(records)
        installer.run(['/usr/sbin/nginx', '-t'])
        installer.run(['systemctl', 'reload', 'nginx'])
        raise
    print('Synchronized. Rollback: sudo python3 ' + str(Path(__file__).resolve()) + ' --rollback ' + str(manifest))

if __name__ == '__main__':
    main()

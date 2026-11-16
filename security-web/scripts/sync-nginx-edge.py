#!/usr/bin/env python3
"""Review/render by default; --apply validates, backs up and reloads or starts NGINX only."""
import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def nginx_active():
    result = subprocess.run(['systemctl', 'is-active', '--quiet', 'nginx'],
                            check=False, timeout=15)
    if result.returncode not in (0, 3):
        raise RuntimeError('Cannot determine NGINX service state')
    return result.returncode == 0


def activate(installer, changed=True):
    active = nginx_active()
    if changed or not active:
        installer.run(['systemctl', 'reload' if active else 'start', 'nginx'])
    if not nginx_active():
        raise RuntimeError('NGINX is not active after applying configuration')


def recover(installer, records, was_active):
    # Preserve the original apply exception even if the old configuration is invalid.
    try:
        installer.restore(records)
        installer.run(['/usr/sbin/nginx', '-t'])
        if was_active:
            activate(installer)
    except Exception as error:
        print('ROLLBACK WARNING: old files may be restored but service recovery failed: '
              + str(error), file=sys.stderr)


def tls_options(prepare, current, cert=None, key=None, disable=False):
    if disable:
        if cert or key:
            raise ValueError('--disable-https cannot be combined with TLS paths')
        return None, None
    if cert or key:
        if not cert or not key:
            raise ValueError('Both --tls-cert and --tls-key are required')
        return prepare.certificate_path(cert), prepare.certificate_path(key)
    return prepare.existing_tls(current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-ip', default='192.168.10.1')
    parser.add_argument('--upstream-ip', default='192.168.20.10')
    parser.add_argument('--lan-ip')
    parser.add_argument('--tls-cert', help='Absolute certificate path; pair with --tls-key')
    parser.add_argument('--tls-key', help='Absolute private key path; never copied into Git')
    parser.add_argument('--disable-https', action='store_true', help='Explicitly remove HTTPS; keep HTTP')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    installer = load('installer', 'install-ai-shadow-host.py')
    if args.rollback:
        if os.geteuid() != 0:
            parser.error('Rollback requires sudo')
        installer.restore(json.loads(args.rollback.read_text()))
        installer.run(['/usr/sbin/nginx', '-t'])
        activate(installer)
        return
    target = Path('/etc/nginx/sites-available/pbl4-proxy').resolve()
    prepare = load('prepare', 'prepare-nginx-host.py')
    cert, key = tls_options(prepare, target.read_text() if target.exists() else '',
                            args.tls_cert, args.tls_key, args.disable_https)
    site, formats = prepare.render(args.host_ip, args.upstream_ip, args.lan_ip, cert, key)
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
        installer.run(['/usr/sbin/nginx', '-t'])
        activate(installer, changed=False)
        print('Already synchronized; NGINX active.')
        return
    backup = Path('/var/backups/pbl4-nginx-edge') / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    records = installer.snapshot(backup, [target, config])
    manifest = backup / 'rollback.json'
    installer.atomic(manifest, json.dumps(records).encode(), 0o600)
    was_active = nginx_active()
    print('Backup: ' + str(manifest))
    try:
        installer.atomic(target, site.encode(), 0o644)
        installer.atomic(config, formats.encode(), 0o644)
        installer.run(['/usr/sbin/nginx', '-t'])
        activate(installer)
    except BaseException:
        recover(installer, records, was_active)
        raise
    print('Synchronized. Rollback: sudo python3 ' + str(Path(__file__).resolve()) + ' --rollback ' + str(manifest))

if __name__ == '__main__':
    main()

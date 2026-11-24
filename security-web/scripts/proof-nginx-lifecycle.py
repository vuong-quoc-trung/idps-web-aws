#!/usr/bin/env python3
"""Foreground supervisor for the existing nginx.service; opt-in, never run by staging.
A readiness snapshot is NOT transaction-time trust. No Rust attribution is enabled.
"""
import argparse
import fcntl
import hashlib
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import signal
import subprocess
import time

spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('local-egress-guard.py'))
guard_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_module)


def atomic(path, data, mode=0o600, gid=0):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if os.geteuid() == 0:
                os.fchown(stream.fileno(), 0, gid)
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)


def rotate(path, gid):
    # Always new material, including crash/restart. Never restore old key backups.
    material = {'kid': secrets.token_hex(8), 'epoch': secrets.token_hex(16),
                'key': secrets.token_hex(32)}
    atomic(path, json.dumps(material).encode(), 0o640, gid)


def identity(name):
    entry = pwd.getpwnam(name)
    if entry.pw_uid <= 0 or name in ('root', 'www-data', 'nobody'):
        raise ValueError('Exclusive dedicated NGINX account required')
    if not entry.pw_shell.endswith(('nologin', '/false')):
        raise ValueError('Dedicated account must not have a login shell')
    group = grp.getgrgid(entry.pw_gid)
    if group.gr_name != name or any(member != name for member in group.gr_mem):
        raise ValueError('Exclusive matching primary group required')
    if set(os.getgrouplist(name, entry.pw_gid)) != {entry.pw_gid}:
        raise ValueError('Supplementary groups are not allowed')
    if any(other.pw_name != name and (other.pw_uid == entry.pw_uid or other.pw_gid == entry.pw_gid)
           for other in pwd.getpwall()):
        raise ValueError('UID/GID shared with another account')
    return entry


def secure_directory(path, gid, mode):
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    st = path.lstat()
    if path.is_symlink() or st.st_uid != 0:
        raise ValueError('Directory must be root-owned and not a symlink')
    os.chown(path, 0, gid)
    os.chmod(path, mode)


def run(args):
    if os.geteuid() != 0:
        raise RuntimeError('Lifecycle requires root inside the reviewed nginx.service')
    if args.unit == "ws-native-edge.service":
        if args.user != "ws-native-edge":
            raise ValueError("Native guard requires its dedicated worker")
        guard_module.TABLE = "ws_native_egress"
        guard_module.SOURCE, guard_module.DEST, guard_module.PORT = "127.78.0.1", "127.78.0.2", 28080
    account = identity(args.user)
    state, key = Path(args.state), Path(args.key)
    secure_directory(state, 0, 0o700)
    secure_directory(key.parent, account.pw_gid, 0o750)
    lock = os.open(state/'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    nginx = ['/usr/sbin/nginx', '-c', args.config]
    group = next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
                 if line.startswith('0::')).lstrip('/')
    if not group or not group.endswith('/' + args.unit):
        raise RuntimeError('Must run in dedicated nginx.service cgroup v2')
    guard = guard_module.Guard(group, account.pw_uid)
    recovery = state/'deny.json'
    process = None
    stopping = False

    def stop_signal(*unused):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    # Do not reload behind the supervisor: conservatively stop, require restart.
    signal.signal(signal.SIGHUP, stop_signal)
    try:
        tables = json.loads(guard.command(['nft', '-j', 'list', 'tables']).stdout)['nftables']
        exists = any(v.get('table', {}).get('name') == guard_module.TABLE and
                     v['table'].get('family') == 'inet' for v in tables)
        if exists:
            # Only adopt a deny-only snapshot recorded by our clean shutdown.
            # Unclean supervisor crash with an allow table requires operator recovery.
            if not recovery.exists() or guard.snapshot() != json.loads(recovery.read_text()):
                raise RuntimeError('Unknown/stale guard table: keep stopped; explicit recovery required')
            guard.owned, guard.state = True, 'DENY_ONLY'
        else:
            guard.arm()
        recovery.unlink(missing_ok=True)
        rotate(key, account.pw_gid)
        expected = hashlib.sha256(key.read_bytes()).digest()
        effective = subprocess.run(nginx + ['-T'], check=True, timeout=30,
                                   text=True, capture_output=True).stdout
        if not re.search(r'(?m)^user\s+' + re.escape(args.user) + r'\s+' + re.escape(args.user) + r'\s*;', effective):
            raise RuntimeError('Effective NGINX identity differs from guard UID/GID')
        if 'PBL4 TRANSACTION PROOF CANDIDATE v1' not in effective:
            raise RuntimeError('Proof site is not included in effective configuration')
        guard.grant()
        process = subprocess.Popen(nginx + ['-g', 'daemon off;'])
        while not stopping:
            st = key.lstat()
            good_key = (not key.is_symlink() and st.st_uid == 0 and
                        st.st_gid == account.pw_gid and st.st_mode & 0o777 == 0o640 and
                        hashlib.sha256(key.read_bytes()).digest() == expected)
            if process.poll() is not None or not guard.ready() or not good_key:
                raise RuntimeError('NGINX/key/guard fault: stop and latch closed')
            atomic(state/'status.json', json.dumps({'pid': process.pid,
                'checked_at': time.time(), 'guard_snapshot': True,
                'client_ip_verified': False, 'auto_block': False}).encode())
            time.sleep(0.5)
    finally:
        (state/'status.json').unlink(missing_ok=True)
        try:
            guard.revoke()
            if guard.owned:
                atomic(recovery, json.dumps(guard.snapshot()).encode())
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            key.unlink(missing_ok=True)
            os.close(lock)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default='/etc/nginx/nginx.conf')
    p.add_argument('--unit', choices=['nginx.service', 'websentinel-beta-edge.service', 'ws-native-edge.service'], default='nginx.service')
    p.add_argument('--user', default='websentinel-edge')
    p.add_argument('--key', default='/etc/nginx/pbl4-proof/key.json')
    p.add_argument('--state', default='/var/lib/websentinel-egress')
    run(p.parse_args())

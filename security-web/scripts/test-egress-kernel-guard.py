#!/usr/bin/env python3
"""Privileged, isolated prerequisite test. Never installs a production policy.
Run with sudo and --run-isolated. Only a unique cgroup subtree is made on host.
All nftables, listeners and AF_PACKET sockets run in an unshared network namespace.
"""
import argparse
import importlib.util
import http.client
import http.server
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid

CGROOT = Path('/sys/fs/cgroup')
SELF = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location('egress_manager', SELF.with_name('local-egress-guard.py'))
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
TABLE = manager.TABLE


def policy(group, uid=65534, allow=True):
    if not re.fullmatch(r'ws-egress-test-[0-9a-f]{32}/allowed', group):
        raise ValueError('Not a dedicated test cgroup')
    return manager.render(group, uid, allow)


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=15, **kwargs)


def probe(group, uid):
    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('Refusing probe in initial network namespace')
    path = Path(group)
    if path.parent.parent != CGROOT or not re.fullmatch(r'ws-egress-test-[0-9a-f]{32}', path.parent.name) or path.name not in ('allowed', 'denied'):
        raise RuntimeError('Invalid probe cgroup')
    (path / 'cgroup.procs').write_text(str(os.getpid()))
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    connection = http.client.HTTPConnection('127.77.0.2', 18080,
        source_address=('127.77.0.1', 0), timeout=.8)
    try:
        connection.request('GET', '/probe', headers={'X-Forwarded-For': '192.0.2.99',
            'X-Request-Id': 'b' * 32})
        response = connection.getresponse()
        response.read()
        print(json.dumps({'connected': True, 'status': response.status}))
    except (OSError, http.client.HTTPException):
        print(json.dumps({'connected': False}))
    finally:
        connection.close()


def namespace_test(root, host_ns):
    if os.geteuid() != 0 or os.readlink('/proc/self/ns/net') == host_ns:
        raise RuntimeError('Refusing host network namespace')
    links = json.loads(subprocess.check_output(['ip', '-j', 'link'], text=True))
    if {link['ifname'] for link in links} != {'lo'}:
        raise RuntimeError('Namespace contains external interfaces')
    if root.parent != CGROOT or not re.fullmatch(r'ws-egress-test-[0-9a-f]{32}', root.name):
        raise RuntimeError('Invalid cgroup scope')
    run(['ip', 'link', 'set', 'lo', 'up'])
    # No fallback to an IP-only or UID-only rule if parsing/loading fails.
    rules = policy(root.name + '/allowed')
    run(['nft', '--check', '-f', '-'], input=rules, text=True)
    run(['nft', '-f', '-'], input=rules, text=True)
    seen = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(1)
            self.send_response(204)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(('127.77.0.2', 18080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    capture = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    capture.bind(('lo', 0))
    capture.settimeout(.05)

    def one(name, group, uid, expected):
        # A new process enters its cgroup BEFORE creating a socket, then loses
        # root UID and supplementary groups. No existing host process is moved.
        while True:
            try: capture.recv(65535)
            except socket.timeout: break
        before = len(seen)
        process = subprocess.Popen([sys.executable, str(SELF), '--probe', str(root / group), str(uid)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        frames = 0
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            try:
                frame = capture.recv(65535)
                # Ethernet framing on Linux loopback; count only test TCP tuple.
                if len(frame) >= 54 and frame[12:14] == b'\x08\x00' and frame[23] == 6:
                    offset = 14 + (frame[14] & 15) * 4
                    if (frame[26:30] == socket.inet_aton('127.77.0.1') and
                        frame[30:34] == socket.inet_aton('127.77.0.2') and
                        struct.unpack('!H', frame[offset + 2:offset + 4])[0] == 18080):
                        frames += 1
            except socket.timeout:
                if process.poll() is not None: break
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate()
            raise RuntimeError('Probe timeout')
        if process.returncode != 0:
            raise RuntimeError('Probe could not execute: ' + stderr)
        result = json.loads(stdout)
        passed = (result['connected'] == expected and
                  len(seen) - before == int(expected) and
                  (frames > 0 if expected else frames == 0))
        print(json.dumps({'case': name, 'result': 'PASS' if passed else 'FAIL',
            'http_received': len(seen) - before, 'outbound_frames': frames,
            'connected': result['connected']}), flush=True)
        if not passed:
            raise RuntimeError('Kernel boundary test failed: ' + name)

    try:
        one('allowed_uid_and_cgroup', 'allowed', 65534, True)
        one('same_uid_other_cgroup_source_bound', 'denied', 65534, False)
        one('other_uid_allowed_cgroup_source_bound', 'allowed', 65533, False)
        one('other_uid_other_cgroup_source_bound', 'denied', 65533, False)
        # A deny-only policy is replaced atomically with a fresh grant later.
        run(['nft', '-f', '-'], input=f'delete table inet {TABLE}\n' +
            policy(root.name + '/allowed', allow=False), text=True)
        one('grant_removed_fail_closed', 'allowed', 65534, False)
        run(['nft', '-f', '-'], input=f'delete table inet {TABLE}\n' + rules, text=True)
        one('grant_restored', 'allowed', 65534, True)
        print(json.dumps({'kernel_prerequisite': 'PASS', 'production_ready': False,
            'pending': ['NGINX lifecycle', 'Suricata EVE', 'Rust dynamic readiness',
                        'policy deletion / event-time trust']}), flush=True)
    finally:
        capture.close()
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-isolated', action='store_true')
    parser.add_argument('--with-nginx-suricata', action='store_true', help='Run existing NGINX/TLS + actual Suricata harness with guard')
    parser.add_argument('--namespace', nargs=2, metavar=('CGROUP', 'HOST_NETNS'), help=argparse.SUPPRESS)
    parser.add_argument('--probe', nargs=2, help=argparse.SUPPRESS)
    parser.add_argument('--live-proof-module', type=Path)
    parser.add_argument('--rust-test-binary', type=Path)
    args = parser.parse_args()
    if args.live_proof_module and not args.rust_test_binary:
        parser.error('--rust-test-binary required for live proof')
    if args.probe:
        probe(args.probe[0], int(args.probe[1])); return
    if args.namespace:
        namespace_test(Path(args.namespace[0]), args.namespace[1]); return
    if not args.run_isolated:
        parser.error('Explicit --run-isolated required')
    if os.geteuid() != 0 or not (CGROOT / 'cgroup.controllers').is_file():
        parser.error('Requires sudo and cgroup v2')
    root = CGROOT / ('ws-egress-test-' + uuid.uuid4().hex)
    child = None
    try:
        root.mkdir()
        for name in ('allowed', 'denied'): (root / name).mkdir()
        command = [sys.executable, str(SELF), '--namespace', str(root), os.readlink('/proc/self/ns/net')]
        if args.with_nginx_suricata:
            command = [sys.executable, str(SELF.with_name('test-local-egress-capture.py')), '--kernel-cgroup', str(root)]
        if args.live_proof_module:
            command = [sys.executable, str(SELF.with_name('test-live-transaction-proof.py')),
                       '--isolated-root', '--kernel-cgroup', str(root),
                       '--module', str(args.live_proof_module.resolve()),
                       '--rust-test-binary', str(args.rust_test_binary.resolve())]
        child = subprocess.Popen(['unshare', '--net', '--'] + command, start_new_session=True)
        try:
            code = child.wait(timeout=180)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=10)
            raise RuntimeError('Interrupted; isolated test stopped')
        if code:
            raise RuntimeError(f'Isolated test failed (exit {code}); no weaker fallback')
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL); child.wait()
        # Only our unique subtree. Never write host/root cgroup.kill.
        if root.exists():
            kill = root / 'cgroup.kill'
            if kill.exists(): kill.write_text('1')
            for name in ('allowed', 'denied'):
                path = root / name
                if path.exists(): path.rmdir()
            root.rmdir()


if __name__ == '__main__':
    main()

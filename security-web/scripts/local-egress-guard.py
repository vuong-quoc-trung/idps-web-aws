#!/usr/bin/env python3
"""Local-egress nftables lifecycle primitives. No CLI applies host policy.
A readiness snapshot is operational evidence, NEVER event-time attribution proof.
"""
import json
from pathlib import Path
import re
import subprocess

TABLE = 'pbl4_local_egress'
SOURCE = '127.77.0.1'
DEST = '127.77.0.2'
PORT = 18080


def render(group, uid, allow=False):
    parts = group.split('/')
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p in ('.', '..') for p in parts):
        raise ValueError('Invalid cgroup path')
    if not isinstance(uid, int) or uid <= 0:
        raise ValueError('Dedicated non-root worker UID required')
    grant = (f'ip saddr {SOURCE} meta skuid {uid} '
             f'socket cgroupv2 level {len(parts)} "{group}" counter accept') if allow else ''
    return f'''table inet {TABLE} {{
 chain output {{
  type filter hook output priority -150; policy accept;
  ip daddr {DEST} tcp dport {PORT} jump egress
 }}
 chain egress {{
  {grant}
  counter drop
 }}
}}
'''


def canonical(value):
    """Ignore only kernel handles and changing counters, not rule order/expressions."""
    if isinstance(value, list):
        return [canonical(v) for v in value if not (isinstance(v, dict) and 'metainfo' in v)]
    if isinstance(value, dict):
        return {k: ({} if k == 'counter' else canonical(v))
                for k, v in value.items() if k not in ('handle', 'packets', 'bytes')}
    return value


def execute(args, **kwargs):
    return subprocess.run(args, check=True, timeout=10, text=True, capture_output=True, **kwargs)


class Guard:
    def __init__(self, group, uid, command=execute, cgroup_root=Path('/sys/fs/cgroup')):
        render(group, uid)  # validate before any command
        self.group, self.uid, self.command = group, uid, command
        self.path = cgroup_root / group
        self.identity = None
        self.expected = None
        self.faulted = False
        self.state = 'NOT_READY'
        self.owned = False

    def snapshot(self):
        return canonical(json.loads(self.command(['nft', '-j', 'list', 'table', 'inet', TABLE]).stdout))

    def replace(self, allow):
        # Never flush the ruleset. A failed transaction leaves old rules in place.
        # Caller must serialize lifecycle operations; existing unrelated table is
        # refused at initial arm(), rather than silently taken over.
        rules = f'delete table inet {TABLE}\n' + render(self.group, self.uid, allow)
        self.command(['nft', '--check', '-f', '-'], input=rules)
        self.command(['nft', '-f', '-'], input=rules)

    def arm(self):
        if self.faulted or self.state != 'NOT_READY':
            raise RuntimeError('Fresh lifecycle required; faults are latched')
        # nft add fails if table already exists; never adopt a foreign policy.
        rules = render(self.group, self.uid)
        self.command(['nft', '--check', '-f', '-'], input=rules)
        # Explicit add table without an existing-table idempotency assumption.
        tables = json.loads(self.command(['nft', '-j', 'list', 'tables']).stdout)
        if any(item.get('table', {}).get('name') == TABLE and
               item['table'].get('family') == 'inet' for item in tables['nftables']):
            raise RuntimeError('Reserved table already exists; operator review required')
        self.command(['nft', '-f', '-'], input=rules)
        self.owned = True
        self.state = 'DENY_ONLY'

    def grant(self):
        if self.faulted or self.state != 'DENY_ONLY':
            raise RuntimeError('Must arm deny-only boundary first')
        self.identity = self.path.stat().st_ino
        self.replace(True)
        self.expected = self.snapshot()
        self.state = 'READY_SNAPSHOT_ONLY'

    def ready(self):
        if self.faulted or self.state != 'READY_SNAPSHOT_ONLY':
            return False
        try:
            ok = self.path.stat().st_ino == self.identity and self.snapshot() == self.expected
        except (OSError, subprocess.SubprocessError, ValueError):
            ok = False
        if not ok:
            self.faulted = True
            self.state = 'FAULTED'
        return ok

    def revoke(self):
        if not self.owned:
            return  # Never alter a pre-existing/foreign table after failed arm.
        self.faulted = True
        self.state = 'FAULTED'
        self.expected = None
        try:
            self.replace(False)
        except subprocess.SubprocessError:
            # Table may have been deleted. Restore a deny-only table; if this
            # also fails the caller MUST keep NGINX stopped and report failure.
            self.command(['nft', '-f', '-'], input=render(self.group, self.uid))

    def before_reload(self):
        if not self.ready():
            raise RuntimeError('Reload refused: guard not ready')

    def status(self):
        ready = self.ready()
        return {'state': self.state, 'ready_snapshot': ready,
                'attribution_ready': False,
                'reason': 'No event-time proof across policy deletion gaps'}


class Lifecycle:
    """Single-owner NGINX lifecycle adapter; callbacks control only owned process.

    Caller must execute tick periodically and route SIGHUP through reload().
    No automatic recovery following a fault. This stops service AFTER a detected
    gap, not before the gap; it cannot provide event-time trust to Rust.
    """
    def __init__(self, guard, start, stop, reload, alive):
        self.guard = guard
        self.start_process, self.stop_process = start, stop
        self.reload_process, self.alive = reload, alive

    def start(self):
        try:
            self.guard.arm()
            self.guard.grant()
            self.start_process()
            if not self.guard.ready() or not self.alive():
                raise RuntimeError('NGINX/guard startup not ready')
        except Exception:
            self.stop()
            raise

    def stop(self):
        # Revoke before shutdown so no new request passes while workers drain.
        try:
            self.guard.revoke()
        finally:
            self.stop_process()

    def tick(self):
        if not self.guard.ready() or not self.alive():
            self.stop()
            return False
        return True

    def reload(self):
        if not self.tick():
            raise RuntimeError('NGINX reload refused after guard fault')
        try:
            self.reload_process()
            if not self.tick():
                raise RuntimeError('NGINX guard changed during reload')
        except Exception:
            self.stop()
            raise

    def restart(self):
        if not self.tick():
            raise RuntimeError('Explicit operator recovery required after fault')
        self.stop()
        # Reuse the deny-only boundary, re-resolving the cgroup identity.
        # This is intentional lifecycle restart, never automatic fault healing.
        self.guard.faulted = False
        self.guard.state = 'DENY_ONLY'
        try:
            self.guard.grant()
            self.start_process()
            if not self.tick():
                raise RuntimeError('NGINX restart not ready')
        except Exception:
            self.stop()
            raise

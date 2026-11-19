#!/usr/bin/env python3
"""Render an optional dedicated-worker identity fragment; never creates users or installs files."""
import argparse
import re


def render(user, uid, group, gid):
    for value in (user, group):
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', value):
            raise ValueError('Invalid account name')
    if min(uid, gid) <= 0 or user in ('root', 'www-data', 'nobody') or group in ('root', 'www-data', 'nogroup'):
        raise ValueError('A dedicated non-root account/group is required')
    return f'''# Optional NGINX main-context fragment, not an additional instance.
# Operator must verify exclusive UID {uid} / GID {gid} before installing.
user {user} {group};
worker_rlimit_core 0;
# Key directory: root:{group} 0750; key: root:{group} 0640.
# Worker must have no supplementary groups. No other service may use UID/GID.
'''

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user', default='websentinel-edge')
    p.add_argument('--group', default='websentinel-edge')
    p.add_argument('--uid', type=int, required=True)
    p.add_argument('--gid', type=int, required=True)
    a = p.parse_args()
    print(render(a.user, a.uid, a.group, a.gid), end='')

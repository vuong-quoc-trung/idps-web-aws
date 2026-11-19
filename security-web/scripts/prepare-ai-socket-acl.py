#!/usr/bin/env python3
"""ExecStartPre helper, run as existing AI service user (never HMAC group).
Only operator installation enables it. Default ACL persists across socket rebinds.
"""
import argparse
import os
from pathlib import Path
import pwd
import stat
import subprocess


def apply(directory, uid):
    directory = Path(directory)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError('RuntimeDirectory must be a real directory owned by AI service user')
    if uid <= 0 or uid == info.st_uid:
        raise ValueError('Distinct non-root NGINX UID required')
    # Keep original group traverse (www-data), grant only named UID traverse/write.
    subprocess.run(['setfacl', '-m', f'u:{uid}:--x,m::--x', str(directory)], check=True)
    subprocess.run(['setfacl', '-m',
        f'd:u::rwx,d:u:{uid}:-w-,d:g::-w-,d:m::-w-,d:o::---', str(directory)], check=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', default='/run/pbl4-ai-shadow')
    p.add_argument('--user', default='websentinel-edge')
    a = p.parse_args()
    apply(a.directory, pwd.getpwnam(a.user).pw_uid)

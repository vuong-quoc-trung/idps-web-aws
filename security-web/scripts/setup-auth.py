#!/usr/bin/env python3
"""Configure a local admin/viewer Argon2 hash without printing the password."""
import argparse
import getpass
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--role', choices=['admin', 'viewer'], default='admin')
parser.add_argument('--username')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
binary = root / 'target/debug/pbl4-security-demo'
if not binary.exists():
    raise SystemExit('Run cargo build in security-web first.')
password = getpass.getpass('New password (at least 12 characters): ')
if password != getpass.getpass('Confirm password: '):
    raise SystemExit('Passwords do not match.')
result = subprocess.run([str(binary), '--hash-password'], input=password, text=True, capture_output=True)
if result.returncode:
    raise SystemExit(result.stderr)
username = args.username or args.role
if not username.isascii() or not username.replace('_', '').replace('-', '').isalnum():
    raise SystemExit('Username must contain ASCII letters, digits, _ or - only.')
path = root / '.env'
text = path.read_text() if path.exists() else (root / '.env.example').read_text()
values = {args.role.upper() + '_USERNAME': username, args.role.upper() + '_PASSWORD_HASH': "'" + result.stdout.strip() + "'"}
lines = []
for line in text.splitlines():
    key = line.split('=', 1)[0]
    if key in values:
        lines.append(key + '=' + values.pop(key))
    else:
        lines.append(line)
lines.extend(key + '=' + value for key, value in values.items())
# Write with restrictive permissions from creation, preserving other settings.
temporary = path.with_suffix('.env-auth-tmp')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as handle:
    handle.write('\n'.join(lines) + '\n')
os.replace(temporary, path)
print(f'Configured {args.role} account {username}. Restart the backend to apply.')

#!/usr/bin/env python3
"""Read-only HTTP smoke test (login/logout mutate only the temporary session)."""
import argparse
import getpass
import json
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:3000')
parser.add_argument('--username', default='admin')
args = parser.parse_args()
base = args.url.rstrip('/')

def call(path, token=None, payload=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(base + path, headers=headers, data=None if payload is None else json.dumps(payload).encode())
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response) if response.status != 204 else None

try:
    call('/api/alerts')
    raise SystemExit('FAIL: anonymous API request was allowed')
except urllib.error.HTTPError as error:
    if error.code != 401:
        raise
print('PASS: anonymous request rejected')
session = call('/api/auth/login', payload={'username': args.username, 'password': getpass.getpass('Password: ')})
token = session['token']
try:
    for path in ['/api/auth/me', '/api/alerts?limit=1', '/api/stats', '/api/rules', '/api/blocked-ips', '/api/audit']:
        call(path, token)
        print('PASS:', path)
    try:
        status = call('/api/ready', token)
        print('PASS: pipeline status', status)
    except urllib.error.HTTPError as error:
        if error.code != 503:
            raise
        print('DEGRADED:', error.read().decode())
finally:
    call('/api/auth/logout', token, {})
try:
    call('/api/alerts', token)
    raise SystemExit('FAIL: logged-out token remains usable')
except urllib.error.HTTPError as error:
    if error.code != 401:
        raise
print('PASS: logout revokes token')

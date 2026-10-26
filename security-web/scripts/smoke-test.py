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

for path in ['/api/alerts', '/api/application-audit']:
    try:
        call(path)
        raise SystemExit('FAIL: anonymous API request was allowed')
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
    print('PASS: anonymous request rejected:', path)
session = call('/api/auth/login', payload={'username': args.username, 'password': getpass.getpass('Password: ')})
token = session['token']
try:
    for path in ['/api/auth/me', '/api/alerts?limit=1', '/api/stats', '/api/rules', '/api/blocked-ips', '/api/audit']:
        call(path, token)
        print('PASS:', path)
    page = call('/api/application-audit?limit=1&offset=0', token)
    assert page['total'] >= len(page['items'])
    assert isinstance(page['collection']['enabled'], bool)
    print('PASS: application audit page and collection metadata')
    if page['items']:
        event = call('/api/application-audit/' + str(page['items'][0]['id']), token)
        assert event['canonical']['schema_version'] == '1.0'
        assert len(event['related']) <= 10
        assert all(r['request_id'] == event['canonical']['request_id'] for r in event['related'])
        print('PASS: application audit detail and request-ID correlation contract')
    else:
        print('SKIPPED: application audit detail (no stored observations)')
    for path, expected in [('/api/application-audit?status_code=999', 400), ('/api/application-audit/9223372036854775807', 404)]:
        try:
            call(path, token)
            raise AssertionError('Invalid audit request was accepted')
        except urllib.error.HTTPError as error:
            assert error.code == expected
    print('PASS: invalid audit filters and missing event')
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

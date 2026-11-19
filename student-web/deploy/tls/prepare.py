#!/usr/bin/env python3
"""Stage HTTPS by extending the existing single-server VM site; never writes /etc."""
import argparse
import ipaddress
from pathlib import Path
import re

TOKEN = re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{};]|[^\s{};\'"]+')

def render(source, cert, key, address):
    ipaddress.IPv4Address(address)
    for path in (cert, key):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path) or '..' in Path(path).parts:
            raise ValueError('Use safe absolute certificate paths')
    tokens = [m for m in TOKEN.finditer(source) if not m.group().startswith('#')]
    servers = [i for i, t in enumerate(tokens[:-1]) if t.group() == 'server' and tokens[i+1].group() == '{']
    if len(servers) != 1:
        raise ValueError('Exactly one server block required; review multi-server site manually')
    if any(t.group() in ('ssl_certificate', 'ssl_certificate_key', 'ssl_protocols', 'include') for t in tokens):
        raise ValueError('Existing TLS/include requires manual review; refusing ambiguous site')
    for i, t in enumerate(tokens):
        if t.group() == 'listen':
            endpoint = tokens[i+1].group()
            if endpoint == '443' or endpoint.endswith(':443'):
                raise ValueError('HTTPS listener already exists')
    if 'http://127.0.0.1:5173' not in source or 'http://127.0.0.1:8080' not in source:
        raise ValueError('Expected frontend/backend upstreams absent')
    point = tokens[servers[0]+1].end()
    addition = f'''\n    # WebSentinel Student TLS: HTTP and all existing routes preserved.
    listen {address}:443 ssl;
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
'''
    return source[:point] + addition + source[point:]

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--ip', default='192.168.20.10')
    p.add_argument('--cert', default='/etc/nginx/student-tls/student.crt')
    p.add_argument('--key', default='/etc/nginx/student-tls/student.key')
    a = p.parse_args()
    target = a.output.resolve()
    if target == a.source.resolve() or Path('/etc') in target.parents:
        p.error('Output must be a NEW staging file outside /etc and distinct from source')
    text = render(a.source.read_text(), a.cert, a.key, a.ip)
    with a.output.open('x') as f: f.write(text)
    print('Staged only; existing routing/headers unchanged. Review and nginx -t before reload.')

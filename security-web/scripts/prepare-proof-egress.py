#!/usr/bin/env python3
"""Stage proof-enabled NGINX candidate only. No keys generated; no runtime writes.
Not a production-readiness assertion: lifecycle and shadow ingest remain gated.
"""
import argparse
import importlib.util
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('host', HERE / 'prepare-nginx-host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
MARKER = '# PBL4 TRANSACTION PROOF CANDIDATE v1'


def render(cert, key, ca, name, js, keyfile, gid, ai_mode="enabled", shadow_socket=None, *,
           edge_ip="192.168.10.1", student_ip="192.168.20.10"):
    if ai_mode not in ('enabled', 'deferred'):
        raise ValueError('Unknown AI telemetry mode')
    for value in (cert, key, ca, js, keyfile): host.certificate_path(value)
    if not isinstance(gid, int) or gid <= 0:
        raise ValueError('Dedicated non-root worker group required')
    site, formats = host.render(host=edge_ip, upstream=student_ip, tls_cert=cert, tls_key=key,
                               egress=host.egress_options(ca, name, 443))
    site = site.replace('proxy_pass http://127.77.0.2:18080;',
                        'proxy_pass http://pbl4_proof_egress;')
    site = site.replace('proxy_set_header Host $host;',
                        'proxy_set_header Connection "";\n    proxy_set_header Host $host;')
    formats += '\nupstream pbl4_proof_egress { server 127.77.0.2:18080; keepalive 16; keepalive_timeout 2s; }\n'
    # Contract binds the original Host, including a port if supplied.
    site = site.replace('proxy_set_header Host $host;', 'proxy_set_header Host $http_host;')
    edge = 'proxy_set_header X-Request-Id $request_id;'
    assert site.count(edge) == 1
    site = site.replace(edge, edge + '\n    proxy_set_header X-WS-Proof $probe_signed;\n'
        '    proxy_set_header X-WS-Receipt "";\n    proxy_hide_header X-WS-Receipt;\n'
        '    proxy_hide_header X-WS-Proof;')
    location = 'location / {\n        proxy_pass https://'
    assert site.count(location) == 1
    site = site.replace(location, 'location / {\n'
        '        if ($probe_verified != ok) { return 403; }\n'
        '        add_header X-WS-Receipt $probe_receipt always;\n'
        '        proxy_set_header X-WS-Proof "";\n'
        '        proxy_set_header X-WS-Receipt "";\n'
        '        proxy_hide_header X-WS-Receipt;\n'
        '        proxy_pass https://')
    site = site.replace('server_name _;', f'server_name _;\n    set $probe_key_file {keyfile};')
    formats += (f'\njs_import proof from {js};\n'
                'js_shared_dict_zone zone=nonces:1m timeout=65s;\n'
                f'js_var $probe_key_gid {gid};\njs_var $probe_receipt;\n'
                'js_set $probe_signed proof.sign;\njs_set $probe_verified proof.verify;\n')
    if shadow_socket is not None:
        if ai_mode != "enabled" or not re.fullmatch(r"/[A-Za-z0-9_./-]+", shadow_socket):
            raise ValueError("Shadow requires enabled telemetry and an absolute Unix socket path")
        if ".." in Path(shadow_socket).parts or len(shadow_socket.encode()) >= 108:
            raise ValueError("Invalid shadow socket path")
        marker = "    location / {\n        proxy_bind 127.77.0.1;"
        if site.count(marker) != 1:
            raise ValueError("Cannot identify the unique edge location")
        mirror = (HERE.parent / "nginx/https-shadow-mirror.conf").read_text().replace("__SOCKET__", shadow_socket)
        site = site.replace(marker, mirror + "    location / {\n"
            "        set $r35_id $request_id;\n        set $r35_method $request_method;\n"
            "        set $r35_target $request_uri;\n        set $r35_dispatch $msec;\n"
            "        mirror /_idps_https_projection;\n        mirror_request_body off;\n"
            "        proxy_bind 127.77.0.1;")
        formats += '\nmap "$scheme:$request_uri" $r35_api { default 0; ~^https:/api/ 1; }\n'
    if ai_mode == 'deferred':
        lines = site.splitlines()
        matched = [i for i, line in enumerate(lines) if 'access_log syslog:' in line and 'tag=ai_shadow' in line]
        if len(matched) != 1:
            raise ValueError('Expected exactly one AI telemetry sink')
        i = matched[0]
        lines[i] = '    # AI DEFERRED: restore via --ai-mode enabled after acceptance.\n    # ' + lines[i].strip()
        site = '\n'.join(lines) + '\n'
    return MARKER + '\n' + site, formats


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('cert', 'key', 'ca', 'tls-name', 'js', 'keyfile'):
        p.add_argument('--' + flag, required=True)
    p.add_argument('--ai-mode', choices=['enabled', 'deferred'], default='enabled')
    p.add_argument('--shadow-socket', help='Optional private HTTPS research receiver Unix socket')
    p.add_argument('--gid', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output == Path('/etc') or Path('/etc') in output.parents:
        p.error('Staging must be outside /etc')
    site, formats = render(a.cert, a.key, a.ca, a.tls_name, a.js, a.keyfile, a.gid, a.ai_mode, a.shadow_socket)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    (output / 'pbl4-proxy').write_text(site)
    (output / 'pbl4-http.conf').write_text(formats)
    (output / 'proof.js').write_text((HERE.parent / 'tests/njs/proof-probe.js').read_text())
    (output / 'readiness.json').write_text(json.dumps({
        'stage': 'REVIEW_ONLY', 'apply_allowed': False, 'runtime_verified': False,
        'gates': ['Defender TLS verification', 'njs package and UID isolation',
                  'key rotation lifecycle and guard readiness', 'Lua output lifecycle',
                  'Rust Shadow ingestion not implemented', 'staged nginx syntax/runtime acceptance']}, indent=2))
    print('Prepared review-only candidate. No module/key/account installed; no runtime changes.')

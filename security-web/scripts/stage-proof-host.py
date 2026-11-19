#!/usr/bin/env python3
"""Build reviewable deployment bundle outside /etc; no secrets generated or services contacted."""
import argparse
import hashlib
import glob
import importlib.util
import json
from pathlib import Path
import re
import yaml

HERE = Path(__file__).resolve().parent

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--nginx-base', type=Path, default=Path('/etc/nginx/nginx.conf'))
    p.add_argument('--suricata-base', type=Path, required=True)
    p.add_argument('--student-ca', type=Path, required=True)
    p.add_argument('--edge-ca', type=Path, required=True)
    p.add_argument('--edge-cert', required=True)
    p.add_argument('--edge-key', required=True)
    p.add_argument('--module', required=True, help='Reviewed installed module path; does not install module')
    p.add_argument('--ai-mode', choices=['enabled', 'deferred'], default='enabled')
    p.add_argument('--https-ml-shadow', action='store_true', help='Stage the optional private HTTPS URI100 mirror')
    p.add_argument('--gid', type=int, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output == Path('/etc') or Path('/etc') in output.parents:
        p.error('Stage outside /etc')
    renderer = load('candidate_stage', 'prepare-proof-egress.py')
    for value in (a.edge_cert, a.edge_key, a.module):
        renderer.host.certificate_path(value)
    main_conf = a.nginx_base.read_text()
    main_conf, count = re.subn(r'(?m)^\s*user\s+[^;]+;', 'user websentinel-edge websentinel-edge;', main_conf)
    if count != 1:
        p.error('Review main-context user directive manually; expected exactly one')
    # Freeze module includes into the candidate; never load njs twice.
    def modules_include(match):
        return ''.join(Path(path).read_text() + '\n' for path in sorted(glob.glob(match[1])))
    main_conf = re.sub(r'(?m)^\s*include\s+(/etc/nginx/modules-enabled/[^;]+);', modules_include, main_conf)
    njs = re.findall(r'(?m)^\s*load_module\s+[^;]*ngx_http_js_module\.so;', main_conf)
    if len(njs) > 1:
        p.error('Duplicate njs modules in base configuration')
    if njs:
        main_conf = main_conf.replace(njs[0], f'load_module {a.module};')
    else:
        main_conf = f'load_module {a.module};\n' + main_conf
    directives = []
    for kind in ('client_body', 'proxy', 'fastcgi', 'scgi', 'uwsgi'):
        directive = f'{kind}_temp_path /var/lib/websentinel-nginx/{kind};'
        if re.search(r'(?m)^\s*' + kind + r'_temp_path\s', main_conf):
            p.error('Existing explicit temp directive requires manual review')
        directives.append(directive)
    main_conf, count = re.subn(r'(?m)^\s*http\s*{', lambda _: 'http {\n    ' + '\n    '.join(directives), main_conf)
    if count != 1:
        p.error('Expected exactly one http context')
    site, formats = renderer.render(a.edge_cert, a.edge_key,
        '/etc/nginx/pbl4-proof/student-ca.crt', 'student.lab',
        '/etc/nginx/pbl4-proof/proof.js', '/etc/nginx/pbl4-proof/key.json', a.gid, a.ai_mode,
        "/run/websentinel-edge-shadow/receiver.sock" if a.https_ml_shadow else None)
    suri = load('suri_stage', 'prepare-suricata-post-proxy.py').render(
        yaml.safe_load(a.suricata_base.read_text()), 'local-egress')
    suri['outputs'] = [entry for entry in suri.get('outputs', []) if 'lua' not in entry]
    suri['outputs'].append({'lua': {'enabled': True, 'scripts-dir': '/etc/suricata/pbl4',
                                   'scripts': ['transaction-evidence.lua']}})
    output.mkdir(mode=0o700, exist_ok=False)
    files = {'transaction-evidence.lua': (HERE.parent/'config/suricata/transaction-evidence.lua').read_text(), 'nginx.conf': main_conf, 'site': site, 'formats': formats,
        'proof.js': (HERE.parent/'tests/njs/proof-probe.js').read_text(),
        'ca.crt': a.student_ca.read_text(),
        'suricata.yaml': '%YAML 1.1\n---\n' + yaml.safe_dump(suri, sort_keys=False),
        'nginx.service.conf': '''[Service]
Type=simple
PIDFile=
ExecStartPre=
ExecStartPost=
ExecStopPost=
ExecStart=
ExecStart=/usr/bin/python3 /usr/local/lib/websentinel/proof-nginx-lifecycle.py
ExecReload=
ExecStop=
KillMode=control-group
TimeoutStopSec=30
Restart=no
LimitCORE=0
UMask=0027
''',
        'suricata.service.conf': '''[Service]
UMask=0077
ExecStart=
ExecStart=/usr/bin/suricata -D --af-packet -c /etc/suricata/pbl4/local-egress.yaml --pidfile /var/run/suricata/suricata.pid
'''}
    for name in ('proof-nginx-lifecycle.py', 'local-egress-guard.py'):
        files[name] = (HERE/name).read_text()
    for name, data in files.items():
        (output/name).write_text(data)
    (output/'edge-ca.crt').write_bytes(a.edge_ca.read_bytes())
    slot_registry = HERE.parents[1]/'ai-training/contracts/https-model-r36/slots.json'
    local_model = None
    if a.https_ml_shadow:
        registry = json.loads(slot_registry.read_bytes())
        selected = registry['slots'][registry['default']]
        local_model = {'registry_sha256': hashlib.sha256(slot_registry.read_bytes()).hexdigest(),
            'version': selected['version'], 'model_sha256': selected['sha256'],
            'mode': 'HTTPS_LOCAL_OBSERVATION_ONLY', 'enforcement': False}
    (output/'manifest.json').write_text(json.dumps({'sha256': {
        name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files},
        'edge_ca_sha256': hashlib.sha256((output/'edge-ca.crt').read_bytes()).hexdigest(),
        'ai_worker': 'DEFERRED' if a.ai_mode == 'deferred' else 'ENABLED_NOT_ACCEPTED',
        'https_local_model': local_model, 'ai_mode': a.ai_mode, 'https_ml_shadow': a.https_ml_shadow, 'verified': False, 'apply_approved': False}, indent=2))
    print('Staged bundle; review effective module/unit/include configuration before apply.')

if __name__ == '__main__': main()

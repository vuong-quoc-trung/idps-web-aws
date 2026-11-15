#!/usr/bin/env python3
"""Stage passive post-proxy configuration. Never install, capture or restart services.
Requires PyYAML. Runtime source is explicit; retain its exact pre-proxy snapshot.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import yaml


def render(base):
    config = copy.deepcopy(base)
    config['af-packet'] = [{'interface': 'vmnet3', 'threads': 1,
                           'cluster-id': 98, 'cluster-type': 'cluster_flow',
                           'defrag': True, 'use-mmap': True,
                           'bpf-filter': 'host 192.168.20.1 and host 192.168.20.10 and tcp port 80'}]
    groups = config['vars']['address-groups']
    groups['HOME_NET'] = '[192.168.20.10/32]'
    groups['HTTP_SERVERS'] = '[192.168.20.10/32]'
    groups['EXTERNAL_NET'] = '!$HOME_NET'
    config.setdefault('stream', {})['inline'] = False
    if isinstance(config.get('firewall'), dict):
        config['firewall']['enabled'] = False
    # Standard EVE destination remains compatible with Rust's existing reader.
    # No second sensor, output directory or daemon is introduced.
    eves = [o['eve-log'] for o in config['outputs'] if 'eve-log' in o and o['eve-log'].get('enabled')]
    if len(eves) != 1:
        raise ValueError('Expected exactly one enabled EVE output; review source configuration')
    eve = eves[0]
    if eve.get('filetype', 'regular') != 'regular' or eve.get('threaded', False):
        raise ValueError('Expected single regular EVE file')
    eve['xff'] = {'enabled': True, 'mode': 'extra-data', 'deployment': 'reverse', 'header': 'X-Forwarded-For'}
    http_found = False
    for entry in eve['types']:
        if isinstance(entry, dict) and 'http' in entry:
            http_found = True
            http = entry['http'] or {}
            # 8.0.3 custom supports fixed header names, not arbitrary X-Request-Id.
            # Never enable dump-all-headers to obtain it: cookies/tokens would leak.
            http['custom'] = []
            http['dump-all-headers'] = 'none'
            entry['http'] = http
        if isinstance(entry, dict) and 'alert' in entry:
            alert = entry['alert'] or {}
            for key in ('payload', 'payload-printable', 'packet', 'http-body', 'http-body-printable'):
                alert[key] = False
            entry['alert'] = alert
    if not http_found:
        raise ValueError('HTTP EVE output required for transaction correlation')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New staging directory outside /etc')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == Path('/etc') or Path('/etc') in output.parents:
        parser.error('Use staging outside /etc')
    raw = args.base.read_bytes()
    base = yaml.safe_load(raw)
    config = render(base)
    rules_dir = Path(base.get('default-rule-path', '/var/lib/suricata/rules'))
    manifest = {'base_sha256': hashlib.sha256(raw).hexdigest(), 'rules': [],
                'mode': 'passive; XFF is evidence only, NOT verified client attribution'}
    for rule in base.get('rule-files', []):
        path = Path(rule) if Path(rule).is_absolute() else rules_dir / rule
        manifest['rules'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if not manifest['rules']:
        parser.error('No rules configured')
    config['rule-files'] = [r['path'] for r in manifest['rules']]
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output / 'pre-proxy.yaml').write_bytes(raw)
    (output / 'post-proxy.yaml').write_text('%YAML 1.1\n---\n' + yaml.safe_dump(config, sort_keys=False))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (output / 'post-proxy.conf').write_text('''[Service]
ExecStart=
ExecStart=/usr/bin/suricata -D --af-packet -c /etc/suricata/pbl4/post-proxy.yaml --pidfile /var/run/suricata/suricata.pid
''')
    print(f'Staged {output}. No service changed. Review manifest, disable enforcement and run -T before switching.')

if __name__ == '__main__':
    main()

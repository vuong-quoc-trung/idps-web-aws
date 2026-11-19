#!/usr/bin/env python3
"""Prepare/check a generation-only bundle. Never install or restart anything."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DROPIN = '/etc/systemd/system/suricata.service.d/99-pbl4-local-egress.conf'
CONFIG = '/etc/suricata/pbl4/local-egress.yaml'
LUA = '/etc/suricata/pbl4/transaction-evidence.lua'
LAUNCHER = '/usr/local/libexec/websentinel/run-suricata-generation.py'
NEW_UNIT = '/etc/systemd/system/suricata.service.d/zz-websentinel-generation.conf'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def stage(out):
    assert not out.exists(), 'Use a fresh output directory'
    config = yaml.safe_load(Path(CONFIG).read_text())
    lua = next(x['lua'] for x in config['outputs'] if 'lua' in x)
    assert lua.get('enabled') is True
    assert lua['scripts-dir'] == '/etc/suricata/pbl4'
    assert 'transaction-evidence.lua' in lua['scripts']
    text = Path(DROPIN).read_text()
    expected = '/usr/bin/suricata -D --af-packet -c '+CONFIG+' --pidfile /var/run/suricata/suricata.pid'
    assert 'ExecStart='+expected in text, 'Unknown ExecStart; review manually'
    assert not Path(NEW_UNIT).exists(), 'Existing generation override; review before staging'
    assert all(p.name < Path(NEW_UNIT).name for p in Path(DROPIN).parent.glob('*.conf')), 'Later drop-in must be reviewed'
    paths = [Path(CONFIG), Path(LUA), *Path('/etc/systemd/system/suricata.service.d').glob('*.conf')]
    for base in ('/etc/systemd/system/suricata.service', '/usr/lib/systemd/system/suricata.service',
                 '/lib/systemd/system/suricata.service'):
        if Path(base).exists(): paths.append(Path(base))
    out.mkdir(mode=0o700)
    shutil.copyfile(HERE/'run-suricata-generation.py', out/'run-suricata-generation.py')
    shutil.copyfile(ROOT/'config/suricata/transaction-evidence.lua', out/'transaction-evidence.lua')
    (out/'zz-websentinel-generation.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 '+LAUNCHER+' '+expected.split(' ',1)[1]+'\n')
    manifest = {'baseline': {str(p): digest(p) for p in paths},
                'dropins': sorted(str(p) for p in Path(DROPIN).parent.glob('*.conf')),
                'payload': {p.name: digest(p) for p in out.iterdir()},
                'new_unit': NEW_UNIT, 'runtime_verified': False}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('STAGED: disk snapshot only; effective systemd command still requires operator review')

def check(out):
    manifest = json.loads((out/'manifest.json').read_text())
    for path, sha in manifest['baseline'].items():
        assert digest(path) == sha, 'Production drift: '+path
    assert sorted(str(p) for p in Path(DROPIN).parent.glob('*.conf')) == manifest['dropins'], 'Drop-in set changed'
    assert not Path(manifest['new_unit']).exists(), 'Generation override already present'
    for name, sha in manifest['payload'].items():
        assert digest(out/name) == sha, 'Payload checksum mismatch: '+name
    print('PASS: payload checksums and disk drift check. DRY-RUN ONLY; no services changed.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'check'])
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    (stage if args.action == 'stage' else check)(args.bundle)

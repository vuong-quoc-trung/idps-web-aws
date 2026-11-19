#!/usr/bin/env python3
"""Operator-only: send one GET; reuse fresh EVE/Lua health checkpoint. No service changes."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--edge-ca', type=Path, required=True)
p.add_argument('--previous-generation', required=True)
a = p.parse_args()
spec = importlib.util.spec_from_file_location('deploy', Path(__file__).with_name('deploy-proof-host.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='ws-generation-health-') as folder:
    bundle = Path(folder)
    shutil.copyfile('/etc/suricata/pbl4/local-egress.yaml', bundle/'suricata.yaml')
    shutil.copyfile(a.edge_ca, bundle/'edge-ca.crt')
    deployment = m.Deployment(bundle, bundle/'unused-backup', m.command, Path('/'))
    deployment.previous_generation = a.previous_generation
    deployment.require_eve_generation = True
    deployment.capture_health()
    print('PASS: fresh HTTPS 401 + EVE/Lua exact flow/tx/request correlation, same new generation; NOT Verified')

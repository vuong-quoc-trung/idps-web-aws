#!/usr/bin/env python3
"""Load njs in temporary nginx -t config. No listener/start/install/reload."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import re
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--module',type=Path,required=True)
a=p.parse_args()
module=a.module.resolve(strict=True)
if not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(module)): p.error('Unsafe path')
with tempfile.TemporaryDirectory(prefix='ws-njs-abi-') as d:
    root=Path(d)
    (root/'probe.js').write_text('import crypto from "crypto"; function probe(r) { return crypto.createHmac("sha256", "test").update("test").digest("hex"); } export default {probe};')
    (root/'nginx.conf').write_text(f'''load_module {module};
pid {root}/nginx.pid;
error_log {root}/error.log;
events {{}}
http {{
 access_log off;
 js_import proof from {root}/probe.js;
 js_shared_dict_zone zone=nonces:1m timeout=65s;
 js_set $probe proof.probe;
}}
''')
    subprocess.run(['/usr/sbin/nginx','-t','-p',str(root)+'/', '-c',str(root/'nginx.conf')],check=True)
print('PASS: module ABI/load, njs import/shared dictionary syntax. No daemon started; HMAC execution tested separately.')

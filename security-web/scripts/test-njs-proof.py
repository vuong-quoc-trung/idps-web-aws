#!/usr/bin/env python3
"""Non-root njs capability tests; reuse disposable TLS Egress fixture. No firewall."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import ssl
import subprocess
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('egress', HERE / 'test-nginx-egress.py')
egress = importlib.util.module_from_spec(spec); spec.loader.exec_module(egress)


class Stack(egress.EgressTests):
    @classmethod
    def config_snippet(cls):
        text = super().config_snippet().replace('proxy_set_header Host $host;', 'proxy_set_header Host $http_host;')
        cls.keyfile = cls.work / 'key.json'
        cls.rotate()
        js = cls.work / 'proof.js'
        js.write_text((HERE.parent / 'tests/njs/proof-probe.js').read_text())
        text = f'js_import proof from {js};\njs_shared_dict_zone zone=nonces:64k timeout=65s;\njs_var $probe_receipt;\njs_var $probe_key_gid;\njs_set $probe_signed proof.sign;\njs_set $probe_verified proof.verify;\n' + text
        text = text.replace('server_name _;', f'server_name _;\n set $probe_key_file {cls.keyfile};')
        text = text.replace('proxy_set_header X-Request-Id $request_id;', 'proxy_set_header X-Request-Id $request_id;\n proxy_set_header X-WS-Proof $probe_signed;\n proxy_set_header X-WS-Receipt "";\n proxy_hide_header X-WS-Receipt;')
        text = text.replace('location / {\n        proxy_pass https://', 'location / {\n if ($probe_verified != ok) { return 403; }\n add_header X-WS-Receipt $probe_receipt always;\n add_header X-Test-Worker $pid always;\n proxy_set_header X-WS-Proof "";\n proxy_set_header X-WS-Receipt "";\n proxy_pass https://')
        return text
    @classmethod
    def rotate(cls):
        cls.material = {'kid': 'lab-key-1', 'epoch': secrets.token_hex(16), 'key': secrets.token_hex(32)}
        cls.key_history = getattr(cls, 'key_history', []) + [cls.material['key']]
        temp = cls.work / 'key.new'
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f: json.dump(cls.material, f)
        temp.replace(cls.keyfile)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--proof-chain', action='store_true', help='Offline Suricata/Rust bridge using actual njs receipts')
    args = parser.parse_args()
    module = args.module.resolve()
    if not module.is_file(): parser.error('Extracted HTTP njs module required')
    original_write, original_popen = Path.write_text, subprocess.Popen
    def write(path, text, *a, **kw):
        if path.name == 'nginx.conf': text = f'load_module {module};\nworker_processes 4;\n' + text.replace('error_log /dev/null crit;', f'error_log {path.parent}/probe.log warn;')
        return original_write(path, text, *a, **kw)
    def popen(command, *a, **kw):
        if Path(command[0]).name == 'nginx': command = [s.replace('master_process off;', 'master_process on;') for s in command]
        return original_popen(command, *a, **kw)
    with patch.object(Path, 'write_text', write), patch.object(subprocess, 'Popen', popen): Stack.setUpClass()
    def proof(nonce=None, age=0):
        now = int(time.time()*1000)-age
        p = [1, Stack.material['kid'], Stack.material['epoch'], nonce or secrets.token_hex(16), '192.0.2.10', 'a'*32, 'GET', 'https', 'lab', hashlib.sha256(b'/api/probe').hexdigest(), now, now+60000]
        body = base64.urlsafe_b64encode(json.dumps(p,separators=(',',':')).encode()).decode().rstrip('=')
        return body + '.' + hmac.new(bytes.fromhex(Stack.material['key']), ('ws-request-v1:'+body).encode(), hashlib.sha256).hexdigest()

    def direct(token=None, connection=None, overrides=None):
        c = connection or http.client.HTTPConnection('127.77.0.2', Stack.egress_port, source_address=('127.77.0.1',0),timeout=3)
        headers = {'Host':'lab', 'X-Real-IP':'192.0.2.10', 'X-Request-Id':'a'*32, 'X-Forwarded-For':'192.0.2.10','X-Forwarded-Proto':'https'}
        if token is not None: headers['X-WS-Proof'] = token
        if overrides: headers.update(overrides)
        c.request('GET','/api/probe',headers=headers)
        r=c.getresponse(); r.read(); result=(r.status,r.getheader('X-WS-Receipt'),r.getheader('X-Test-Worker'))
        if not connection: c.close()
        return result
    def check(name, condition):
        assert condition, name
        print('PASS:', name, flush=True)
    def wait_ready():
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            try: direct(); return
            except OSError: time.sleep(.05)
        raise RuntimeError('NGINX startup timed out')
    def stop(crash=False):
        if crash:
            children=Path(f'/proc/{Stack.process.pid}/task/{Stack.process.pid}/children').read_text().split()
            Stack.process.kill(); Stack.process.wait(timeout=5)
            for pid in children:
                try: os.kill(int(pid),signal.SIGKILL)
                except ProcessLookupError: pass
        else:
            Stack.process.terminate(); Stack.process.wait(timeout=5)
    def start():
        Stack.process = popen(Stack.command+['-g','daemon off; master_process on;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        wait_ready()
    try:
        # Negative security control: mode 0600 does not isolate same-UID processes.
        same_uid = subprocess.run([os.sys.executable, '-c',
            "import pathlib,sys;sys.exit(0 if pathlib.Path(sys.argv[1]).read_bytes() else 1)",
            str(Stack.keyfile)], capture_output=True)
        check('negative control: same UID can read key (isolation NOT achieved)', same_uid.returncode == 0)
        token=proof(); good=direct(token)
        check('HMAC Python->njs and receipt MAC', good[0]==204 and good[1].split('.')[1]==hmac.new(bytes.fromhex(Stack.material['key']),('ws-receipt-v1:'+good[1].split('.')[0]).encode(),hashlib.sha256).hexdigest())
        check('nonce replay rejected', direct(token)[0]==403)
        for name,t in [('missing',None),('expired',proof(age=120000)),('bad_mac',proof()[:-64]+'0'*64)]:
            before=len(Stack.upstream_headers); r=direct(t)
            check(name+' no receipt/no upstream',r[:2]==(403,None) and len(Stack.upstream_headers)==before)
        for field in ('X-Forwarded-For','X-Request-Id','Host'):
            before=len(Stack.upstream_headers)
            check('tampered '+field,direct(proof(),overrides={field:'b'*32 if field=='X-Request-Id' else 'forged'})[:2]==(403,None) and len(Stack.upstream_headers)==before)
        token=proof()
        with ThreadPoolExecutor(max_workers=16) as pool: rows=list(pool.map(lambda _: direct(token),range(64)))
        check('concurrent same nonce accepted exactly once',sum(r[0]==204 for r in rows)==1)
        c=http.client.HTTPConnection('127.77.0.2',Stack.egress_port,source_address=('127.77.0.1',0),timeout=3)
        token=proof(); check('keepalive replay',direct(token,c)[0]==204 and direct(token,c)[0]==403); c.close()
        with ThreadPoolExecutor(max_workers=16) as pool: rows=list(pool.map(lambda _:direct(proof()),range(64)))
        check('distinct concurrent requests',all(r[0]==204 for r in rows))
        check('multiple worker PIDs exercised',len({r[2] for r in rows})>1)
        check('proof stripped before TLS mock upstream',all('X-WS-Proof' not in h and 'X-WS-Receipt' not in h for h in Stack.upstream_headers))
        c=http.client.HTTPSConnection('127.0.0.1',Stack.tls_port,context=ssl.create_default_context(cafile=str(Stack.cert)),timeout=3)
        c.request('GET','/api/probe',headers={'X-WS-Proof':'client-forgery'})
        r=c.getresponse(); r.read(); check('Edge njs signing and receipt hidden from client',r.status==204 and r.getheader('X-WS-Receipt') is None);c.close()
        if args.proof_chain:
            pairs=[]
            for _ in range(64):
                p=proof(); result=direct(p);assert result[0]==204;pairs.append((p,result[1]))
            bridge=egress.load('bridge','proof-chain-offline.py')
            bridge.verify(Stack.work,Stack.material,pairs)
        token=proof();check('pre-reload accepted',direct(token)[0]==204)
        Stack.process.send_signal(signal.SIGHUP);time.sleep(.4)
        check('reload retains replay rejection',direct(token)[0]==403)
        stop();start()
        check('negative control: restart without rotation loses nonce memory',direct(token)[0]==204)
        stop();Stack.rotate();start()
        check('restart rotates epoch rejects old proof',direct(token)[0]==403 and direct(proof())[0]==204)
        token=proof();check('pre-crash accepted',direct(token)[0]==204)
        stop(True);Stack.rotate();start()
        check('master/workers crash recovery rotates epoch',direct(token)[0]==403 and direct(proof())[0]==204)
        Stack.keyfile.chmod(0o644); check('unsafe key permissions fail closed',direct(proof())[0]==403);Stack.keyfile.chmod(0o600)
        saved=Stack.keyfile.with_suffix('.saved');Stack.keyfile.rename(saved)
        check('missing key fails closed',direct(proof())[:2]==(403,None));saved.rename(Stack.keyfile)
        denied=False
        for _ in range(1500):
            if direct(proof())[0]==403: denied=True;break
        check('dictionary full fails closed without eviction',denied)
        check('full dictionary remains closed',direct(proof())[:2]==(403,None))
        logs=''.join(p.read_text(errors='replace') for p in Stack.work.glob('*.log'))
        check('current key absent from logs',all(key not in logs for key in Stack.key_history) and all(key not in json.dumps(Stack.upstream_headers) for key in Stack.key_history))
        print('No nftables installed or modified; GET-only test fixture, not production proof format.')
    finally:
        Stack.tearDownClass()

if __name__=='__main__': main()

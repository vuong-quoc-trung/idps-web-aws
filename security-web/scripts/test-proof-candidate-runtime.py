#!/usr/bin/env python3
"""Actual candidate renderer with temporary NGINX/njs and TLS mock, no sudo."""
import argparse
import http.client
import importlib.util
from pathlib import Path
import ssl
import subprocess
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE/file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

njs = load('njs', 'test-njs-proof.py')
candidate = load('candidate', 'prepare-proof-egress.py')

class Stack(njs.Stack):
    tls_name = 'student.test'
    wrong_ca = False
    ai_mode = "enabled"
    @classmethod
    def config_snippet(cls):
        # Reuse certificate, TLS mock setup and ephemeral port reservation only.
        njs.egress.EgressTests.config_snippet.__func__(cls)
        cls.keyfile = cls.work/'key.json'; cls.rotate()
        js = cls.work/'proof.js'
        js.write_text((HERE.parent/'tests/njs/proof-probe.js').read_text())
        ca = cls.cert
        if cls.wrong_ca:
            ca=cls.work/'wrong-ca.crt'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-noenc','-days','1',
                '-subj','/CN=Unrelated CA','-keyout',str(cls.work/'wrong-ca.key'),'-out',str(ca)],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        site, formats = candidate.render(str(cls.cert), str(cls.work/'upstream.key'),
            str(ca), cls.tls_name, str(js), str(cls.keyfile), 991, cls.ai_mode)
        # Root-owned managed-group keys require privileged acceptance separately.
        formats = formats.replace('js_var $probe_key_gid 991;', 'js_var $probe_key_gid;')
        site = site.replace('192.168.10.1:80;', f'127.0.0.1:{cls.port};')
        site = site.replace('192.168.10.1:443 ssl;', f'127.0.0.1:{cls.tls_port} ssl;')
        site = site.replace('192.168.20.10:443;', f'127.0.0.1:{cls.upstream.server_port};')
        site = site.replace('127.77.0.2:18080', f'127.77.0.2:{cls.egress_port}')
        formats = formats.replace('127.77.0.2:18080', f'127.77.0.2:{cls.egress_port}')
        site = site.replace('syslog:server=unix:/run/pbl4-ai-shadow/nginx.sock,tag=ai_shadow,nohostname', str(cls.work/'telemetry.log'))
        return formats+'\n'+site

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--module',type=Path,required=True)
    p.add_argument('--ai-mode', choices=['enabled','deferred'], default='enabled')
    args=p.parse_args();Stack.ai_mode=args.ai_mode;module=args.module.resolve(strict=True)
    original=Path.write_text
    def write(path,text,*a,**kw):
        if path.name=='nginx.conf': text=f'load_module {module};\n'+text
        return original(path,text,*a,**kw)
    for mode in ('valid', 'wrong_name', 'wrong_ca'):
        wrong = mode != 'valid'
        Stack.wrong_ca = mode == 'wrong_ca'
        Stack.tls_name='wrong.test' if mode == 'wrong_name' else 'student.test'
        with patch.object(Path,'write_text',write): Stack.setUpClass()
        try:
            def request(tls=True, path='/api/probe', method='GET', body=None):
                c=(http.client.HTTPSConnection('127.0.0.1',Stack.tls_port,
                   context=ssl.create_default_context(cafile=str(Stack.cert)),timeout=5) if tls else
                   http.client.HTTPConnection('127.0.0.1',Stack.port,timeout=5))
                c.request(method,path,body=body,headers={'X-WS-Proof':'fake','X-WS-Receipt':'fake',
                    'X-Forwarded-For':'192.0.2.99','X-Request-Id':'b'*32})
                r=c.getresponse();r.read();status=r.status
                assert r.getheader('X-WS-Receipt') is None and r.getheader('X-WS-Proof') is None
                rid=r.getheader('X-Request-Id');c.close()
                return status,rid
            if wrong:
                assert request()[0]==502
                assert not Stack.upstream_headers
                print('PASS: candidate upstream '+mode+' rejected')
                continue
            for tls in (True,False):
                status,rid=request(tls)
                assert status==204 and rid!='b'*32
                h=Stack.upstream_headers[-1]
                assert h['X-Request-Id']==rid and h['X-Forwarded-For']=='127.0.0.1'
                assert h['X-Forwarded-Proto']==('https' if tls else 'http')
                assert not any(k.lower() in ('x-ws-proof','x-ws-receipt') for k in h)
            if Stack.ai_mode == 'enabled':
                assert len((Stack.work/'telemetry.log').read_text().splitlines())==2
            else:
                assert not (Stack.work/'telemetry.log').exists()
            print('PASS: HTTP/HTTPS, identity, no proof leak; AI mode='+Stack.ai_mode)
            c=http.client.HTTPConnection('127.77.0.2',Stack.egress_port,source_address=('127.77.0.1',0),timeout=5)
            c.request('GET','/api/probe',headers={'X-Request-Id':'b'*32,'X-Forwarded-For':'192.0.2.99','X-Forwarded-Proto':'https'})
            r=c.getresponse();r.read();assert r.status==403;c.close()
            assert len(Stack.upstream_headers)==2
            print('PASS: direct egress missing proof denied before mock')
            assert request(path='/.env')[0]==403
            assert request(method='TRACE')[0]==405
            assert request(method='POST',body='x'*(1024*1024+1))[0]==413
            print('PASS: sensitive path, method and body protection preserved')
            outcomes=[request(path='/api/probe?burst='+str(i))[0] for i in range(65)]
            assert 429 in outcomes
            print('PASS: candidate bounded burst triggers rate limiting')
            import time
            time.sleep(2.2)
            Stack.keyfile.unlink()
            before=len(Stack.upstream_headers)
            status,_=request()
            assert status in (403,500,502,503) and len(Stack.upstream_headers)==before, status
            print('PASS: missing HMAC key fails closed')
        finally: Stack.tearDownClass()

if __name__=='__main__': main()

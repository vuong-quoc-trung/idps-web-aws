#!/usr/bin/env python3
"""Operator-run disposable PostgreSQL 17 test. Never consumes caller DATABASE_URL.
Requires preinstalled Docker image; no sudo, pull, host volumes or production DB.
"""
import json
import argparse
import re
import os
from pathlib import Path
import secrets
import subprocess
import time

HERE=Path(__file__).resolve().parent

def run(args, **kwargs):
    r=subprocess.run(args,capture_output=True,timeout=240,**kwargs)
    if r.returncode:
        if args[0]=='cargo':
            diagnostic=(r.stdout+r.stderr).decode(errors='replace')
            diagnostic=re.sub(r'postgres(?:ql)?://[^\s\"]+', '[DB_URL_REDACTED]', diagnostic)
            print(diagnostic[-6000:],flush=True)
        # Do not echo argv/env: they may contain disposable password.
        raise RuntimeError('Isolated test command failed: '+args[0]+'; output withheld')
    return r.stdout

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--c2', action='store_true', help='Run only controlled prevention isolated DB tests')
    parser.add_argument('--c2-regression',action='store_true',help='Run complete Rust regression against disposable PostgreSQL')
    args=parser.parse_args()
    image='postgres:17-alpine'
    run(['docker','image','inspect',image])  # No network pull or fallback to production.
    name='ws-lua-pg-test-'+secrets.token_hex(6)
    password=secrets.token_hex(24)
    created=False
    try:
        run(['docker','run','--pull=never','--detach','--rm','--name',name,
             '--label','websentinel.disposable=lua-shadow-test','--memory','512m','--cpus','2',
             '--tmpfs','/var/lib/postgresql/data:rw,noexec,nosuid,size=384m',
             '-p','127.0.0.1::5432','-e','POSTGRES_PASSWORD='+password,image])
        created=True
        for _ in range(60):
            r=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True)
            if r.returncode==0: break
            time.sleep(.5)
        else: raise RuntimeError('Isolated PostgreSQL did not become ready')
        port=run(['docker','port',name,'5432/tcp']).decode().strip()
        if not port.startswith('127.0.0.1:') or not port.split(':')[1].isdigit():
            raise RuntimeError('Unexpected disposable port binding')
        env=dict(os.environ,DATABASE_URL='postgres://postgres:'+password+'@'+port+'/postgres')
        tests=['checkpoint_restart_rotation_partial_and_conflict',
               'lua_shadow_rollback_and_generation_view',
               'rust_idps_database_upgrades_to_ai_without_rewriting_history']
        if args.c2: tests=['c2_', 'c3_', 'ai_verdict_contract::', 'prevention_simulation::']
        if args.c2_regression: tests=['']
        for test in tests:
            run(['cargo','test','--offline','--manifest-path',str(HERE.parent/'Cargo.toml'),test,'--','--nocapture'],env=env)
            print(json.dumps({'test':test,'status':'PASS'}),flush=True)
        if args.c2 or args.c2_regression: return
        # Restore smoke check against schema through 0014 then additive 0015.
        run(['docker','exec',name,'createdb','-U','postgres','restore_source'])
        for migration in sorted((HERE.parent/'migrations').glob('*.sql')):
            run(['docker','exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d','restore_source'],input=migration.read_bytes())
        insert=b"INSERT INTO suricata_lua_shadow(generation,flow_id,tx_id,request_id,record_hash,proof_present,receipt_present,mismatched) VALUES(repeat('a',32),'123',0,'rid','hash',true,true,true);"
        run(['docker','exec','-i',name,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d','restore_source'],input=insert)
        dump=run(['docker','exec',name,'pg_dump','-U','postgres','-Fc','restore_source'])
        run(['docker','exec',name,'createdb','-U','postgres','restored'])
        run(['docker','exec','-i',name,'pg_restore','--exit-on-error','-U','postgres','-d','restored'],input=dump)
        result=run(['docker','exec',name,'psql','-X','-At','-U','postgres','-d','restored','-c',
                    "SELECT count(*) FROM suricata_lua_shadow WHERE mismatched AND generation=repeat('a',32)"]).strip()
        if result!=b'1': raise RuntimeError('Restored conflict history missing')
        print(json.dumps({'test':'pg_dump_restore_schema_and_conflict','status':'PASS'}))
    finally:
        if created:
            subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)

if __name__=='__main__': main()

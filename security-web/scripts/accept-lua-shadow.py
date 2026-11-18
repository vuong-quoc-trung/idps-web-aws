#!/usr/bin/env python3
"""Read-only Stage B acceptance. No traffic to Student, writes, restart or migrations."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

SQL = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='10s';
SELECT json_build_object(
 'database',current_database(),
 'counts',json_build_object('shadow',(SELECT count(*) FROM suricata_lua_shadow),'seen',(SELECT count(*) FROM suricata_lua_seen)),
 'rows',coalesce((SELECT json_agg(x) FROM (SELECT generation,flow_id,tx_id,request_id,record_hash,mismatched,last_seen FROM suricata_lua_shadow ORDER BY last_seen DESC LIMIT 200) x),'[]'::json),
 'alerts',coalesce((SELECT json_agg(x) FROM (SELECT a.id,a.client_ip_verified,l.source_instance,l.flow_id,l.tx_id,l.request_id,s.status,s.client_ip_verified AS shadow_verified,
 CASE WHEN l.source_instance !~ '^suricata-[a-f0-9]{32}$' THEN 'PENDING_GENERATION'
 WHEN l.flow_id IS NULL OR l.tx_id IS NULL THEN 'MISSING_TRANSACTION'
 WHEN e.generation IS NULL THEN 'PENDING_EVIDENCE'
 WHEN e.mismatched OR (l.request_id IS NOT NULL AND l.request_id<>e.request_id) THEN 'MISMATCHED'
 WHEN NOT e.proof_present OR NOT e.receipt_present THEN 'MISSING_PROOF_OR_RECEIPT'
 WHEN e.duplicate_count>0 THEN 'DUPLICATE_SHADOW' ELSE 'MATCHED_SHADOW' END expected,
 (SELECT count(*) FROM firewall_actions f WHERE f.event_id=a.id) AS actions
 FROM security_alerts a JOIN detector_alert_links l ON l.alert_id=a.id
 JOIN suricata_lua_alert_status s ON s.alert_id=a.id
 LEFT JOIN suricata_lua_shadow e ON l.source_instance='suricata-'||e.generation AND l.flow_id=e.flow_id AND l.tx_id=e.tx_id
 WHERE a.source='SURICATA' ORDER BY a.occurred_at DESC LIMIT 200) x),'[]'::json));
ROLLBACK;"""

def tail(path, limit=8*1024*1024):
    with path.open('rb') as f:
        f.seek(max(0,os.fstat(f.fileno()).st_size-limit))
        if f.tell(): f.readline()
        data=f.read(limit)
    return data[:data.rfind(b'\n')+1].splitlines()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',type=int,default=74708)
    p.add_argument('--candidate',type=Path,default=Path('/home/dinh-huynh-nguyen-khang/ws-rust-shadow-20261118-224505/candidate'))
    a=p.parse_args(); results=[]
    def result(test,status,evidence):results.append({'test':test,'status':status,'evidence':evidence})
    env={}
    try:
        proc=Path('/proc')/str(a.pid)
        env=dict(item.split(b'=',1) for item in (proc/'environ').read_bytes().split(b'\0') if b'=' in item)
        same=hashlib.sha256((proc/'exe').read_bytes()).digest()==hashlib.sha256((a.candidate/'pbl4-security-demo').read_bytes()).digest()
        result('Rust Shadow runtime','PASS' if same else 'FAIL',{'pid':a.pid,'candidate_matches':same})
    except OSError: result('Rust Shadow runtime','NOT_VERIFIED','Process unavailable; no environment values printed')
    required={b'AUTO_BLOCK':b'false',b'ENFORCEMENT_MODE':b'OFF',b'SURICATA_TRUSTED_EDGE_CONFIRMED':b'false'}
    flags={k.decode():('MATCH' if env.get(k)==v else 'UNKNOWN' if k not in env else 'MISMATCH') for k,v in required.items()}
    result('Enforcement configuration','FAIL' if 'MISMATCH' in flags.values() else 'NOT_VERIFIED' if 'UNKNOWN' in flags.values() else 'PASS',flags)
    db=None
    try:
        r=subprocess.run(['docker','exec','-i','pbl4-postgres','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','pbl4','-d','pbl4_security'],input=SQL,text=True,capture_output=True,timeout=20)
        if r.returncode: raise ValueError('DB inaccessible')
        db=json.loads(r.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):result('Database checks','NOT_VERIFIED','Read-only query unavailable; raw output suppressed')
    if db:
        result('Lua ingestion → PostgreSQL','PASS' if db['counts']['shadow']>0 and db['counts']['seen']>0 else 'NOT_VERIFIED',db['counts'])
        alerts=db['alerts']; bad=[x for x in alerts if x['status']!=x['expected']]
        statuses={s:sum(x['status']==s for x in alerts) for s in set(x['status'] for x in alerts)}
        result('Shadow status consistency','FAIL' if bad else 'PASS' if alerts else 'NOT_VERIFIED',{'sampled_alerts':len(alerts),'statuses':statuses,'wrong_statuses':len(bad)})
        try:
            gen=Path('/var/log/suricata/proof-generation').read_text().strip()
            assert re.fullmatch('[a-f0-9]{32}',gen)
            rows={(x['generation'],x['flow_id'],str(x['tx_id'])):x for x in db['rows']}
            eve={}
            for line in tail(Path('/var/log/suricata/eve.json')):
                try:e=json.loads(line)
                except ValueError:continue
                if e.get('host')=='ws-generation-'+gen and e.get('event_type') in ('http','alert'):
                    eve[(gen,str(e.get('flow_id')),str(e.get('tx_id')))]=True
            observed=[]
            for line in tail(Path('/var/log/suricata/chain.tsv')):
                f=line.decode('utf-8').rstrip('\r\n').split('\t')
                if len(f)!=9 or f[8]!=gen:continue
                key=(gen,f[0],f[1]); row=rows.get(key)
                if key in eve:observed.append((row is not None,row is not None and row['request_id']==f[5] and row['record_hash']==hashlib.sha256(line.rstrip(b'\r\n')).hexdigest()))
            result('EVE ↔ Lua ↔ PostgreSQL','PASS' if observed and all(y for _,y in observed) else 'NOT_VERIFIED',{'current_generation_transactions':len(observed),'database_exact_matches':sum(y for _,y in observed),'note':'bounded tails/200 DB rows; live ingest lag possible; retry after draining'})
            current=[x for x in alerts if x['source_instance']=='suricata-'+gen]
            result('Client IP Unverified','FAIL' if any(x['client_ip_verified'] or x['shadow_verified'] for x in current) else 'PASS' if current else 'NOT_VERIFIED',{'current_generation_alerts':len(current)})
            result('No linked firewall action','NOT_VERIFIED' if not current or any(x['actions'] for x in current) else 'PASS',{'linked_actions':sum(x['actions'] for x in current),'note':'linked actions may be manual; not a proof of historical firewall absence'})
        except (OSError,ValueError,AssertionError):result('EVE ↔ Lua ↔ PostgreSQL','NOT_VERIFIED','Capture files unavailable or invalid; no raw evidence printed')
    token=''
    if sys.stdin.isatty():token=getpass.getpass('Dashboard read-only Bearer token (hidden; Enter to skip authenticated API): ').strip()
    def api(path):
        req=urllib.request.Request('http://127.0.0.1:3000'+path,headers={'Authorization':'Bearer '+token} if token else {})
        # Fixed loopback endpoint, refuse redirects to avoid credential forwarding.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        with urllib.request.build_opener(NoRedirect).open(req,timeout=5) as r:return json.loads(r.read(2*1024*1024))
    try:
        ready=api('/api/ready'); watchers=ready.get('watchers',{})
        result('System Status API','PASS' if all(watchers.get(k,{}).get('state')=='watching' and watchers.get(k,{}).get('last_success_at') and watchers.get(k,{}).get('last_data_at') for k in ('SURICATA','SURICATA_LUA')) else 'NOT_VERIFIED',{'watchers':{k:{f:watchers.get(k,{}).get(f) for f in ('state','last_success_at','last_data_at')} for k in ('SURICATA','SURICATA_LUA')},'enforcement_off':ready.get('enforcement_mode')=='OFF'})
        if ready.get('enforcement_mode') not in (None,'OFF'):result('API Enforcement OFF','FAIL','API mode differs from OFF')
    except Exception:result('System Status API','NOT_VERIFIED','Unavailable/unauthorized; raw response suppressed')
    try:
        assert db and db['alerts']
        row=db['alerts'][0]; detail=api('/api/alerts/'+str(row['id'])); shadow=detail.get('lua_shadow') or {}
        result('API ↔ Dashboard data contract','PASS' if shadow.get('status')==row['status'] and shadow.get('client_ip_verified') is False else 'FAIL',{'alert_id':row['id'],'status_matches':shadow.get('status')==row['status']})
    except Exception:result('API ↔ Dashboard data contract','NOT_VERIFIED','No sampled alert or authenticated detail unavailable')
    token='';env.clear()
    result('Dashboard visual rendering','NOT_VERIFIED','API contract only; System Status visual acceptance reported by operator')
    print(json.dumps({'checks':results,'conclusion':'FAIL' if any(x['status']=='FAIL' for x in results) else 'NOT_VERIFIED' if any(x['status']=='NOT_VERIFIED' for x in results if x['test']!='Dashboard visual rendering') else 'PASS (API/data; visual operator acceptance separate)'},indent=2,ensure_ascii=False))
if __name__=='__main__':main()

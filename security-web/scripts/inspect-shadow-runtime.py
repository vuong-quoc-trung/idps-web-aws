#!/usr/bin/env python3
"""Read-only, allowlisted process config and EVE metadata. No credentials/headers."""
import json
from urllib.parse import urlsplit
from pathlib import Path

ALLOWED={'APP_ADDR','SURICATA_EVE_PATH','SURICATA_LUA_PATH','SURICATA_CAPTURE_MODE',
'SURICATA_PROXY_IP','SURICATA_WEB_IP','SURICATA_WEB_PORT','SURICATA_POST_PROXY_INTERFACE',
'SURICATA_TRUSTED_EDGE_CONFIRMED','SURICATA_EVE_GENERATION_HOST','AUTO_BLOCK','ENFORCEMENT_MODE'}
found=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        name=(p/'comm').read_text().strip()
        if 'pbl4-security' not in name:continue
        row={'pid':int(p.name),'name':name,'cgroup':(p/'cgroup').read_text().strip()}
        for label in ('exe','cwd'):
            try: row[label]=str((p/label).resolve(strict=True))
            except OSError: row[label]='UNREADABLE'
        for line in (p/'status').read_text().splitlines():
            if line.startswith('PPid:'): row['parent_pid']=int(line.split()[1])
        try:
            env={}
            for item in (p/'environ').read_bytes().split(b'\0'):
                key,_,value=item.partition(b'=')
                if key == b'DATABASE_URL':
                    try:
                        url=urlsplit(value.decode())
                        row['initial_database_target']={'host':url.hostname,'port':url.port or 5432,'database':url.path.lstrip('/')}
                    except (ValueError,UnicodeError): row['initial_database_target']='UNPARSEABLE_REDACTED'
                if key.decode(errors='replace') in ALLOWED:env[key.decode()]=value.decode(errors='replace')
            row['initial_environment_allowlist']=env
            row['caveat']='proc environment may omit dotenv changes made after exec; absent is unknown'
        except OSError:row['environment']='UNREADABLE'
        found.append(row)
    except OSError:continue
print(json.dumps({'processes':found,'runtime_config':'NOT_FULLY_VERIFIED'},indent=2))
p=Path('/var/log/suricata/eve.json')
try:
    alerts=[]
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-8*1024*1024))
        if f.tell():f.readline()
        for line in f:
            try:e=json.loads(line)
            except ValueError:continue
            if e.get('event_type')!='alert':continue
            alerts.append({k:e.get(k) for k in ('timestamp','flow_id','tx_id','in_iface') } |
                {'sid':e.get('alert',{}).get('signature_id'),'severity':e.get('alert',{}).get('severity')})
    print(json.dumps({'native_alerts_tail_only':alerts[-20:],'database_match':'NOT_VERIFIED'},indent=2))
except OSError:print('{"eve":"UNREADABLE"}')

"""Bridge real njs artifacts through synthetic PCAP and real Suricata to Rust tests.
Not a live capture claim. Key fixture exists only in the caller's private temp dir.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import yaml

HERE=Path(__file__).resolve().parent

def write_lua(work):
    lua=work/'chain.lua'
    lua.write_text((HERE.parent/'config/suricata/transaction-evidence.lua').read_text())


def verify(work, material, pairs):
    spec=importlib.util.spec_from_file_location('support', HERE/'test-transaction-proof-support.py')
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    generation='c'*32
    write_lua(work)
    transactions=[]
    for proof,receipt in pairs:
        req=('GET /api/probe HTTP/1.1\r\nHost: lab\r\nX-Forwarded-For: 192.0.2.10\r\nX-Request-Id: '+'a'*32+'\r\nX-Forwarded-Proto: https\r\nCookie: SECRET_CANARY\r\nX-WS-Proof: '+proof+'\r\n\r\n').encode()
        resp=('HTTP/1.1 204 No Content\r\nX-WS-Receipt: '+receipt+'\r\n\r\n').encode()
        transactions.append((req,resp))
    support.pcap(work/'chain.pcap',transactions)
    cfg=yaml.safe_load(Path('/etc/suricata/suricata.yaml').read_text());cfg.pop('run-as',None)
    cfg.update({'default-log-dir':str(work),'unix-command':{'enabled':False},'stats':{'enabled':False},'rule-files':[], 'outputs':[
        {'eve-log':{'enabled':True,'filetype':'regular','filename':'chain-eve.json','types':[{'http':{'extended':True,'dump-all-headers':'none'}}]}},
        {'lua':{'enabled':True,'scripts-dir':str(work),'scripts':['chain.lua']}}]})
    conf=work/'chain.yaml';conf.write_text('%YAML 1.1\n---\n'+yaml.safe_dump(cfg))
    subprocess.run(['suricata','-c',str(conf),'-r',str(work/'chain.pcap'),'-l',str(work),'-k','none','--runmode','single'],check=True,capture_output=True,timeout=30)
    eve=[json.loads(x) for x in (work/'chain-eve.json').read_text().splitlines() if json.loads(x).get('event_type')=='http']
    lines=(work/'chain.tsv').read_text().splitlines()
    assert len(lines)==len(eve)==len(pairs)
    rows=[];observations=[]
    import base64
    for line in lines:
        flow,tx,proof,receipt,client,rid,scheme,host,generation=line.split('\t')
        event=next(e for e in eve if str(e['flow_id'])==flow and e['tx_id']==int(tx))
        key={'generation':generation,'flow_id':flow,'tx_id':int(tx)}
        rows.append({'tx':key,'proof':proof,'receipt':receipt})
        # Synthetic capture timestamp is unrelated to issuance; this bridge does
        # NOT test clock provenance. Feed known issuance time explicitly.
        issued=json.loads(base64.urlsafe_b64decode(proof.split('.')[0]+'==='))[10]
        observations.append({'response_complete':True,'tx':key,'client':client,'request_id':rid,'scheme':scheme,'host':host,
            'method':event['http']['http_method'],'target_sha256':hashlib.sha256(event['http']['url'].encode()).hexdigest(),'observed_ms':issued})
    assert 'SECRET_CANARY' not in (work/'chain.tsv').read_text()+(work/'chain-eve.json').read_text()
    fixture=work/'rust-proof.json'
    with os.fdopen(os.open(fixture,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        json.dump({'key_hex':material['key'],'kid':material['kid'],'epoch':material['epoch'],'rows':rows,'observations':observations},f)
    env=dict(os.environ,WS_PROOF_TEST_FIXTURE=str(fixture))
    subprocess.run(['cargo','test','--offline','--manifest-path',str(HERE.parent/'Cargo.toml'),'transaction_proof::external_njs_suricata_batch','--','--ignored','--nocapture'],check=True,env=env,timeout=120)
    print(f'PASS: njs artifacts -> synthetic PCAP -> Suricata Lua/EVE -> Rust ({len(rows)} transactions)',flush=True)

#!/usr/bin/env python3
"""Read-only compare snapshots/current JSONL; never print audit payload or secrets."""
import argparse, collections, hashlib, json, pathlib, sys

def read(paths):
    result={};counts=collections.Counter();partial=0
    for path in paths:
        with open(path,'rb') as f:
            for number,line in enumerate(f,1):
                if not line.endswith(b'\n'): partial+=1;continue
                if len(line)>16384:raise ValueError(f'{path}:{number}: oversized line')
                event=json.loads(line)
                if event.get('source')!='STUDENT_AUDIT' or event.get('schema_version')!='1.0':raise ValueError('Unexpected source/schema or envelope')
                key=tuple(event[k] for k in ('source','source_instance','event_id'))
                if not all(isinstance(v,str) and v for v in key) or not event.get('timestamp'):raise ValueError('Missing identity/timestamp')
                digest=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if key in result and result[key]!=digest:raise ValueError('Same ID has conflicting content')
                result[key]=digest;counts[key]+=1
    return result,sum(counts.values())-len(counts),partial

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',nargs='+',required=True);p.add_argument('--destination',nargs='+');a=p.parse_args()
    src,dup,partial=read(a.source);print(f'Source: unique={len(src)} duplicate={dup} incomplete={partial}')
    if partial:sys.exit('Incomplete source line: take a stable snapshot and retry.')
    if a.destination:
        dst,dup,partial=read(a.destination)
        missing=set(src)-set(dst);changed=[k for k in src.keys()&dst.keys() if src[k]!=dst[k]]
        print(f'Destination: unique={len(dst)} duplicate={dup} incomplete={partial}; missing={len(missing)} changed={len(changed)}')
        if missing or changed or partial:sys.exit(1)
        print('PASS: every source identity and full JSON content is preserved; extra destination history is permitted.')
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError) as e:sys.exit(type(e).__name__+': validation failed (payload suppressed)')

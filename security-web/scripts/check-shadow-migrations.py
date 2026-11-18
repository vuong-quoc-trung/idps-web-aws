#!/usr/bin/env python3
"""Offline comparison of ALL SQLx migrations against operator-exported JSON. No DB access."""
import argparse
import hashlib
import json
from pathlib import Path

def compare(rows, directory):
    local={int(p.name.split('_',1)[0]):p for p in directory.glob('*.sql')}
    applied={}
    for row in rows:
        v=int(row['version'])
        if v in applied: raise ValueError('Duplicate migration version')
        applied[v]=row
        if v not in local: raise ValueError(f'Unknown applied migration {v}')
        if row['success'] is not True: raise ValueError(f'Failed migration {v}')
        if row['checksum'] != hashlib.sha384(local[v].read_bytes()).hexdigest():
            raise ValueError(f'Checksum mismatch migration {v}')
    pending=[p.name for v,p in sorted(local.items()) if v not in applied]
    return {'applied_validated':len(applied),'pending':pending,'migration_approval':'REQUIRED' if pending else 'NONE_PENDING'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory',type=Path)
    args=parser.parse_args()
    print(json.dumps(compare(json.loads(args.inventory.read_text()),Path(__file__).resolve().parent.parent/'migrations'),indent=2))

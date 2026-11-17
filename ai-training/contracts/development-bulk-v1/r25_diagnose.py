"""Aggregate-only audit of the missed component; no payload or identity persists."""

import argparse
import json
import os
import secrets
from collections import Counter,defaultdict
from hashlib import blake2s
from pathlib import Path
import numpy as np
import r16_waf as waf
from r18_data import check
from r20_quality import R19,PINS
from r25_probe import SOURCE
from r24_data import census
from r20_calibration import uri76_oracle
from idps_ai.common import atomic_json,file_sha256


def run(out):
    check(file_sha256(R19/"waf-r19.npz")==PINS["waf-r19.npz"],"Source pin")
    with np.load(SOURCE/"publisher-r24-uri100.npz",allow_pickle=False) as d:
        group=d["tune_groups"]==2780;x=d["tune_x"][group];y=d["tune_y"][group]
    with np.load(R19/"waf-r19.npz",allow_pickle=False) as d:
        coordinates=d["tuning_row"][group]
    order=np.argsort(coordinates);coord=coordinates[order]
    key=secrets.token_bytes(32);pairs={};payloads=defaultdict(set);body_lengths=[[],[]];method=Counter();offset=0;count=0
    def opaque(data):return blake2s(data,key=key,digest_size=16).digest()
    for batch in waf.source().iter_batches(batch_size=waf.BATCH,columns=["method","url","label","body","headers"],use_threads=False):
        end=offset+batch.num_rows;lo,hi=np.searchsorted(coord,[offset,end])
        rows=batch.take(coord[lo:hi]-offset).to_pylist() if hi>lo else ()
        for i,row in zip(order[lo:hi],rows,strict=True):
            label=waf.LABEL[row["label"]];check(label==y[i],"Diagnostic label binding")
            target=waf.origin_view(row["url"])[0]
            identity=opaque((row["method"]+"\0"+target).encode())
            pairs[identity]=pairs.get(identity,0)|(1<<label)
            # Opaque digests remain in process memory and are never emitted.
            payload=json.dumps([row["body"],row["headers"]],sort_keys=True).encode()
            payloads[(identity,label)].add(opaque(payload))
            body=row["body"];body_lengths[label].append(len(body.encode()) if isinstance(body,str) else len(json.dumps(body).encode()) if body else 0)
            method[(row["method"],label)]+=1;count+=1
        offset=end
    check(count==len(y),"Diagnostic coordinate coverage")
    mixed={k for k,v in pairs.items() if v==3}
    both_visible_payload=sum(bool(payloads[k,0]&payloads[k,1]) for k in mixed)
    caps={}
    for width in (76,100):
        unique,counts,inv,summary=census(x[:,:width],y)
        caps[str(width)]={"census":summary,"empirical_oracle_at_component_1pct_fpr":uri76_oracle(counts)}
    atomic_json(out/"diagnosis.json",{
        "component":2780,"originals":count,"normal_anomalous":np.bincount(y,minlength=2).tolist(),
        "normalized_method_target_count":len(pairs),"mixed_label_method_targets":len(mixed),
        "mixed_targets_with_identical_body_and_headers_across_labels":both_visible_payload,
        "methods":{m:{str(l):n for (mm,l),n in method.items() if mm==m} for m,_ in method},
        "body_stats_by_label":{str(label):{"nonempty":int(np.count_nonzero(values)),"length_p50_p95":np.percentile(values,[50,95]).tolist()} for label,values in enumerate(body_lengths)},
        "representation":caps,"body_headers_only_diagnostic_not_features":True,
        "label_noise_rate":"UNIDENTIFIABLE_WITHOUT_INDEPENDENT_REVIEW",
        "calibration_limit":"A monotone calibration changes score probabilities and ties, not separability of equal representations.",
        "raw_payloads_or_identity_digests_persisted":False,"protected_roles_read":False,
    })


if __name__=="__main__":
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path);run(p.parse_args().out)

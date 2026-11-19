"""Post-lock comparison only. Embargo complete foreign components that touch any WAF role."""
import argparse
import json
from pathlib import Path

import numpy as np
import onnx

from cohort import BASE, PLAN, bootstrap, collision, errors, load, method, rate_ci, r36
from experiment import originals, rank_at_one_percent


def panel(x,y,g,models):
    rows={}
    for name,(model,t) in models.items():
        p=r36.ort_scores(model,x)
        prob=r36.ort_scores(model,x,"publisher_probability")
        m=r36.stats(y,p,t,prob)
        m["request_binomial_ci"]={"recall":rate_ci(m["tp"],m["tp"]+m["fn"]),
                                  "fpr":rate_ci(m["fp"],m["fp"]+m["tn"])}
        m["lineage_bootstrap_ci"]=bootstrap(y,g,p>t)
        m["ranking_recall_at_1pct_descriptive"]=rank_at_one_percent(y,p)
        m["threshold"]=t
        m["errors"]=errors(x,y,g,p,t)
        m["by_method"]={}
        for verb in ("GET","POST","OTHER"):
            mask=method(x)==verb
            yy,dd=y[mask],p[mask]>t
            tn,fp,fn,tp=[int(np.sum((yy==i)&(dd==j))) for i,j in ((0,0),(0,1),(1,0),(1,1))]
            m["by_method"][verb]=dict(tn=tn,fp=fp,fn=fn,tp=tp,recall=tp/(tp+fn) if tp+fn else None,
                                      fpr=fp/(tn+fp) if tn+fp else None)
        rows[name]=m
    return dict(arms=rows,groups=len(set(g)),collision=collision(x,y))


def run(a):
    lock=json.loads((a.study/"selection.json").read_text())
    for name,pin in lock["files"].items(): r36.checked(a.study/name,pin)
    ref=json.loads((BASE/"slots.json").read_text())["slots"]["candidate"]
    comp=json.loads((a.study/"comparison.json").read_text())
    models={"R36":(onnx.load(r36.checked(BASE/ref["model"],ref["sha256"])),ref["threshold"]),
            "R37":(onnx.load(a.study/"finalist.onnx"),comp["arms"][lock["finalist"]]["threshold"])}
    x,c,_,g,h,tx,*_=load(a.root)
    i,y=originals(c[h])
    result={"selection_sha256":r36.sha(a.study/"selection.json"),"WAF_EXPOSED_HOLDOUT":panel(x[h][i],y,g[h][i],models)}
    used=set(r36.signatures(x))|set(r36.signatures(tx))
    for source,pin in PLAN["transfer_sha256"].items():
        path=a.root/"t09-r32-information-TIu0kTGQ/verified/pilot"/(source+".npz")
        with np.load(r36.checked(path,pin),allow_pickle=False) as z:
            xx,yy,gg,n=z["x"],z["y"],z["group"],int(z["nfit"])
        if set(gg[:n]) & set(gg[n:]): raise ValueError("Foreign role leakage")
        touched={grp for grp,view in zip(gg,r36.signatures(xx),strict=True) if view in used}
        keep=~np.isin(gg,list(touched))
        for role,mask in [("FIT",np.arange(len(yy))<n),("TUNING",np.arange(len(yy))>=n)]:
            valid=keep&mask
            result[source+"_"+role]=dict(embargoed_originals=int((mask&~keep).sum()),
                                         **panel(xx[valid],yy[valid],gg[valid],models))
    r36.dump(a.out,result)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for n in ["root","study","out"]: p.add_argument(n,type=Path)
    run(p.parse_args())

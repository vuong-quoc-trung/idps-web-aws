"""Bounded R37 pilot, full fit, development selection and write-once model lock."""
import argparse
from io import BytesIO
import json
from pathlib import Path

import joblib
import numpy as np
import onnx
from scipy.special import expit, logit
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier

from cohort import BASE, HERE, bootstrap, load, r36

PROTOCOL = HERE / "protocol.json"


def threshold(scores, negative_group, cap=8):
    """Smallest observed strict threshold respecting both empirical negative measures."""
    if not len(scores) or not np.isfinite(scores).all():
        raise ValueError("Missing finite calibration negatives")
    _, inv, counts = np.unique(negative_group,return_inverse=True,return_counts=True)
    weight = np.minimum(1.,cap/counts)[inv]
    levels, bins = np.unique(scores,return_inverse=True)
    raw = np.bincount(bins)
    capped = np.bincount(bins,weights=weight)
    above = lambda w: np.r_[np.cumsum(w[::-1])[-2::-1],0.] if len(w)>1 else np.zeros(1)
    ok = (above(raw) <= len(scores)*.01) & (above(capped) <= weight.sum()*.01+1e-10)
    return float(levels[np.flatnonzero(ok)[0]])


def make_model(arm):
    if arm == "ET":
        return ExtraTreesClassifier(n_estimators=48,max_depth=9,min_samples_leaf=3,
                                    max_features=.8,n_jobs=1,random_state=36)
    return HistGradientBoostingClassifier(max_iter=140,max_leaf_nodes=15,l2_regularization=2.,
                                         learning_rate=.08,early_stopping=False,random_state=36)


def fit(x,c,mass,factor,arm):
    idx,label = np.where(c>0)
    w=mass[idx,label].copy()
    w[label==0] *= factor[idx[label==0]]
    w *= w.sum()/(2*np.bincount(label,weights=w)[label])
    return make_model(arm).fit(x[idx],label,sample_weight=w)


def train(x,c,mass,g,arm):
    factor=np.ones(len(x))
    evidence={}
    if arm=="HGB_HARD":
        folds=r36.buckets(g,"r37-hard-negative",3)
        oof=np.full(len(x),np.nan)
        for k in range(3):
            a,b=folds!=k,folds==k
            teacher=fit(x[a],c[a],mass[a],factor[a],"HGB")
            assert not set(g[a]) & set(g[b])
            oof[b]=teacher.predict_proba(x[b])[:,1]
        if not np.isfinite(oof).all(): raise ValueError("Incomplete OOF mining")
        neg=c[:,0]>0
        cut=float(np.quantile(oof[neg],.9))
        hard=neg & (oof>=cut)
        factor[hard]=4.
        evidence=dict(mining_score_cut=cut,negative_cells=int(neg.sum()),
                      upweighted_cells=int(hard.sum()),upweighted_negative_originals=int(c[hard,0].sum()))
    return fit(x,c,mass,factor,arm),evidence


def originals(c):
    idx,y=np.where(c>0)
    n=c[idx,y].astype(int)
    return np.repeat(idx,n),np.repeat(y,n)


def rank_at_one_percent(y,s):
    neg=np.sort(s[y==0])
    cutoff=neg[-1-len(neg)//100]
    return float(np.mean(s[y==1]>cutoff))


def run_pilot(data):
    x,c,mass,g,h,*_=data
    folds=r36.buckets(g,"r37-pilot",5)
    a=(~h)&(folds<3); b=(~h)&(folds==3); v=(~h)&(folds==4)
    assert not (set(g[a]) & set(g[b]) or set(g[b]) & set(g[v]) or set(g[v]) & set(g[a]))
    roles = {k:dict(originals=c[m].sum(axis=0).tolist(),groups=len(set(g[m])),views=int(m.sum()))
             for k,m in [('fit',a),('cal',b),('val',v)]}
    ib,yb=originals(c[b]); iv,yv=originals(c[v])
    rows={}
    for arm in ("ET","HGB","HGB_HARD"):
        est,info=train(x[a],c[a],mass[a],g[a],arm)
        model=r36.export(est)
        p=r36.ort_scores(model,x[b])[ib]
        t=threshold(p[yb==0],g[b][ib][yb==0])
        scores=r36.ort_scores(model,x[v])[iv]
        rows[arm]=dict(threshold=t,validation=r36.stats(yv,scores,t,scores),
                       best_recall_at_1pct_ranking_only=rank_at_one_percent(yv,scores),mining=info)
    def key(n):
        m=rows[n]["validation"]
        return (max(0,m["fpr"]-.01),-m["recall"],-m["ap"])
    return dict(roles=roles,arms=rows,finalist=min(("HGB","HGB_HARD"),key=key))


def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    binding={k:r36.sha(p) for k,p in dict(protocol=PROTOCOL,runner=Path(__file__),cohort=HERE/"cohort.py",
            r36_study=BASE/"study.py",r36_data_plan=BASE/"plan.json",r36_registry=BASE/"slots.json").items()}
    lock=a.out/"selection.json"
    if lock.exists():
        state=json.loads(lock.read_text())
        if state["binding"]!=binding: raise ValueError("Selection binding changed")
        for name,pin in state["files"].items(): r36.checked(a.out/name,pin)
        print("RESUMED_LOCKED",state["winner"])
        return
    data=load(a.root)
    pilot=a.out/"pilot.json"
    if pilot.exists():
        p=json.loads(pilot.read_text())
        if p["binding"]!=binding: raise ValueError("Pilot binding changed")
    else:
        p=dict(binding=binding,**run_pilot(data))
        r36.dump(pilot,p)
    x,c,mass,g,hold,tx,ty,tg,b=data
    arm=p["finalist"]
    est,mine=train(x[~hold],c[~hold],mass[~hold],g[~hold],arm)
    buf=BytesIO()
    joblib.dump(est,buf,compress=3)
    r36.atomic(a.out/"finalist.joblib",buf.getvalue())
    slots=json.loads((BASE/"slots.json").read_text())["slots"]["candidate"]
    base=onnx.load(r36.checked(BASE/slots["model"],slots["sha256"]))
    raw=r36.export(est)
    s=r36.ort_scores(raw,tx)
    error=float(np.max(np.abs(est.predict_proba(tx)[:,1]-s)))
    if error>2e-5: raise ValueError("Estimator export mismatch")
    f,o,v=b==2,b==3,b<2
    slope,bias=r36.calibrate(s[f],ty[f])
    calibrated=r36.calibrated_model(raw,slope,bias)
    r36.atomic(a.out/"finalist.onnx",calibrated.SerializeToString())
    cp=r36.ort_scores(calibrated,tx,"publisher_probability")
    expected=expit(logit(np.clip(s.astype(float),1e-6,1-1e-6))*slope+bias)
    calerr=float(np.max(np.abs(cp-expected)))
    if calerr>2e-5: raise ValueError("Calibration export mismatch")
    bscore=r36.ort_scores(base,tx)
    bprob=r36.ort_scores(base,tx,"publisher_probability")
    t=threshold(s[o & (ty==0)],tg[o & (ty==0)])
    bt=threshold(bscore[o & (ty==0)],tg[o & (ty==0)])
    rows={}
    for name,score,prob,op in [("R36",bscore,bprob,slots["threshold"]),("ET_CONTROL",bscore,bprob,bt),
                               (arm,s,cp,t)]:
        rows[name]=dict(threshold=op,cal=r36.stats(ty[o],score[o],op,prob[o]),
                        select=r36.stats(ty[v],score[v],op,prob[v]),
                        select_cluster_ci=bootstrap(ty[v],tg[v],score[v]>op),
                        select_rank_recall_at_1pct=rank_at_one_percent(ty[v],score[v]))
    ci=bootstrap(ty[v],tg[v],s[v]>t,bscore[v]>slots["threshold"])
    m=rows[arm]["select"]; ref=rows["R36"]["select"]; ctl=rows["ET_CONTROL"]["select"]
    gates=dict(select_budget=m["fpr"]<=.01,three_point_gain=m["recall"]>=ref["recall"]+.03,
               positive_paired_recall_lower=ci["recall"][0]>0,no_extra_fpr=m["fpr"]<=ref["fpr"],
               comparable_control=m["recall"]>ctl["recall"] or ctl["fpr"]>.01,
               operating_point_has_sensitivity=rows[arm]["cal"]["tp"]>0)
    winner=arm if all(gates.values()) else "R36"
    r36.dump(a.out/"comparison.json",dict(arms=rows,paired_delta_ci=ci,selection_gates=gates,mining=mine,
             finalist=arm,fit_originals=c[~hold].sum(axis=0).tolist(),fit_vectors=int((~hold).sum()),
             slope=slope,bias=bias,estimator_export_error=error,calibration_export_error=calerr))
    r36.dump(lock,dict(binding=binding,winner=winner,finalist=arm,threshold=rows[winner]["threshold"],
                       files={n:r36.sha(a.out/n) for n in ("pilot.json","finalist.onnx","finalist.joblib","comparison.json")}))
    print("LOCKED",winner,arm,gates,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for name in ["root","out"]: parser.add_argument(name,type=Path)
    run(parser.parse_args())

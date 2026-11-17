"""Locked, bounded R25 model comparison on publisher development only."""

import argparse
import os
import time
from pathlib import Path

import joblib
import numpy as np
import onnx
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.export.onnx import graph_for, cpu_session
from idps_ai.training.checkpoint import RunLock, save_checkpoint, load_checkpoint
from r18_data import check, read
from r18_train import WeightedSwiGLU, logistic_onnx
from r16_train import batched_predict
from r20_quality import cpu_benchmark
from r21_quality import R20, R20_ONNX
from r24_pilot import anchor, warm_start, ep
from r24_eval import evaluate
from r25_probe import SOURCE

MAX_EPOCHS = 12


def load(out):
    manifest=read(out/"dataset-manifest.json")
    path=out/"publisher-r25-uri132.npz"
    check(file_sha256(path)==manifest["dataset_sha256"],"R25 dataset binding")
    with np.load(path,allow_pickle=False) as d:
        return {k:d[k] for k in d.files}


def rank(report):
    transfer=report["grouped_threshold_transfer_exposed_tuning"]["0.01"]["aggregate"]
    at=report["matched_fp_tuning_envelope"]["0.01"]["metrics"]["original_request"]
    return (transfer["recall"] if transfer["fpr"]<=.01 else -1.,at["ap"])


def run(out):
    start=time.monotonic();d=load(out)
    x,counts,mass=d["fit_x"],d["fit_counts"],d["fit_cell_mass"]
    tx,ty,groups,context=(d[k] for k in ("tune_x","tune_y","tune_groups","tune_context"))
    ix,y=np.nonzero(counts);cell=mass[ix,y];balance=d["binary_class_weights"]
    weights=cell*balance[y]
    source,sha=anchor()
    plan={
        "role":"PUBLISHER_RESEARCH_TRAINING_NOT_RELEASE",
        "dataset_sha256":file_sha256(out/"publisher-r25-uri132.npz"),
        "dataset_manifest_sha256":file_sha256(out/"dataset-manifest.json"),
        "runner_sha256":file_sha256(__file__),"r19_checkpoint_sha256":sha,
        "fit_originals":int(counts.sum()),"fit_uri100_or_uri132_cells":[None,len(ix)],
        "comparison":["R20","R24_URI100","HGB_URI76","HGB_URI100","HGB_URI132","LOGISTIC_URI132","WARM_SWIGLU_URI100_400256"],
        "tree":{"max_iter":150,"max_leaf_nodes":15,"learning_rate":.05,"l2_regularization":1,"seed":2501},
        "neural":{"epochs":MAX_EPOCHS,"batch_cells":2048,"seed":2401,"lr":.00015,"patience":3,
                  "regularization":source.regularization,"checkpoint_selection":"Grouped transferred TUNING recall at dual 1% FPR, then AP; earlier epoch on ties"},
        "labels":"Original publisher normal/anomalous preserved, both labels retained in mixed vectors",
        "weighting":"R19 parent URI76 capped group mass conserved. No majority relabel or original duplication.",
        "external":"CSIC normal TRAIN and PKDD Valid TRAIN are FPR stress only. Fixed TUNING thresholds before scoring.",
        "independent_evaluation":"No fresh dual-class source available. Historical HOLDOUT, publisher eval/test and native CAL/TEST are unopened.",
        "native_requirement":"Required for promotion, not for authorized publisher research training.",
    }
    path=out/"training-plan.json"
    if path.exists():
        check(read(path)==plan,"Immutable training plan differs")
    else:
        atomic_json(path,plan)
    binding=digest(plan)
    arms={};models={};thresholds={};scores_all={}
    from r20_calibration import threshold
    from r23_pilot import grouped_scores
    def record(name,model,scores,width):
        a=evaluate(tx[:,:width],ty,scores,groups,context)
        truth,values=grouped_scores(tx[:,:width],ty,scores)
        cut=max(threshold(truth,values),threshold(truth,values,True))
        a["frozen_tuning_dual_cutoff"]=cut
        arms[name]=a;thresholds[name]=cut;scores_all[name]=scores
        if model is not None:
            p=out/f"{name}.joblib";joblib.dump(model,p);models[name]={"file":p.name,"sha256":file_sha256(p),"width":width}
    for name,path,width in (("R20",R20/"bundle/swiglu.onnx",76),("R24_URI100",SOURCE/"pilot-uri100.onnx",100)):
        if name=="R20":
            check(file_sha256(path)==R20_ONNX,"R20 model pin")
        record(name,None,cpu_session(path,1).run(["score"],{"input":tx[:,:width]})[0],width)
        models[name]={"onnx":str(path),"sha256":file_sha256(path),"width":width}
    for width in (76,100,132):
        model=HistGradientBoostingClassifier(**{k:v for k,v in plan["tree"].items() if k!="seed"},
            random_state=2501,early_stopping=False).fit(x[ix,:width],y,sample_weight=weights)
        record(f"HGB_URI{width}",model,model.predict_proba(tx[:,:width])[:,1].astype(np.float32),width)
    logistic=LogisticRegression(C=1,max_iter=600,random_state=2501).fit(x[ix],y,sample_weight=weights)
    check(logistic.n_iter_.max()<600,"Logistic convergence")
    record("LOGISTIC_URI132",logistic,logistic.predict_proba(tx)[:,1].astype(np.float32),132)
    # Full 400k-original warm URI100 arm, matched to R24's frozen schema/config.
    # Reuse R24's exact cell masses so lexical refinement never changes its loss.
    with np.load(SOURCE/"publisher-r24-uri100.npz",allow_pickle=False) as old:
        base=old["fit_x"]; c=old["fit_counts"]; m=old["fit_cell_mass"]
    rows,labels=np.nonzero(c);train=base[rows];wm=m[rows,labels]
    batches=int(np.ceil(len(labels)/2048))
    schedule={"scheduler":"warmup_cosine","learning_rate":.00015,"warmup_steps":5,"total_steps":MAX_EPOCHS*batches,"min_lr_ratio":.1}
    root=out/"training/uri100";history=[];epoch=0;best=(-1.,-1.);best_epoch=0
    with RunLock(root):
        if (root/"latest.json").exists():
            saved=load_checkpoint(root);s=saved.state
            check(not saved.used_previous and s["binding"]==binding and saved.model.steps==s["epoch"]*batches,"Resume binding/cursor")
            model=WeightedSwiGLU.from_arrays(saved.model.metadata(),saved.model.arrays())
            epoch=s["epoch"];history=s["history"];best=tuple(s["best"]);best_epoch=s["best_epoch"]
            atomic_json(out/"resumed.json",{"epoch":epoch,"pid":os.getpid(),"binding":binding})
        else:
            model=warm_start(source,100,balance)
        while epoch<MAX_EPOCHS and epoch-best_epoch<3:
            order,loss=ep(model,train,labels,wm,epoch,schedule)
            epoch+=1;scores=batched_predict(model,tx[:,:100])
            report=evaluate(tx[:,:100],ty,scores,groups,context)
            key=rank(report);improved=key>best
            if improved:best=key;best_epoch=epoch
            history.append({"epoch":epoch,"loss":loss,"rank":list(key),"global_step":model.steps})
            save_checkpoint(root,model,{"binding":binding,"epoch":epoch,"history":history,"best":list(best),"best_epoch":best_epoch,"loss":loss},order,is_best=improved)
            atomic_json(out/"progress.json",{"state":"TRAINING","epoch":epoch,"best_epoch":best_epoch,"fit_originals":400000,"elapsed_seconds":time.monotonic()-start})
        pointer=read(root/"best.json");saved=load_checkpoint(root/pointer["path"])
        model=saved.model;np.testing.assert_equal(model.steps,batches*best_epoch)
        graph=out/"swiglu-uri100-r25.onnx";onnx.save(graph_for(model),graph)
        py=batched_predict(model,tx[:,:100]);ort=cpu_session(graph,1).run(["score"],{"input":tx[:,:100]})[0]
        np.testing.assert_allclose(py,ort,rtol=1e-5,atol=1e-6)
        name="WARM_SWIGLU_URI100";record(name,None,ort,100)
        models[name]={"onnx":str(graph),"sha256":file_sha256(graph),"width":100,"checkpoint":pointer,"parameters":sum(v.size for v in model.parameters.values()),"python_onnx_max_abs":float(np.max(np.abs(py-ort))),"history":history}
    chosen=max((k for k in arms if k not in ("R20","R24_URI100")),key=lambda k:rank(arms[k]))
    # Selection is sealed before any external source scores are opened.
    atomic_json(out/"model-selection.json",{"selected_development":chosen,"selection_rank":list(rank(arms[chosen])),"thresholds":thresholds,"models":models,"binding":binding,"native_release_ready":False})
    np.savez_compressed(out/"tuning-scores.npz",**scores_all)
    atomic_json(out/"experiment.json",{"arms":arms,"models":models,"selected_development":chosen,"seconds":time.monotonic()-start})


if __name__=="__main__":
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path);run(p.parse_args().out)

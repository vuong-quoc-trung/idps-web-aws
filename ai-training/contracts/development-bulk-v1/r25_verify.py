"""External benign stress, exact epoch replay and numeric-only R25 evidence."""

import argparse
import os
import time
from pathlib import Path
import joblib
import numpy as np
from idps_ai.common import atomic_json, file_sha256
from idps_ai.export.onnx import cpu_session
from idps_ai.training.checkpoint import load_checkpoint
from r18_data import check,read
from r18_train import WeightedSwiGLU
from r24_pilot import ep
from r25_external import SOURCES,load
from r25_probe import SOURCE


def run(out):
    start=time.monotonic();selection=read(out/"model-selection.json");thresholds=selection["thresholds"]
    scorers={}
    for name,spec in selection["models"].items():
        path=Path(spec["onnx"]) if "onnx" in spec else out/spec["file"]
        check(file_sha256(path)==spec["sha256"],"Selected artifact digest")
        model=cpu_session(path,1) if "onnx" in spec else joblib.load(path)
        scorers[name]=(model,spec["width"],"onnx" in spec)
    report={}
    for source in SOURCES:
        x,methods,metadata=load(source)
        scores={};latency={}
        for name,(model,width,ort) in scorers.items():
            def predict(values):
                return model.run(["score"],{"input":values[:,:width]})[0] if ort else model.predict_proba(values[:,:width])[:,1]
            values=np.concatenate([predict(x[i:i+4096]) for i in range(0,len(x),4096)])
            check(np.isfinite(values).all() and values.min()>=0 and values.max()<=1,"Score validity")
            flags=values>thresholds[name]
            unique,inv=np.unique(x[:,:width],axis=0,return_inverse=True);inv=inv.reshape(-1)
            first=np.unique(inv,return_index=True)[1]
            np.testing.assert_allclose(values[first][inv],values,rtol=1e-5,atol=1e-6)
            scores[name]={"cutoff":thresholds[name],"false_positives":int(flags.sum()),"original_records":len(x),"fpr_by_record":float(flags.mean()),"fpr_balanced_vector":float(flags[first].mean()),"score_coverage":1.,
                          "by_method":{method:{"support":int((methods==i).sum()),"fp":int(flags[methods==i].sum())} for i,method in enumerate(("GET","POST","OTHER"))}}
            # Bounded cold and warm CPU inference; no networking or active service changes.
            samples=[]
            for row in x[:128]:
                t=time.perf_counter_ns();predict(row[None,:]);samples.append(time.perf_counter_ns()-t)
            latency[name]={"warm_batch1_ns_p50_p95":np.percentile(samples[8:],[50,95]).tolist(),"first_call_in_this_microbenchmark_ns":samples[0]}
        report[source]={"metadata":metadata,"frozen_tuning_threshold_stress":scores,"latency":latency}
    root=out/"training/uri100"
    pointer=read(root/"previous.json");previous=load_checkpoint(root/pointer["path"]);latest=load_checkpoint(root)
    check(previous.state["epoch"]+1==latest.state["epoch"],"Replay epochs adjacent")
    check(previous.state["binding"]==latest.state["binding"]==selection["binding"],"Replay binding")
    with np.load(SOURCE/"publisher-r24-uri100.npz",allow_pickle=False) as d:
        ix,y=np.nonzero(d["fit_counts"]);x=d["fit_x"][ix];mass=d["fit_cell_mass"][ix,y]
    model=WeightedSwiGLU.from_arrays(previous.model.metadata(),previous.model.arrays())
    schedule={"scheduler":"warmup_cosine","learning_rate":.00015,"warmup_steps":5,"total_steps":12*int(np.ceil(len(y)/2048)),"min_lr_ratio":.1}
    permutation,loss=ep(model,x,y,mass,previous.state["epoch"],schedule)
    check(loss==latest.state["loss"] and model.steps==latest.model.steps,"Resume loss/step equality")
    np.testing.assert_array_equal(permutation,latest.permutation)
    for name,value in model.arrays().items():
        np.testing.assert_array_equal(value,latest.model.arrays()[name])
    atomic_json(out/"verification.json",{
        "external_benign_stress":report,
        "resume":{"state":"PASS","mode":"New process replayed next epoch from previous immutable generation","optimizer_parameters_permutation_loss":"BIT_EXACT","step":model.steps,"epoch":latest.state["epoch"],"checkpoint_manifest_sha256":pointer["manifest_sha256"]},
        "protected_roles_read":False,"independent_dual_class_claim":"BLOCKED_NO_ELIGIBLE_FRESH_DUAL_CLASS_SOURCE",
        "native_acceptance":"PENDING_REVIEWED_TWO_CLASS_CAL_TEST",
        "rust_abi100_raw_parser":"PENDING_NOT_DEPLOYED","active_services_untouched":True,
        "seconds":time.monotonic()-start,
    })


if __name__=="__main__":
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path);run(p.parse_args().out)

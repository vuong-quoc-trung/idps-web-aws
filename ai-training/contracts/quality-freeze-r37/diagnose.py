"""R36 ranking and error concentration on FIT and historical development tuning."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import onnx
from cohort import BASE, HERE, errors, collision, load, r36


def main(root, out, models):
    x,c,mass,g,hold,tx,ty,tg,b = load(root)
    mixed=c[~hold].min(axis=1)>0
    result={"fit_class_counts":c[~hold].sum(axis=0).tolist(),"fit_mixed":int(mixed.sum()),
            "fit_mixed_class_counts":c[~hold][mixed].sum(axis=0).tolist(),
            "fit_minority_error_floor":int(c[~hold].min(axis=1).sum()),"models":{}}
    meta=json.loads((BASE/"evidence/metrics.json").read_text())
    for arm in ("ExtraTrees","HistGradientBoosting"):
        name="R36-"+arm
        if arm=="ExtraTrees":
            slot=json.loads((BASE/"release/selection.json").read_text())
            m=onnx.load(r36.checked(BASE/"release/candidate.onnx",slot["model_sha256"]))
        else:
            estimator=joblib.load(r36.checked(models/(name+".joblib"),"e4f22cf9692b8998fbc522b076e4e1faeb13401dd01a70eb4379bedf2c9dfcdf"))
            m=r36.export(estimator)
        t=meta["arms"][name]["threshold"]
        p=r36.ort_scores(m,tx)
        result["models"][name]={}
        for key,mask in (("CAL_OP",b==3),("SELECT",b<2)):
            result["models"][name][key]={
                "error":errors(tx[mask],ty[mask],tg[mask],p[mask],t),
                "collision":collision(tx[mask],ty[mask]),
                "ap":meta["arms"][name][key.lower()]["ap"]}
    r36.dump(out,result)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for n in ["root","out","models"]: p.add_argument(n,type=Path)
    a=p.parse_args()
    main(a.root,a.out,a.models)

"""Pinned publisher development roles. No publisher TEST or native records are loaded."""
from pathlib import Path
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "https-model-r36"
sys.path.insert(0, str(BASE))
import study as r36

PLAN = json.loads(r36.PLAN.read_text())
SCHEMA = json.loads(r36.SCHEMA.read_text())
NEG, POS = 0, 1


def load(root):
    material = root / "t09-r24-readiness-msurbJkS/publisher-r24-uri100.npz"
    lineage = root / "t09-r26-acceleration-zfyPqyt3/data-v2/waf-r26.npz"
    with np.load(r36.checked(material, PLAN["waf_cells_sha256"]), allow_pickle=False) as z:
        x, c, mass, parent, tx, ty, tg = (
            z[k] for k in ("fit_x","fit_counts","fit_cell_mass","fit_parent","tune_x","tune_y","tune_groups"))
    with np.load(r36.checked(lineage, PLAN["waf_lineage_sha256"]), allow_pickle=False) as z:
        n = int(z["nfit"])
        pairs = np.unique(np.column_stack([z["parent"][:n],z["component"][:n]]), axis=0)
    lookup = dict(pairs)
    if len(lookup) != len(pairs) or n != c.sum() or n != 400000:
        raise ValueError("Invalid FIT identity mapping")
    g = np.array([lookup[k] for k in parent])
    hold = r36.buckets(g, "r36-holdout", 10) == 0
    roles = r36.buckets(tg, "r36-select", 4)
    sets = [set(r36.signatures(a)) for a in [x[~hold], x[hold], tx[roles < 2], tx[roles == 2], tx[roles == 3]]]
    if set(g) & set(tg) or any(sets[i] & sets[j] for i in range(5) for j in range(i)):
        raise ValueError("Lineage or feature overlap")
    return x,c,mass,g,hold,tx,ty,tg,roles


def method(x):
    out = np.full(len(x), "OTHER",dtype="U5")
    for name in ("GET","POST"):
        out[x[:,SCHEMA["columns"].index("method_"+name)] > .5] = name
    return out


def rate_ci(hit, total):
    from scipy.stats import beta
    if not total:
        return None
    return [float(beta.ppf(.025,hit,total-hit+1)) if hit else 0.,
            float(beta.ppf(.975,hit+1,total-hit)) if total>hit else 1.]


def group_cells(y, group, decision):
    ids, inv = np.unique(group,return_inverse=True)
    cells = np.zeros((len(ids),4),dtype=int)
    np.add.at(cells,(inv,2*y.astype(int)+decision.astype(int)),1)
    return cells


def rates(c):
    tn,fp,fn,tp = c.T
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.column_stack((tp/(tp+fn),fp/(fp+tn)))


def bootstrap(y,g,d,other=None):
    cells = group_cells(y,g,d)
    alt = None if other is None else group_cells(y,g,other)
    rng = np.random.default_rng(37001)
    batches = []
    for _ in range(20):
        ids = rng.integers(len(cells),size=(100,len(cells)))
        sample = rates(cells[ids].sum(axis=1))
        if alt is not None:
            sample -= rates(alt[ids].sum(axis=1))
        batches.append(sample)
    samples = np.concatenate(batches)
    return dict(zip(("recall","fpr"),np.nanpercentile(samples,[2.5,97.5],axis=0).T.tolist()))


def errors(x,y,g,p,t):
    d = p>t
    info = {}
    for name,mask in (("FP",d & (y==0)),("FN",~d & (y==1))):
        ids,frequency=np.unique(g[mask],return_counts=True)
        order=np.argsort(-frequency,kind="stable")[:5]
        info[name]={"n":int(mask.sum()),"components":len(ids),"top_components":[[int(ids[i]),int(frequency[i])] for i in order],
                    "method":{m:int((method(x)[mask]==m).sum()) for m in ("GET","POST","OTHER")}}
    benign=y==0
    ids,count=np.unique(g[benign],return_counts=True)
    info["benign"]={"n":int(benign.sum()),"components":len(ids),
                    "largest_component":int(count.max()),"effective_components":float(count.sum()**2/(count.astype(float)**2).sum()),
                    "score_q50_q95_q99_max":np.quantile(p[benign],[.5,.95,.99,1]).tolist()}
    return info


def collision(x,y):
    _,inv=np.unique(x,axis=0,return_inverse=True)
    c=np.zeros((int(inv.max())+1,2),dtype=int)
    np.add.at(c,(inv.reshape(-1),y),1)
    mixed=c.min(axis=1)>0
    return {"distinct":len(c),"mixed_vectors":int(mixed.sum()),"in_mixed_by_label":c[mixed].sum(axis=0).tolist(),
            "minority_conflict_floor":int(np.min(c,axis=1).sum())}

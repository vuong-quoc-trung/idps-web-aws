"""Coordinate-bound lexical extension on the existing WAF FIT/TUNING roster."""

import argparse
import os
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
import r16_waf as waf
from r18_data import check, read
from r20_quality import R19, PINS
from r24_data import census
from r25_features import lexical, VERSION, SPECS
from r25_probe import SOURCE, DATA_SHA
from idps_ai.common import atomic_json, file_sha256


def run(out):
    start = time.monotonic()
    check(file_sha256(SOURCE / "publisher-r24-uri100.npz") == DATA_SHA, "R24 data pin")
    check(file_sha256(R19 / "waf-r19.npz") == PINS["waf-r19.npz"], "R19 pin")
    check(file_sha256(waf.WAF) == waf.WAF_SHA, "WAF TRAIN pin")
    with np.load(R19 / "waf-r19.npz", allow_pickle=False) as d:
        coords = np.r_[d["fit_row"], d["tuning_row"]]
        labels = np.r_[d["fit_label"], d["tuning_label"]]
        indices = np.r_[d["fit_index"], d["tuning_index"]]
        nfit = len(d["fit_row"])
        counts = d["counts"]
    with np.load(SOURCE / "publisher-r24-uri100.npz", allow_pickle=False) as d:
        original_fields = {k: d[k] for k in d.files}
    check(nfit == 400000 and len(np.unique(coords)) == len(coords), "Original identities")
    order = np.argsort(coords)
    sorted_coords = coords[order]
    extra = np.zeros((len(coords), 32), np.uint8)
    seen = offset = 0
    encode = lru_cache(maxsize=32768)(lexical)
    for batch in waf.source().iter_batches(batch_size=waf.BATCH, columns=["method", "url", "label"], use_threads=False):
        end = offset + batch.num_rows
        lo, hi = np.searchsorted(sorted_coords, [offset, end])
        rows = batch.take(sorted_coords[lo:hi] - offset).to_pylist() if hi > lo else ()
        for i, row in zip(order[lo:hi], rows, strict=True):
            origin = waf.origin_view(row["url"])
            check(origin and waf.LABEL[row["label"]] == labels[i], "Coordinate/label binding")
            extra[i] = encode(origin[0])
            seen += 1
        offset = end
    check(seen == len(coords), "Projection coverage")
    # Recover every FIT URI100 row from the same extension code as the frozen ETL.
    from r23_features import numeric, sketch
    from idps_ai.features.request_time import from_request
    # R24 unique rows cannot recover original-to-extended-vector mapping; join it
    # explicitly from the pinned original coordinates, without persisting targets.
    base = np.empty((nfit, 100), np.float32)
    offset = 0
    base_encode = lru_cache(maxsize=32768)(lambda m,t: np.r_[from_request(t,m), numeric(*sketch(t))[0].astype(np.float32)/31])
    fit_order = np.argsort(coords[:nfit]); fit_coords = coords[:nfit][fit_order]
    for batch in waf.source().iter_batches(batch_size=waf.BATCH, columns=["method", "url"], use_threads=False):
        end = offset + batch.num_rows; lo, hi = np.searchsorted(fit_coords, [offset, end])
        rows = batch.take(fit_coords[lo:hi]-offset).to_pylist() if hi>lo else ()
        for i,row in zip(fit_order[lo:hi],rows,strict=True):
            base[i] = base_encode(row["method"],waf.origin_view(row["url"])[0])
        offset = end
    x, group_counts, inv, summary = census(np.column_stack((base,extra[:nfit].astype(np.float32))), labels[:nfit])
    first = np.unique(inv, return_index=True)[1]
    parent = indices[:nfit][first]
    parent_mass = np.minimum(8,np.sqrt(counts.sum(axis=1))) / counts.sum(axis=1)
    tune_x = np.column_stack((original_fields["tune_x"],extra[nfit:].astype(np.float32)))
    # FIT/TUNING already disjoint under the stricter URI76 closure, inherited intact.
    path = out / "publisher-r25-uri132.npz"
    waf.write_array(path,fit_x=x,fit_counts=group_counts,fit_cell_mass=group_counts*parent_mass[parent,None],
        fit_parent=parent,tune_x=tune_x,tune_y=labels[nfit:],tune_groups=original_fields["tune_groups"],
        tune_context=original_fields["tune_context"],binary_class_weights=original_fields["binary_class_weights"])
    component = original_fields["tune_groups"] == 2780
    summary_big = {}
    for label in (0,1):
        e = extra[nfit:][component & (labels[nfit:] == label)]
        summary_big[str(label)] = {"originals":len(e),"indicator_count_by_name":dict(zip([n for n,_ in SPECS],e.sum(axis=0).tolist(),strict=True))}
    atomic_json(out / "dataset-manifest.json",{
        "role":"WAF_PUBLISHER_DEVELOPMENT", "fit_originals":nfit,"tuning_originals":len(coords)-nfit,
        "schema":VERSION,"schema_sha256":file_sha256(Path(__file__).with_name("r25_features.py")),
        "dataset_sha256":file_sha256(path),"source_sha256":waf.WAF_SHA,"parent_dataset_sha256":DATA_SHA,
        "fit_uri132":summary,"dominant_tuning_component_2780":summary_big,
        "roles_unchanged":True,"protected_roles_read":False,"raw_inputs_persisted":False,
        "seconds":time.monotonic()-start,
    })


if __name__ == "__main__":
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path)
    run(p.parse_args().out)

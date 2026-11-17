"""Bounded nonlinear URI100 alternative, on permitted publisher FIT/TUNING only."""

import argparse
import os
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from idps_ai.common import atomic_json, file_sha256
from r18_data import check
from r24_eval import evaluate

SOURCE = Path(__file__).resolve().parents[2] / ".artifacts/t09-r24-readiness-msurbJkS"
DATA_SHA = "249f7810b3bbdfef2e898bac120b42ef9857c3da6cf35b8302092e996114a4f5"


def run(out):
    start = time.monotonic()
    path = SOURCE / "publisher-r24-uri100.npz"
    check(file_sha256(path) == DATA_SHA, "R24 dataset pin")
    with np.load(path, allow_pickle=False) as d:
        x, counts, mass = (d[k] for k in ("fit_x", "fit_counts", "fit_cell_mass"))
        tx, ty, groups, context = (d[k] for k in ("tune_x", "tune_y", "tune_groups", "tune_context"))
        balance = d["binary_class_weights"]
    ix, label = np.nonzero(counts)
    weights = mass[ix, label] * balance[label]
    plan = {
        "purpose": "ALTERNATIVE_ARCHITECTURE_RESEARCH_PROBE",
        "input_sha256": DATA_SHA, "fit_originals": int(counts.sum()),
        "code_sha256": file_sha256(__file__),
        "iterations": 150, "max_leaf_nodes": 15, "learning_rate": 0.05,
        "l2_regularization": 1, "seed": 2501,
        "selection": "Exposed TUNING diagnostic only. No protected HOLDOUT access or release claim.",
    }
    atomic_json(out / "probe-plan.json", plan)
    arms = {}
    for width in (76, 100):
        model = HistGradientBoostingClassifier(
            max_iter=150, max_leaf_nodes=15, learning_rate=0.05,
            l2_regularization=1, early_stopping=False, random_state=2501,
        ).fit(x[ix, :width], label, sample_weight=weights)
        scores = model.predict_proba(tx[:, :width])[:, 1].astype(np.float32)
        arms[str(width)] = evaluate(tx[:, :width], ty, scores, groups, context)
        np.savez_compressed(out / f"probe-scores-{width}.npz", scores=scores)
    atomic_json(out / "probe.json", {"arms": arms, "seconds": time.monotonic() - start})


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)

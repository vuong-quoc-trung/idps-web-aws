"""Post-selection diagnostics for feature distribution and representation collisions."""
import argparse
import json
from pathlib import Path

import numpy as np
import onnx
from scipy.stats import ks_2samp

from cohort import BASE, PLAN, SCHEMA, load, r36
from experiment import originals


def optimistic_recall(counts):
    # Fractional relaxation lets an oracle allocate any portion of a mixed cell.
    neg, pos = counts.T
    budget = neg.sum() * 0.01
    total = float(pos[neg == 0].sum())
    indices = np.flatnonzero((neg > 0) & (pos > 0))
    for i in indices[np.argsort(-(pos[indices] / neg[indices]))]:
        used = min(budget, neg[i])
        total += used * pos[i] / neg[i]
        budget -= used
        if budget <= 0:
            break
    return float(total / pos.sum())


def run(root, directory, output):
    selection = json.loads((directory / "selection.json").read_text())
    model = onnx.load(r36.checked(directory / "finalist.onnx", selection["files"]["finalist.onnx"]))
    x, counts, _, _, hold, tx, ty, _, roles = load(root)
    i, y = originals(counts[~hold])
    s = r36.ort_scores(model, x[~hold])[i]
    prob = r36.ort_scores(model, x[~hold], "publisher_probability")[i]
    result = {
        "fit_resubstitution": r36.stats(y, s, selection["threshold"], prob),
        "fit_fractional_oracle_max_recall_at_1pct": optimistic_recall(counts[~hold]),
        "selection_sha256": r36.sha(directory / "selection.json"),
        "shift": {},
    }
    reference = tx[(roles == 3) & (ty == 0)]
    used = set(r36.signatures(x)) | set(r36.signatures(tx))
    panels = {"WAF_SELECT": tx[(roles < 2) & (ty == 0)]}
    for source, pin in PLAN["transfer_sha256"].items():
        path = root / "t09-r32-information-TIu0kTGQ/verified/pilot" / (source + ".npz")
        with np.load(r36.checked(path, pin), allow_pickle=False) as z:
            xx, yy, groups, n = z["x"], z["y"], z["group"], int(z["nfit"])
        touched = {g for g, view in zip(groups, r36.signatures(xx), strict=True) if view in used}
        panels[source + "_TUNING"] = xx[(np.arange(len(yy)) >= n) & (yy == 0) & ~np.isin(groups, list(touched))]
    for name, normal in panels.items():
        shifts = []
        for j, col in enumerate(SCHEMA["columns"]):
            distance = ks_2samp(reference[:, j], normal[:, j], method="asymp").statistic
            shifts.append({"feature": col, "ks_distance": float(distance),
                           "cal_median": float(np.median(reference[:, j])), "panel_median": float(np.median(normal[:, j]))})
        result["shift"][name] = {"normal": len(normal),
                                  "largest_marginal_differences": sorted(shifts, key=lambda row: -row["ks_distance"])[:5]}
    r36.dump(output, result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ["root","study","output"]:
        p.add_argument(name,type=Path)
    a = p.parse_args()
    run(a.root, a.study, a.output)

"""Post-lock transfer to historical publisher FIT rows unused by the WAF-only candidate."""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
from study import HERE, PLAN, checked, sha, signatures, ort_scores, stats, dump


def run(root, output):
    plan = json.loads(PLAN.read_text())
    selection = HERE / "release/selection.json"
    lock = json.loads(selection.read_text())
    model = onnx.load(checked(HERE / "release/candidate.onnx", lock["model_sha256"]))
    cells = root / "t09-r24-readiness-msurbJkS/publisher-r24-uri100.npz"
    with np.load(checked(cells, plan["waf_cells_sha256"]), allow_pickle=False) as a:
        used = set(signatures(a["fit_x"])) | set(signatures(a["tune_x"]))
    roles = {}
    for name, pin in plan["transfer_sha256"].items():
        f = root / "t09-r32-information-TIu0kTGQ/verified/pilot" / (name + ".npz")
        with np.load(checked(f, pin), allow_pickle=False) as a:
            n = int(a["nfit"])
            x, y, g = a["x"][:n], a["y"][:n], a["group"][:n]
        # Embargo whole transfer components touching a WAF view, not just the duplicate row.
        touched = set(g[i] for i, v in enumerate(signatures(x)) if v in used)
        keep = ~np.isin(g, list(touched))
        x, y = x[keep], y[keep]
        scores = ort_scores(model, x)
        prob = ort_scores(model, x, "publisher_probability")
        roles[name] = dict(
            role="historical publisher FIT, transfer only for R36 WAF model",
            support=n,
            embargoed_rows=int((~keep).sum()),
            embargoed_components=len(touched),
            groups=len(set(g[keep])),
            metrics=stats(y, scores, lock["threshold"], prob),
        )
    dump(
        output,
        dict(
            selection_sha256=sha(selection),
            threshold=lock["threshold"],
            sources=roles,
            limitation="Independent of this WAF fit/selection. Publisher semantics and historical development use preclude a T07 release claim.",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    run(a.root, a.output)

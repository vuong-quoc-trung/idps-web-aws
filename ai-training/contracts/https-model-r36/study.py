"""Finite WAF publisher model selection. Other publishers are transfer diagnostics only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import joblib
import numpy as np
import onnx
import onnxruntime as ort
from onnx import helper, numpy_helper
from scipy.special import expit, logit
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix


HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
SCHEMA = HERE.parent / "https-shadow-r35/schema.json"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def checked(p, pin):
    if sha(p) != pin:
        raise ValueError(f"Digest mismatch: {p.name}")
    return p


def atomic(p, data):
    with tempfile.NamedTemporaryFile(dir=p.parent, delete=False) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(f.name, p)
    directory = os.open(p.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def dump(p, obj):
    atomic(p, (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def buckets(groups, salt, mod):
    def bucket(g):
        return int.from_bytes(hashlib.sha256(f"{salt}:{g}".encode()).digest()[:8], "big") % mod

    lookup = {g: bucket(g) for g in np.unique(groups)}
    return np.array([lookup[g] for g in groups])


def signatures(x):
    v = np.asarray(x, dtype="<f4").copy()
    v[v == 0] = 0
    return [row.tobytes() for row in v]


def ort_scores(model, x, output="score"):
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(model.SerializeToString(), opts, providers=["CPUExecutionProvider"])
    scores = sess.run([output], {"input": x.astype("float32", copy=False)})[0]
    if scores.shape != (len(x),) or not np.isfinite(scores).all():
        raise ValueError("Invalid ONNX output")
    return scores


def export(est):
    # The ONNX-ML regressor expresses each binary tree as one positive-class contribution.
    # numpy booleans emitted by some sklearn converters are not valid repeated int64s.
    hist = isinstance(est, HistGradientBoostingClassifier)
    trees = [r[0].nodes for r in est._predictors] if hist else [t.tree_ for t in est.estimators_]
    a = {
        key: []
        for key in (
            "nodes_treeids",
            "nodes_nodeids",
            "nodes_featureids",
            "nodes_modes",
            "nodes_values",
            "nodes_truenodeids",
            "nodes_falsenodeids",
            "target_treeids",
            "target_nodeids",
            "target_ids",
            "target_weights",
        )
    }
    for tid, tree in enumerate(trees):
        for nid in range(len(tree) if hist else tree.node_count):
            if hist:
                node = tree[nid]
                leaf = bool(node["is_leaf"])
                feat, cut, left, right, weight = [
                    node[k] for k in ("feature_idx", "num_threshold", "left", "right", "value")
                ]
            else:
                left, right = tree.children_left[nid], tree.children_right[nid]
                leaf = left == right
                feat, cut = tree.feature[nid], tree.threshold[nid]
                weights = tree.value[nid, 0]
                weight = weights[1] / weights.sum() / len(trees)
            v = np.float32(cut)
            if float(v) > cut:
                v = np.nextafter(v, np.float32(-np.inf))
            for key, val in (
                ("treeids", tid),
                ("nodeids", nid),
                ("featureids", 0 if leaf else int(feat)),
                ("modes", "LEAF" if leaf else "BRANCH_LEQ"),
                ("values", 0.0 if leaf else float(v)),
                ("truenodeids", 0 if leaf else int(left)),
                ("falsenodeids", 0 if leaf else int(right)),
            ):
                a["nodes_" + key].append(val)
            if leaf:
                for key, val in (
                    ("treeids", tid),
                    ("nodeids", nid),
                    ("ids", 0),
                    ("weights", float(weight)),
                ):
                    a["target_" + key].append(val)
    ops = [
        helper.make_node(
            "TreeEnsembleRegressor",
            ["input"],
            ["trees"],
            domain="ai.onnx.ml",
            n_targets=1,
            base_values=[float(est._baseline_prediction.item()) if hist else 0.0],
            **a,
        )
    ]
    if hist:
        ops.append(helper.make_node("Sigmoid", ["trees"], ["prob"]))
    ops.append(helper.make_node("Squeeze", ["prob" if hist else "trees", "axis"], ["score"]))
    graph = helper.make_graph(
        ops,
        "r36-uri100",
        [helper.make_tensor_value_info("input", onnx.TensorProto.FLOAT, [None, 100])],
        [helper.make_tensor_value_info("score", onnx.TensorProto.FLOAT, [None])],
        [numpy_helper.from_array(np.array([1], dtype=np.int64), "axis")],
    )
    m = helper.make_model(
        graph,
        ir_version=9,
        opset_imports=[helper.make_opsetid("", 17), helper.make_opsetid("ai.onnx.ml", 3)],
    )
    onnx.checker.check_model(m)
    return m


def calibrate(raw, y):
    z = logit(np.clip(raw.astype("float64"), 1e-6, 1 - 1e-6))
    lr = LogisticRegression(C=10, solver="lbfgs", max_iter=300).fit(z[:, None], y)
    slope, bias = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    if slope <= 0:
        raise ValueError("Non-monotone calibration")
    return slope, bias


def calibrated_model(raw, slope, bias):
    m = onnx.ModelProto.FromString(raw.SerializeToString())
    for name, val in dict(lo=1e-6, hi=1 - 1e-6, one=1.0, slope=slope, bias=bias).items():
        m.graph.initializer.append(numpy_helper.from_array(np.float32(val), "r36_" + name))
    for op, inputs, out in [
        ("Clip", ["score", "r36_lo", "r36_hi"], "r36_clipped"),
        ("Sub", ["r36_one", "r36_clipped"], "r36_den"),
        ("Div", ["r36_clipped", "r36_den"], "r36_odds"),
        ("Log", ["r36_odds"], "r36_logit"),
        ("Mul", ["r36_logit", "r36_slope"], "r36_product"),
        ("Add", ["r36_product", "r36_bias"], "r36_logodds"),
        ("Sigmoid", ["r36_logodds"], "publisher_probability"),
    ]:
        m.graph.node.append(helper.make_node(op, inputs, [out]))
    m.graph.output.append(
        helper.make_tensor_value_info("publisher_probability", onnx.TensorProto.FLOAT, [None])
    )
    onnx.checker.check_model(m)
    return m


def stats(y, p, t, prob):
    y = np.asarray(y)
    tn, fp, fn, tp = map(int, confusion_matrix(y, p > t, labels=[0, 1]).ravel())
    if not (tn + fp and tp + fn):
        raise ValueError("A measured role lacks two classes")
    recall = tp / (tp + fn)
    fpr = fp / (fp + tn)
    return dict(
        n=len(y),
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        recall=recall,
        fpr=fpr,
        accuracy=(tp + tn) / len(y),
        balanced_accuracy=(recall + 1 - fpr) / 2,
        precision=tp / (tp + fp) if tp + fp else None,
        ap=float(average_precision_score(y, p)),
        brier=float(brier_score_loss(y, prob)),
        coverage=1.0,
    )


def run(root, out):
    binding = dict(plan=sha(PLAN), study=sha(Path(__file__)), schema=sha(SCHEMA))
    complete = out / "completed.json"
    if complete.exists():
        state = json.loads(complete.read_text())
        if state["binding"] != binding:
            raise ValueError("Completed study binding mismatch")
        for filename, pin in state["files"].items():
            if Path(filename).name != filename:
                raise ValueError("Invalid artifact path")
            checked(out / filename, pin)
        print("RESUMED_COMPLETED", state["winner"], flush=True)
        return
    plan = json.loads(PLAN.read_text())
    r24 = root / "t09-r24-readiness-msurbJkS/publisher-r24-uri100.npz"
    r26 = root / "t09-r26-acceleration-zfyPqyt3/data-v2/waf-r26.npz"
    with np.load(checked(r24, plan["waf_cells_sha256"]), allow_pickle=False) as z:
        x, c, mass, parent, tx, ty, tg = [
            z[k]
            for k in (
                "fit_x",
                "fit_counts",
                "fit_cell_mass",
                "fit_parent",
                "tune_x",
                "tune_y",
                "tune_groups",
            )
        ]
    with np.load(checked(r26, plan["waf_lineage_sha256"]), allow_pickle=False) as z:
        n = int(z["nfit"])
        par, groups = z["parent"][:n], z["component"][:n]
    pairs = np.unique(np.column_stack((par, groups)), axis=0)
    assert len(set(pairs[:, 0])) == len(pairs)
    lookup = dict(pairs)
    fg = np.array([lookup[k] for k in parent])
    hold = buckets(fg, "r36-holdout", 10) == 0
    b = buckets(tg, "r36-select", 4)
    select, calfit, calop = b < 2, b == 2, b == 3
    assert (
        n == c.sum() == 400000
        and not set(tg) & set(fg)
        and not set(signatures(x)) & set(signatures(tx))
    )
    sets = [set(signatures(tx[v])) for v in [select, calfit, calop]]
    assert not any(sets[i] & sets[j] for i in range(3) for j in range(i))
    idx, yy = np.where((c > 0) & (~hold[:, None]))
    w = mass[idx, yy].copy()
    w *= w.sum() / (2 * np.bincount(yy, weights=w)[yy])
    records = {}
    for name, v in [("fit", ~hold), ("new_model_holdout", hold)]:
        cc = c[v].sum(axis=0)
        records[name] = dict(
            normal=int(cc[0]), anomalous=int(cc[1]), vectors=int(v.sum()), groups=len(set(fg[v]))
        )
    for name, v in [("select", select), ("cal_fit", calfit), ("cal_op", calop)]:
        records[name] = dict(
            normal=int((ty[v] == 0).sum()),
            anomalous=int(ty[v].sum()),
            vectors=len(sets[["select", "cal_fit", "cal_op"].index(name)]),
            groups=len(set(tg[v])),
        )
    arms = {}
    raw = {}
    reg = {
        "R35-logistic": HERE.parent / "https-shadow-r35/bundle/publisher.onnx",
        "R25-SwiGLU": root / "t09-r25-quality-EsMMItaJ/swiglu-uri100-r25.onnx",
    }
    for name in plan["candidates"]:
        ckpt = out / (name + ".joblib")
        pin = out / (name + ".checkpoint.json")
        if name in reg:
            m = onnx.load(
                checked(
                    reg[name],
                    plan["r35_onnx_sha256" if name.startswith("R35") else "r25_onnx_sha256"],
                )
            )
            native_err = None
        else:
            if pin.exists():
                d = json.loads(pin.read_text())
                if d["binding"] != binding:
                    raise ValueError("Checkpoint binding mismatch")
                est = joblib.load(checked(ckpt, d["sha"]))
            else:
                if name.endswith("ExtraTrees"):
                    est = ExtraTreesClassifier(
                        n_estimators=48,
                        max_depth=9,
                        min_samples_leaf=3,
                        max_features=0.8,
                        n_jobs=1,
                        random_state=36,
                    )
                else:
                    est = HistGradientBoostingClassifier(
                        max_iter=140,
                        max_leaf_nodes=15,
                        l2_regularization=2,
                        learning_rate=0.08,
                        early_stopping=False,
                        random_state=36,
                    )
                est.fit(x[idx], yy, sample_weight=w)
                import io

                buf = io.BytesIO()
                joblib.dump(est, buf, compress=3)
                atomic(ckpt, buf.getvalue())
                dump(pin, dict(binding=binding, sha=sha(ckpt)))
            m = export(est)
            native_err = float(np.max(np.abs(est.predict_proba(tx)[:, 1] - ort_scores(m, tx))))
            if native_err > 2e-5:
                raise ValueError(f"Native export parity {name}: {native_err}")
        p = ort_scores(m, tx)
        slope, bias = calibrate(p[calfit], ty[calfit])
        model = calibrated_model(m, slope, bias)
        pred = ort_scores(model, tx)
        reference = expit(
            logit(np.clip(p, np.float32(1e-6), np.float32(1 - 1e-6))).astype(float) * slope + bias
        )
        prob = ort_scores(model, tx, "publisher_probability")
        err = float(np.max(np.abs(prob - reference)))
        if err > 2e-5:
            raise ValueError("Calibrated ONNX parity")
        neg = np.sort(pred[calop & (ty == 0)])
        t = float(neg[len(neg) - 1 - len(neg) // 100])
        arms[name] = dict(
            slope=slope,
            bias=bias,
            threshold=t,
            select=stats(ty[select], pred[select], t, prob[select]),
            cal_op=stats(ty[calop], pred[calop], t, prob[calop]),
            bytes=model.ByteSize(),
            native_export_error=native_err,
            calibration_parity_error=err,
        )
        raw[name] = model

    def key(name):
        a = arms[name]
        s = a["select"]
        return (max(0, s["fpr"] - 0.01), -s["recall"], -s["ap"], a["bytes"])

    eligible = [k for k, a in arms.items() if a["cal_op"]["tp"] > 0]
    if not eligible:
        raise ValueError("No non-degenerate CAL_OP operating point")
    winner = min(eligible, key=key)
    m = raw[winner]
    t = arms[winner]["threshold"]
    # Deterministic filename and manifest lock precede any holdout/transfer predictions.
    model = out / "candidate.onnx"
    atomic(model, m.SerializeToString())
    lock = dict(
        version=winner.lower() + "-uri100-v1",
        winner=winner,
        model_sha256=sha(model),
        schema_sha256=sha(SCHEMA),
        feature_abi="idps-uri100-raw-ascii-r26-v1",
        threshold=t,
        operator=">",
        task=plan["task"],
        enforcement_allowed=False,
        calibration="publisher_probability output only; strict threshold on score",
        binding=binding,
    )
    dump(out / "selection.json", lock)
    held_idx, held_y = np.where((c > 0) & hold[:, None])
    repeats = c[held_idx, held_y]
    h = stats(
        np.repeat(held_y, repeats),
        np.repeat(ort_scores(m, x[held_idx]), repeats),
        t,
        np.repeat(ort_scores(m, x[held_idx], "publisher_probability"), repeats),
    )
    transfer = {}
    exclude = set(signatures(x)) | set(signatures(tx))
    for name, pin in plan["transfer_sha256"].items():
        path = root / "t09-r32-information-TIu0kTGQ/verified/pilot" / (name + ".npz")
        with np.load(checked(path, pin), allow_pickle=False) as z:
            nfit = int(z["nfit"])
            f = z["x"][nfit:]
            y = z["y"][nfit:]
        keep = np.array([s not in exclude for s in signatures(f)])
        transfer[name] = dict(
            exact_overlap_excluded=int((~keep).sum()),
            metrics=stats(
                y[keep], ort_scores(m, f[keep]), t, ort_scores(m, f[keep], "publisher_probability")
            ),
        )
    dump(
        out / "metrics.json",
        dict(
            binding=binding,
            counts=records,
            arms=arms,
            selected=winner,
            threshold=t,
            holdout=h,
            holdout_valid_for_winner=winner not in reg,
            transfer=transfer,
            native=dict(train=0, cal=0, test=0),
        ),
    )
    files = ["metrics.json", "selection.json", "candidate.onnx"]
    for name in plan["candidates"]:
        if name not in reg:
            files.extend([name + ".joblib", name + ".checkpoint.json"])
    dump(complete, dict(binding=binding, winner=winner, files={f: sha(out / f) for f in files}))
    print(winner, records, h, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("input_root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    run(a.input_root, a.output)

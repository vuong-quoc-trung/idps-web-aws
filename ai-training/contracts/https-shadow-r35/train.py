"""Bounded URI100 publisher training check. Accept only the frozen WAF FIT/TUNING roster."""

import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import onnxruntime as ort
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix

DATA_SHA = "57960dea5e8a15110d51abb1c342d577d7b1a45b4cdf38577f1a3224495579f3"
SCHEMA = "idps-uri100-raw-ascii-r26-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stream.name, path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def fit(dataset, output, native_pin=None):
    output.mkdir(mode=0o700, exist_ok=True)
    with (output / ".fit.lock").open("ab") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return fit_locked(dataset, output, native_pin)


def fit_locked(dataset, output, native_pin):
    data_pin = native_pin if native_pin is not None else DATA_SHA
    if sha(dataset) != data_pin:
        raise ValueError("Dataset SHA mismatch")
    manifest = output / "manifest.json"
    model = output / ("publisher.onnx" if native_pin is None else "native.onnx")
    if native_pin is not None:
        from native import load_native

        x, y, g, mass, n = load_native(dataset, native_pin)
        task = "NATIVE_VERIFIED_HTTP_ATTACK_DETECTION"
        source = "Independent custodian-admitted HTTPS canonical TRAIN / preassigned FIT and TUNING"
    else:
        with np.load(dataset, allow_pickle=False) as a:
            x, y, g, mass, n = a["x"], a["y"], a["group"], a["mass"], int(a["nfit"])
        task = "WAF_PUBLISHER_NORMAL_ANOMALOUS"
        source = "WAF Data v2 TRAIN / R32 pilot"
    x[x == 0] = 0.0
    contract_files = ["native.py", "receiver.py"] if native_pin is not None else ["receiver.py"]
    preprocessing_pins = {name: sha(Path(__file__).with_name(name)) for name in contract_files}
    if manifest.exists():
        result = json.loads(manifest.read_text())
        if (
            result.get("runtime_contract_sha256") != preprocessing_pins
            or result["model_sha256"] != sha(model)
            or result["data_sha256"] != data_pin
            or result["task"] != task
            or result["trainer_sha256"] != sha(Path(__file__))
        ):
            raise ValueError("Checkpoint binding mismatch")
        return result
    if (
        x.shape != (len(y), 100)
        or not np.isfinite(x).all()
        or set(g[:n]) & set(g[n:])
        or {r.tobytes() for r in x[:n]} & {r.tobytes() for r in x[n:]}
        or set(y[:n]) != {0, 1}
        or set(y[n:]) != {0, 1}
        or not np.all(mass > 0)
    ):
        raise ValueError("Dataset contract or split violated")
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=35)
    lr.fit(x[:n], y[:n], sample_weight=mass)
    params = [
        numpy_helper.from_array(v, name)
        for name, v in (
            ("w", lr.coef_.T.astype("float32")),
            ("b", lr.intercept_.astype("float32")),
            ("axis", np.array([1], dtype=np.int64)),
        )
    ]
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["input", "w"], ["wx"]),
            helper.make_node("Add", ["wx", "b"], ["z"]),
            helper.make_node("Sigmoid", ["z"], ["prob"]),
            helper.make_node("Squeeze", ["prob", "axis"], ["score"]),
        ],
        ("URI100-WAF-publisher" if native_pin is None else task),
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [None, 100])],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, [None])],
        params,
    )
    onx = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    onnx.checker.check_model(onx)
    write(model, onx.SerializeToString())
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    cpu = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
    scores = cpu.run(["score"], {"input": x[n:]})[0]
    err = float(np.max(np.abs(lr.predict_proba(x[n:])[:, 1] - scores)))
    if err > 2e-5:
        raise ValueError("ONNX parity failed")
    # Diagnostic operating point only, chosen and described on TUNING.
    negative = scores[y[n:] == 0]
    threshold = float(
        np.nextafter(
            np.quantile(negative, 0.99, method="higher"), np.float32(np.inf), dtype=np.float32
        )
    )
    tn, fp, fn, tp = map(int, confusion_matrix(y[n:], scores >= threshold).ravel())
    result = dict(
        schema=SCHEMA,
        task=task,
        source=source,
        data_sha256=data_pin,
        trainer_sha256=sha(Path(__file__)),
        model_sha256=sha(model),
        runtime_contract_sha256=preprocessing_pins,
        fit=n,
        tuning=len(y) - n,
        fit_normal=int(sum(y[:n] == 0)),
        tuning_normal=len(negative),
        cal=0,
        test=0,
        native_train=len(y) if native_pin is not None else 0,
        group_overlap=0,
        vector_overlap=0,
        fit_unique_vectors=len({v.tobytes() for v in x[:n]}),
        effective_fit_weight=float(mass.sum()),
        development_only=True,
        enforcement_allowed=False,
        max_python_onnx_error=err,
        tuning_metrics=dict(
            threshold=threshold,
            ap=float(average_precision_score(y[n:], scores)),
            brier=float(brier_score_loss(y[n:], scores)),
            tp=tp,
            fp=fp,
            tn=tn,
            fn=fn,
            recall=tp / (tp + fn),
            fpr=fp / (fp + tn),
            precision=tp / (tp + fp) if tp + fp else None,
        ),
    )
    write(manifest, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--native-handoff-sha", help="External custodian pin for the canonical TRAIN export"
    )
    args = parser.parse_args()
    print(json.dumps(fit(args.dataset, args.output, args.native_handoff_sha), sort_keys=True))

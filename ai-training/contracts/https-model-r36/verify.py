"""Recompute URI100 and compare the calibrated checkpoint, ONNX and actual Rust scores."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import joblib
import numpy as np
import onnxruntime as ort
from scipy.special import expit, logit

HERE = Path(__file__).resolve().parent
sys.path[:0] = [
    str(HERE.parent / "https-shadow-r35"),
    str(HERE.parent / "development-bulk-v1"),
    str(HERE.parents[1] / "src"),
]
from idps_ai.features.request_time import from_request
from r23_features import sketch, describe_lane
from receiver import vector_sha, MODE, SCHEMA
from serve import slot


def run(a):
    live = json.loads((a.live / "live.json").read_text())
    cp = HERE / "release/R36-ExtraTrees.joblib"
    if (
        hashlib.sha256(cp.read_bytes()).hexdigest()
        != json.loads(cp.with_suffix(".checkpoint.json").read_text())["sha"]
    ):
        raise ValueError("Untrusted checkpoint")
    model = joblib.load(cp)
    met = json.loads((HERE / "evidence/metrics.json").read_text())["arms"]["R36-ExtraTrees"]
    slots = {v["sha256"]: v for v in (slot(None), slot("rollback"))}
    summary = []
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = opts.inter_op_num_threads = 1
    for rid, row in live["requests"].items():
        path = row["route"]
        method = row["method"]
        s = slots[row["model_sha256"]]
        p, q = sketch(path)
        shape = (
            np.minimum(31, describe_lane(p, b"/") + describe_lane(q, b"&")).astype(np.float32) / 31
        )
        x = np.r_[from_request(path, method), shape].astype("float32")[None, :]
        assert vector_sha(x[0]) == row["vector_sha256"]
        sess = ort.InferenceSession(
            str(HERE / s["model"]), opts, providers=["CPUExecutionProvider"]
        )
        score = sess.run(["score"], {"input": x})[0].item()
        assert abs(row["score"] - score) < 2e-5
        est_err = None
        if s == slot(None):
            pred = model.predict_proba(x)[0, 1]
            est_err = float(abs(pred - score))
            prob = sess.run(["publisher_probability"], {"input": x})[0].item()
            assert (
                est_err < 2e-5
                and abs(
                    expit(logit(np.clip(pred, 1e-6, 1 - 1e-6)) * met["slope"] + met["bias"]) - prob
                )
                < 2e-5
            )
        summary.append(
            dict(
                request_id=rid,
                model=s["version"],
                feature_parity=True,
                python_rust_error=abs(row["score"] - score),
                estimator_error=est_err,
            )
        )
    s = slot(None)
    input_frame = json.dumps(dict(schema=SCHEMA, mode=MODE, method="GET", target="/api/auth/me"))
    cli = [a.scorer, "--https-shadow", HERE / s["model"], s["sha256"], a.ort]
    fail = subprocess.run(
        [*cli[:3], "0" * 64, a.ort], input="", capture_output=True, text=True, timeout=10
    )
    assert fail.returncode != 0
    res = subprocess.run(
        cli,
        input="{}\n" + (input_frame + "\n") * 51,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    rows = list(map(json.loads, res.stdout.splitlines()))
    assert rows[0]["status"] == "ABSTAIN" and all(
        r["model_sha256"] == s["sha256"] and not r["hybrid_allowed"] for r in rows[1:]
    )
    times = {}
    for key in ["preprocessing_ns", "inference_ns"]:
        times[key] = dict(
            zip(["p50", "p95"], map(float, np.percentile([r[key] for r in rows[2:]], [50, 95])))
        )
    result = dict(
        requests=summary,
        benchmark="50 warm repeats of one allowed frame, one thread",
        warm_ns=times,
        model_load_ms=rows[1]["model_load_ns"] / 1e6,
        invalid_sha_refused=True,
        malformed_then_recovery=True,
    )
    a.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ["live", "output", "scorer", "ort"]:
        p.add_argument("--" + k, type=Path, required=True)
    run(p.parse_args())

"""Read-only replay of the bounded HTTPS acceptance, including parity and Hybrid."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import onnxruntime as ort

from receiver import SCHEMA, MODE, vector_sha

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-training/contracts/development-bulk-v1"))
from r23_features import describe_lane, sketch
from idps_ai.features.request_time import from_request


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(a):
    run = json.loads((a.live / "live.json").read_bytes())
    if run["rust_transaction_proof"] != "PASS" or run["cleanup"] != "PASS":
        raise ValueError("Unverified source capture")
    expected = json.loads((a.bundle / "manifest.json").read_bytes())["model_sha256"]
    model = a.bundle / "publisher.onnx"
    if hashlib.sha256(model.read_bytes()).hexdigest() != expected:
        raise ValueError("Model pin mismatch")
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = opts.intra_op_num_threads = 1
    session = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
    worker = load(ROOT / "scripts/ai-shadow-worker.py")
    worker.verify_active_strategy()
    if hashlib.sha256((a.ri / "manifest.json").read_bytes()).hexdigest() != worker.MANIFEST_SHA:
        raise ValueError("RI v2 manifest mismatch")
    predictor = load(ROOT / "ai-training/scripts/integration-request-infer.py").RequestPredictor(
        a.ri
    )
    inputs = json.loads((a.live / "ri-input.json").read_text())
    if (
        len(inputs) != len(run["requests"])
        or {r["request_id"] for r in inputs} != run["requests"].keys()
    ):
        raise ValueError("Incomplete or duplicate RI replay")
    policy = []
    evidence = []
    for event in inputs:
        rid = event["request_id"]
        row = run["requests"][rid]
        path = row["route"]
        p, q = sketch(path)
        shape = (
            np.minimum(31, describe_lane(p, b"/") + describe_lane(q, b"&")).astype(np.float32) / 31
        )
        x = np.r_[from_request(path, "GET"), shape].astype("<f4")
        if vector_sha(x) != row["vector_sha256"]:
            # Rust serializes f32 as shortest decimals. Ingest hashes canonical f32 bytes.
            raise ValueError("Live Rust/Python preprocessing mismatch")
        score = float(session.run(["score"], {"input": x[None, :]})[0][0])
        if abs(score - row["score"]) > 2e-5 or expected != row["model_sha256"]:
            raise ValueError("Inference disagreement")
        frame = dict(schema=SCHEMA, mode=MODE, target=path, method="GET")
        messages = "{}\n" + json.dumps(frame) + "\n"
        result = subprocess.run(
            [a.scorer, "--https-shadow", model, expected, a.ort],
            input=messages,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        refused, reloaded = map(json.loads, result.stdout.splitlines())
        if refused["status"] != "ABSTAIN" or abs(reloaded["score"] - score) > 2e-5:
            raise ValueError("Scorer restart/ABSTAIN disagreement")
        start = time.monotonic_ns()
        ri = predictor.predict(worker.model_record(event))
        duration = (time.monotonic_ns() - start) / 1e6
        if (
            ri["record_id"] != rid
            or ri["model_version"] != worker.MODEL
            or ri["research_threshold"] != worker.THRESHOLD
        ):
            raise ValueError("Unbound RI score")
        observation = dict(
            status="SCORED",
            record_id=rid,
            model_version=worker.MODEL,
            score=ri["score"],
            manifest_sha256=worker.MANIFEST_SHA,
            feature_profile="selected_headers_no_body",
            threshold=worker.THRESHOLD,
            latency_ms=duration,
        )
        # Only generation/flow/tx-bound alerts captured by the private passive sensor.
        policy.append(
            dict(
                request_id=rid,
                request_ai=observation,
                rules=row["sensor_rules"],
                correlation=dict(status="MATCHED", late_event="S" not in row["mask_at_cutoff"]),
            )
        )
        evidence.append(
            dict(
                request_id=rid,
                projection_equal=True,
                max_score_error=abs(score - row["score"]),
                score=score,
                ri_v2_score=ri["score"],
                ri_replay_ms=duration,
                scorer_restart="PASS",
                malformed="ABSTAIN",
            )
        )
    (a.live / "policy-input.json").write_text(json.dumps(policy))
    output = a.live / "policy-output.json"
    run_test = subprocess.run(
        [a.policy_test, "--exact", "r35_observed_https_policy", "--ignored"],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ
        | dict(R35_POLICY_INPUT=str(a.live / "policy-input.json"), R35_POLICY_OUTPUT=str(output)),
    )
    if "1 passed" not in run_test.stdout:
        raise ValueError("Policy test was not executed")
    print(
        json.dumps(
            dict(
                parity=evidence,
                hybrid=json.loads(output.read_bytes()),
                scope="POST_OBSERVATION_REPLAY",
                field_coverage="Passive local benign canary; no attack label or automatic action",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("live", "bundle", "ri", "scorer", "ort", "policy-test"):
        p.add_argument("--" + opt, type=Path, required=True)
    replay(p.parse_args())

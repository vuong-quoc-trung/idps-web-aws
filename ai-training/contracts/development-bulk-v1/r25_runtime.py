"""Isolated Rust/Python URI100 tensor parity, restart and ABSTAIN acceptance."""

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import onnxruntime

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256
from idps_ai.export.onnx import cpu_session
from r18_data import check, read
from r25_features import VERSION

SCHEMA = "idps-request-time-uri76-shape-r23-v1"


def run(out):
    binary = REPO_ROOT / "security-web/target/debug/idps-r25-tensor-shadow"
    runtime = next((Path(onnxruntime.__file__).parent / "capi").glob("libonnxruntime.so.*"))
    spec = read(out / "model-selection.json")["models"]["WARM_SWIGLU_URI100"]
    model = Path(spec["onnx"])
    check(file_sha256(model) == spec["sha256"], "Rust model binding")
    with np.load(out / "publisher-r25-uri132.npz", allow_pickle=False) as d:
        x = np.unique(d["tune_x"][:, :100], axis=0)
    x = x[np.random.default_rng(2501).choice(len(x), 256, replace=False)]
    envelope = lambda row: {"version": SCHEMA, "source": "OFFLINE_TENSOR_REPLAY", "vectors": row.tolist()}
    inputs = [envelope(row) for row in x]
    bad = [
        {**inputs[0], "version": VERSION},
        {**inputs[0], "source": "UNTRUSTED_SOURCE"},
        {**inputs[0], "vectors": inputs[0]["vectors"][:76]},
        {**inputs[0], "unexpected": True},
        {**inputs[0], "vectors": [None] * 100},
    ]
    payload = "\n".join(json.dumps(row, allow_nan=False) for row in inputs + bad + [inputs[0]]) + "\n"
    command = [str(binary), str(model), spec["sha256"], str(runtime)]
    reference = cpu_session(model, 1).run(["score"], {"input": x})[0]
    timings, scores, loads = [], [], []
    for _ in range(3):
        child = subprocess.run(command, input=payload, text=True, capture_output=True, check=True, timeout=20)
        rows = [json.loads(row) for row in child.stdout.splitlines()]
        check(len(rows) == len(inputs) + len(bad) + 1, "Rust response count")
        check(all(r["status"] == "ABSTAIN" for r in rows[256:-1]), "Invalid envelope fail-closed")
        check(rows[-1]["status"] == "SCORED", "Malformed-frame recovery")
        check(all(r["model_sha256"] == spec["sha256"] and not r["hybrid_allowed"] for r in rows[:256]), "Rust model provenance")
        actual = np.array([r["score"] for r in rows[:256]], np.float32)
        np.testing.assert_allclose(actual, reference, rtol=1e-5, atol=1e-6)
        scores.append(actual)
        timings.extend(r["inference_ns"] for r in rows[8:256])
        loads.append(rows[0]["model_load_ns"])
    for repeat in scores[1:]:
        np.testing.assert_array_equal(repeat, scores[0])
    invalid_sha = subprocess.run([str(binary), str(model), "0" * 64, str(runtime)], input="", text=True, capture_output=True, timeout=10)
    missing = subprocess.run([str(binary), str(out / "missing.onnx"), spec["sha256"], str(runtime)], input="", text=True, capture_output=True, timeout=10)
    check(invalid_sha.returncode != 0 and missing.returncode != 0, "Invalid load rejected")
    atomic_json(out / "runtime.json", {
        "state": "PASS_OFFLINE_TENSOR_PARITY",
        "evidence_scope": "No HTTP, receiver, native request ID or availability proof created",
        "http_requests": 0,
        "schema": SCHEMA,
        "width": 100,
        "vectors_per_process": 256,
        "fresh_processes": 3,
        "max_abs_rust_python": float(np.max(np.abs(scores[0] - reference))),
        "restart_scores": "BIT_EXACT",
        "invalid_envelope_abstain": len(bad),
        "valid_frame_after_abstain": "PASS",
        "wrong_sha_missing_model": "REJECTED",
        "warm_batch1_ns_p50_p95": np.percentile(timings, [50, 95]).tolist(),
        "model_load_ns_three_processes": loads,
        "model_sha256": spec["sha256"],
        "binary_sha256": file_sha256(binary),
        "runtime_library_sha256": file_sha256(runtime),
        "rust_source_sha256": file_sha256(Path(__file__).with_name("r25_rust") / "src/main.rs"),
        "cargo_lock_sha256": file_sha256(Path(__file__).with_name("r25_rust") / "Cargo.lock"),
        "raw_target_rust_preprocessing": "PENDING",
        "local_http_shadow": "NOT_ACTIVATED_QUALITY_GENERALIZATION_FAILED",
        "serving_ri_v2_and_r20_shadow": "UNCHANGED",
    })


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)

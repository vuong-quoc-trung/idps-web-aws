"""Cross-check Rust feature extraction and ONNX against the committed Local timing trace."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import onnxruntime

from idps_ai.common import atomic_json, file_sha256, load_json
from idps_ai.features.request_time import from_request

HERE = Path(__file__).resolve().parent


def verify(run):
    trace = load_json(run / "live.json")
    env = dict(
        os.environ,
        CARGO_TARGET_DIR=str(run / "cargo"),
        CARGO_BUILD_JOBS="1",
        CARGO_INCREMENTAL="0",
        RUSTFLAGS="-Ccodegen-units=1",
        RAYON_NUM_THREADS="1",
    )
    cargo = Path.home() / ".cargo/bin/cargo"
    subprocess.run(
        [
            "taskset",
            "-c",
            str(min(os.sched_getaffinity(0))),
            cargo,
            "build",
            "--locked",
            "--offline",
            "--manifest-path",
            HERE / "rust_probe/Cargo.toml",
        ],
        env=env,
        check=True,
        timeout=180,
    )
    binary = run / "cargo/debug/idps-r33-prefix-probe"
    library = next((Path(onnxruntime.__file__).parent / "capi").glob("libonnxruntime.so.*"))
    rows = trace["evidence"][3:]
    import hashlib

    ids = {
        hashlib.sha256(from_request(k, "GET").astype("<f4").tobytes()).hexdigest(): v
        for k, v in {"/api/catalog": 1, "/api/topics": 2, "/api/library": 3}.items()
    }
    inputs = ["invalid"] + [
        f"{i % 2} {r['arrived_ns'] // 1000000000} {ids[r['uri76_sha']]}" for i, r in enumerate(rows)
    ]
    cmd = [str(binary), str(run / "session-head.onnx"), trace["onnx_sha"], str(library)]

    def replay():
        return subprocess.run(
            cmd,
            input="\n".join(inputs) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=8,
        ).stdout.splitlines()

    out = replay()
    if out != replay() or out[0] != "ABSTAIN" or len(out) != len(inputs):
        raise ValueError("restart or malformed input failed")
    errors = []
    vector_errors = []
    for line, row in zip(out[1:], rows, strict=True):
        if row["history"] is None:
            if line != "ABSTAIN":
                raise ValueError("invented prefix")
            continue
        v, p = line.rsplit(" ", 1)
        vector_errors.append(
            float(
                np.max(
                    np.abs(
                        np.array(json.loads(v), dtype=np.float32)
                        - np.array(row["history"], dtype=np.float32)
                    )
                )
            )
        )
        errors.append(abs(float(p) - row["score"]))
    invalid = subprocess.run(
        cmd[:2] + ["0" * 64] + cmd[3:], text=True, input="", capture_output=True, timeout=8
    )
    if max(vector_errors) > 1e-6 or max(errors) > 2e-6 or invalid.returncode == 0:
        raise ValueError("model parity or pin failure")
    atomic_json(
        run / "rust-parity.json",
        {
            "feature_max_abs": max(vector_errors),
            "onnx_max_abs": max(errors),
            "scores": len(errors),
            "short_prefix": len(rows) - len(errors),
            "bad_sha_refused": True,
            "malformed_abstain": True,
            "restart_bit_exact": True,
            "binary_sha": file_sha256(binary),
            "ort_sha": file_sha256(library),
            "model_sha": trace["onnx_sha"],
        },
    )


if __name__ == "__main__":
    verify(Path(sys.argv[1]))

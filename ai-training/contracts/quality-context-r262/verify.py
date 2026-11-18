"""Raw evidence-envelope parity with restart/invalid-frame recovery, no model fit."""

import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from context import CATEGORIES, ROLES, STATES, encode


def fixture(role="STUDENT", category="STUDENT_DIRECTORY", mask="NSA"):
    o = {
        "request_key": "request-a",
        "scope": "guest-boot-a",
        "event_id": "a1234567-1234-1234-1234-123456789abc",
        "proof_sha256": "a" * 64,
        "receipt_offset_ns": 10_000_000,
        "available_offset_ns": 11_000_000,
        "role": role,
        "actor_session_bound": role is not None,
        "anonymous": role is None,
        "phase": "CURRENT_REQUEST_AUDIT",
    }
    b = {k: o[k] for k in ("request_key", "scope", "event_id", "proof_sha256")}
    b |= {
        "identity_verified": True,
        "clock_valid": True,
        "source_mask": mask,
        "category": category,
        "method": "GET",
        "disposition": STATES[0],
    }
    return {"observation": o, "binding": b}


def frames():
    values = []
    for role in (*ROLES, None):
        for category in CATEGORIES:
            for mask in ("N", "S", "A", "NS", "NA", "SA", "NSA", "NONE"):
                for state in STATES:
                    value = fixture(role, category, mask)
                    value["binding"]["disposition"] = state
                    values.append(value)
    for key, value in (
        ("request_key", "request-b"),
        ("scope", "boot-b"),
        ("proof_sha256", "b" * 64),
        ("event_id", "BAD"),
        ("phase", "PRIOR_SESSION_SNAPSHOT"),
        ("receipt_offset_ns", -1),
        ("available_offset_ns", 999_000_000),
        ("available_offset_ns", 999_000_001),
        ("available_offset_ns", 1_100_000_000),
        ("anonymous", True),
        ("role", "CLIENT_ADMIN"),
    ):
        f = fixture()
        f["observation"][key] = value
        values.append(f)
    for key, value in (
        ("clock_valid", False),
        ("identity_verified", False),
        ("method", "POST"),
        ("disposition", "INVALID"),
        ("source_mask", "NONE"),
    ):
        f = fixture()
        f["binding"][key] = value
        values.append(f)
    f = fixture()
    f["observation"] = None
    values.append(f)
    f = fixture()
    f["observation"]["oracle_label"] = "ATTACK_VERIFIED"
    values.append(f)
    for invalid in (None, [], "client-role", 7):
        f = fixture()
        f["binding"] = invalid
        values.append(f)
        if invalid is not None:
            f = fixture()
            f["observation"] = invalid
            values.append(f)
    return values


def run(out):
    repo = Path(__file__).resolve().parents[3]
    binary = repo / "security-web/target/debug/idps-r262-context"
    values = frames()
    expected = [encode(f["observation"], f["binding"]) for f in values]
    text = "".join(json.dumps(v, separators=(",", ":")) + "\n" for v in values)
    runs = []
    for _ in range(3):
        start = time.perf_counter_ns()
        proc = subprocess.run(
            [str(binary)], input=text, capture_output=True, text=True, timeout=30, check=True
        )
        duration = time.perf_counter_ns() - start
        results = list(map(json.loads, proc.stdout.splitlines()))
        if results != expected:
            bad = next(
                (i for i, (a, b) in enumerate(zip(results, expected)) if a != b), len(results)
            )
            raise ValueError(
                f"Rust/Python context parity mismatch at {bad}: {values[bad]} {results[bad]} {expected[bad]}"
            )
        runs.append(
            {
                "inputs": len(values),
                "wall_ns": duration,
                "ns_per_input_with_process_startup": duration // len(values),
                "output_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
            }
        )
    if len({r["output_sha256"] for r in runs}) != 1:
        raise ValueError("Restart determinism failed")
    invalid = "not-json\n{}\n" + json.dumps(fixture()) + "\n"
    proc = subprocess.run(
        [str(binary)], input=invalid, capture_output=True, text=True, check=True, timeout=10
    )
    results = list(map(json.loads, proc.stdout.splitlines()))
    if [r["status"] for r in results] != ["ABSTAIN", "ABSTAIN", "CONTEXT_AVAILABLE"]:
        raise ValueError("Invalid-frame recovery failed")
    # Pipe per-frame warm timing includes serialization and IPC. No production
    # inference/load benchmark claim is made from this bounded projection probe.
    process = subprocess.Popen(
        [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
    )
    times = []
    current = encode(fixture()["observation"], fixture()["binding"])
    try:
        for _ in range(100):
            began = time.perf_counter_ns()
            process.stdin.write(json.dumps(fixture()) + "\n")
            process.stdin.flush()
            if json.loads(process.stdout.readline()) != current:
                raise ValueError("Warm pipe parity")
            times.append(time.perf_counter_ns() - began)
    finally:
        process.stdin.close()
        process.wait(timeout=5)
        process.stdout.close()
    output = {
        "state": "PASS",
        "schema": "idps-trusted-context20-r262-v1",
        "frames": len(values),
        "runs": runs,
        "max_vector_error": 0,
        "restart_bit_exact": True,
        "malformed_abstain_recovery": True,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "projection_ipc_warm_p50_ms": statistics.median(times) / 1e6,
        "projection_ipc_warm_p95_ms": sorted(times)[94] / 1e6,
        "scope": "SYNTHETIC_CONTEXT_CONTRACT_NOT_NATIVE_QUALITY",
    }
    (out / "context-runtime.json").write_text(json.dumps(output, indent=2) + "\n")
    (out / "golden-context.jsonl").write_text(
        "".join(json.dumps({"input": f, "output": e}) + "\n" for f, e in zip(values, expected))
    )
    print(json.dumps(output))


if __name__ == "__main__":
    os.umask(0o077)
    run(Path(sys.argv[1]))

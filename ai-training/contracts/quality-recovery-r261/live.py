# isort: skip_file

"""Bounded Local protocol liveness, explicitly synthetic and never native capture."""

import json
import os
import socket
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


from common import atomic_json, check, file_sha256, output_arg
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request, schema


def service(name):
    r = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            f"idps-r22-local-{name}.service",
            "-p",
            "MainPID",
            "-p",
            "ActiveState",
            "-p",
            "NRestarts",
            "-p",
            "ControlGroup",
            "-p",
            "InvocationID",
        ],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    d = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    root = Path("/sys/fs/cgroup") / d["ControlGroup"].lstrip("/")
    d["kernel"] = {
        n: (root / n).read_text().strip()
        for n in ("cpu.max", "memory.max", "memory.current", "memory.swap.max", "pids.max")
    }
    child = root / "ai-worker"
    if child.exists():
        d["guarded_worker_cpu.max"] = (child / "cpu.max").read_text().strip()
        d["guarded_worker_pids"] = (child / "cgroup.procs").read_text().split()
    check(d["ActiveState"] == "active" and d["MainPID"] != "0", "Local service not active")
    return d


def score(sock_path, frame):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(str(sock_path))
        sock.sendall(json.dumps(frame).encode() + b"\n")
        return json.loads(sock.makefile("rb").readline(4096))


def run(out):
    state = Path.home() / ".local/state/idps-r22-local"
    before = {name: service(name) for name in ("ri", "scorer", "collector", "receiver")}
    spec = schema()
    vector = from_request("/api/auth/csrf", "GET")
    frame = {
        "request_id": uuid.uuid4().hex,
        "version": spec["version"],
        "transform_sha256": spec["transform_sha256"],
        "source": "NGINX_REQUEST_MIRROR",
        "vectors": vector.tolist(),
    }
    path = Path(os.environ["XDG_RUNTIME_DIR"]) / "idps-r22-local-scorer/score.sock"
    first = score(path, frame)
    invalid = score(path, frame | {"transform_sha256": "0" * 64})
    again = score(path, frame | {"request_id": uuid.uuid4().hex})
    check(invalid.get("status") == "ABSTAIN", "Invalid schema was not refused")
    check(
        first.get("hybrid_allowed") is False and first["score"] == again["score"],
        "Shadow mode or recovery failed",
    )
    model = state / "bundle/swiglu.onnx"
    check(file_sha256(model) == first["model_sha256"], "Live model SHA mismatch")
    reference = float(cpu_session(model, 1).run(["score"], {"input": vector[None, :]})[0][0])
    check(abs(reference - first["score"]) <= 1e-7, "Live scorer Python parity mismatch")
    # A project-owned synthetic UDS message exercises RI v2; it is never sent as HTTP,
    # never enters the mirror receiver/evidence store and carries no trusted-ID claim.
    rid = uuid.uuid4().hex
    stamp = datetime.now(UTC).isoformat()
    envelope = {
        "schema_version": "nginx-ai-1",
        "request_id": rid,
        "timestamp": stamp,
        "method": "GET",
        "url": "/api/auth/csrf",
        "headers": {
            "User-Agent": "R261SyntheticUDSLiveness",
            "Accept": "application/json",
            "Content-Type": "",
        },
    }
    journal = state / "ri-v2.jsonl"
    offset = journal.stat().st_size
    ri_path = Path(os.environ["XDG_RUNTIME_DIR"]) / "idps-r22-local-ri/ri.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.sendto(b"ai_shadow: " + json.dumps(envelope).encode(), str(ri_path))
    found = None
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with journal.open("rb") as f:
            f.seek(offset)
            for line in f:
                row = json.loads(line)
                if row.get("request_id") == rid:
                    found = row
        if found:
            break
        time.sleep(0.1)
    check(
        found is not None
        and found["kind"] == "inference"
        and found["status"] == "SCORED"
        and found["enforcement_actions"] == 0,
        "RI v2 liveness inference not corroborated",
    )
    time.sleep(3.2)
    after = {name: service(name) for name in before}
    check(
        all(
            after[name]["MainPID"] == before[name]["MainPID"]
            and after[name]["NRestarts"] == before[name]["NRestarts"]
            for name in before
        ),
        "Unexpected Local service restart during liveness probe",
    )
    atomic_json(
        out / "local-acceptance.json",
        {
            "state": "PASS_SCOPED_LIVENESS",
            "before": before,
            "after": after,
            "R20_live_model_sha256": first["model_sha256"],
            "R20_score": first["score"],
            "R20_python_max_abs": abs(reference - first["score"]),
            "RI_v2_liveness": {
                "status": found["status"],
                "model_version": found["model_version"],
                "manifest_sha256": found["manifest_sha256"],
                "score": found["score"],
                "latency_ms": found["latency_ms"],
                "enforcement_actions": 0,
            },
            "fixture_rid": rid,
            "fixture_scope": "SYNTHETIC_UDS_PROTOCOL_ONLY_NOT_HTTP_NOT_TRUSTED_REQUEST_EVIDENCE",
            "ABSTAIN_then_valid_recovery": "PASS",
            "intentional_service_restart": False,
            "restart_rollback_regression": "Unchanged R22.1 controlled restart/rollback evidence reused, not rerun against serving services",
            "HTTP_requests": 0,
            "native_training_samples_added": 0,
            "R261_candidate_not_installed": True,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

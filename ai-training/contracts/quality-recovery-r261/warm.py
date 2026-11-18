# isort: skip_file

"""Five bounded RI protocol fixtures to separate first-use and warm latency."""

import json
import os
import socket
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from common import atomic_json, check, output_arg, read


def run(out):
    state = Path.home() / ".local/state/idps-r22-local"
    journal = state / "ri-v2.jsonl"
    records = []
    for _ in range(5):
        offset = journal.stat().st_size
        rid = uuid.uuid4().hex
        envelope = {
            "schema_version": "nginx-ai-1",
            "request_id": rid,
            "timestamp": datetime.now(UTC).isoformat(),
            "method": "GET",
            "url": "/api/auth/csrf",
            "headers": {
                "User-Agent": "R261SyntheticUDSWarm",
                "Accept": "application/json",
                "Content-Type": "",
            },
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(
                b"ai_shadow: " + json.dumps(envelope).encode(),
                str(Path(os.environ["XDG_RUNTIME_DIR"]) / "idps-r22-local-ri/ri.sock"),
            )
        end = time.monotonic() + 5
        found = None
        while time.monotonic() < end:
            with journal.open("rb") as stream:
                stream.seek(offset)
                for line in stream:
                    row = json.loads(line)
                    if row.get("request_id") == rid:
                        found = row
            if found:
                break
            time.sleep(0.02)
        check(
            found is not None and found["status"] == "SCORED" and found["enforcement_actions"] == 0,
            "Warm RI liveness failed",
        )
        records.append(
            {
                key: found[key]
                for key in ("request_id", "score", "latency_ms", "model_version", "manifest_sha256")
            }
        )
        time.sleep(0.15)
    cold = read(out / "local-acceptance.json")["RI_v2_liveness"]["latency_ms"]
    atomic_json(
        out / "ri-warm-latency.json",
        {
            "scope": "SYNTHETIC_UDS_PROTOCOL_NOT_HTTP_NOT_T07_LOAD_TEST",
            "first_use_after_boot_probe_ms": cold,
            "warm_n": len(records),
            "warm_latency_p50_p95_ms": np.quantile(
                [r["latency_ms"] for r in records], [0.5, 0.95]
            ).tolist(),
            "records": records,
            "new_HTTP_requests": 0,
            "native_training_samples_added": 0,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

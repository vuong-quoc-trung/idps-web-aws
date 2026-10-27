"""Deterministic format-compatible S0 fixtures, not a real/representative corpus."""

import hashlib
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from idps_ai.common import CLASSES, PipelineError, atomic_json, file_sha256


def synthetic_s0(output, seed=17, campaigns=15, requests_per_campaign=64):
    output = Path(output)
    if output.exists():
        raise PipelineError("Synthetic output already exists; use a fresh S0 directory")
    if campaigns < 10 or requests_per_campaign < 16:
        raise PipelineError(
            "S0 needs at least 10 independent campaigns and 16 requests per campaign"
        )
    output.mkdir(parents=True, mode=0o700)
    rng = random.Random(seed)
    files = {
        name: (output / name).open("w")
        for name in ("student-audit.log", "access.log", "eve.json", "labels.jsonl")
    }
    try:
        for campaign in range(campaigns):
            ip = f"192.0.2.{campaign + 1}"
            user = "hmac-sha256:" + hashlib.sha256(f"fake-user-{campaign}".encode()).hexdigest()
            session = (
                "hmac-sha256:" + hashlib.sha256(f"fake-session-{campaign}".encode()).hexdigest()
            )
            start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=campaign * 1200)
            families = list(range(len(CLASSES))) * ((requests_per_campaign + 7) // 8)
            rng.shuffle(families)
            for i in range(requests_per_campaign):
                family = CLASSES[families[i]]
                rid = uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-{seed}-{campaign}-{i}").hex
                timestamp = start + timedelta(seconds=i * 1.5 + rng.random() * 0.1)

                def iso(delta=0):
                    return (timestamp + timedelta(seconds=delta)).isoformat().replace("+00:00", "Z")

                path = (
                    "/api/auth/login"
                    if family == "brute_force"
                    else rng.choice(
                        ("/api/students/[id]", "/api/faculties", "/api/me/profile", "/api/classes")
                    )
                )
                method = (
                    "POST"
                    if family == "brute_force"
                    else rng.choice(("GET", "HEAD", "OPTIONS", "POST", "PUT"))
                )
                status = (
                    401
                    if family == "brute_force"
                    else rng.choice((200, 200, 201, 400, 403, 404, 500))
                )
                role = rng.choice(("ADMIN", "STAFF", "STUDENT"))
                ua = rng.choice(("Mozilla Chrome Safari", "Mozilla Firefox", "curl"))
                student = {
                    "schema_version": "1.0",
                    "event_id": str(uuid.UUID(rid)),
                    "source": "STUDENT_AUDIT",
                    "source_instance": "synthetic-student",
                    "timestamp": iso(),
                    "request_id": rid,
                    "client_ip": ip,
                    "peer_ip": "127.0.0.1",
                    "user_id": user,
                    "username": user,
                    "role": role,
                    "session_hmac": session,
                    "http_method": method,
                    "uri_path": path,
                    "query_string": "page=[REDACTED]&q=[REDACTED]",
                    "status_code": status,
                    "latency_ms": rng.randrange(1, 200),
                    "user_agent": ua,
                    "event_type": "http_request",
                    "outcome": "failure" if status >= 400 else "success",
                    "dest_ip": None,
                    "src_port": None,
                    "dest_port": None,
                    "transport": "HTTP",
                    "flow_id": None,
                    "request_bytes": None,
                    "response_bytes": None,
                    "flow": None,
                    "redacted": True,
                    "truncated": False,
                }
                nginx = {
                    "schema_version": "1.0",
                    "source": "nginx_access",
                    "timestamp": iso(0.02),
                    "request_id": rid,
                    "client_ip": ip,
                    "http_method": method,
                    "uri_path": path,
                    "query_string": None,
                    "status": status,
                    "latency_seconds": student["latency_ms"] / 1000,
                    "request_bytes": 256,
                    "response_bytes": 512,
                    "user_agent": ua,
                    "rule_signals": {
                        "SQLI": int(family == "sqli"),
                        "XSS": int(family == "xss"),
                        "PATH_TRAVERSAL": int(family == "path_traversal"),
                        "COMMAND_INJECTION": int(family == "cmd_injection"),
                    },
                }
                eve = {
                    "timestamp": iso(0.04),
                    "event_type": "http",
                    "src_ip": ip,
                    "dest_ip": "192.0.2.250",
                    "src_port": 30000 + i,
                    "dest_port": 80,
                    "proto": "TCP",
                    "flow_id": 9007199254740993 + campaign * 1000 + i,
                    "http": {
                        "http_method": method,
                        "url": path,
                        "status": status,
                        "length": 512,
                        "http_user_agent": ua,
                        "request_id": rid,
                    },
                }
                label = {
                    "request_id": rid,
                    "campaign_id": f"synthetic-campaign-{campaign}",
                    "label": int(family != "benign"),
                    "attack_family": family,
                    "label_source": "scenario_manifest",
                    "label_confidence": 1.0,
                    "review_status": "approved",
                }
                for name, value in (
                    ("student-audit.log", student),
                    ("access.log", nginx),
                    ("eve.json", eve),
                    ("labels.jsonl", label),
                ):
                    files[name].write(json.dumps(value, sort_keys=True) + "\n")
                if i % 4 == 0:
                    flow = {
                        "timestamp": iso(0.03),
                        "event_type": "flow",
                        "src_ip": ip,
                        "dest_ip": "192.0.2.250",
                        "proto": "TCP",
                        "flow_id": eve["flow_id"],
                        "flow": {
                            "age": 0.2,
                            "bytes_toserver": 256,
                            "bytes_toclient": 512,
                            "pkts_toserver": 2,
                            "pkts_toclient": 3,
                            "state": "closed",
                        },
                    }
                    files["eve.json"].write(json.dumps(flow, sort_keys=True) + "\n")
                if family != "benign" and i % 3 == 0:
                    alert = {
                        **eve,
                        "timestamp": iso(0.03),
                        "event_type": "alert",
                        "alert": {
                            "signature_id": 1000002,
                            "severity": 2,
                            "signature": "Synthetic S0 alert",
                        },
                    }
                    files["eve.json"].write(json.dumps(alert, sort_keys=True) + "\n")
    finally:
        for stream in files.values():
            stream.close()
    key = output / "redaction.key"
    key.write_bytes(os.urandom(32))
    for file in output.iterdir():
        os.chmod(file, 0o600)
    report = {
        "synthetic": True,
        "purpose": "S0 pipeline/resume verification only; not model quality evidence",
        "seed": seed,
        "campaigns": campaigns,
        "requests": campaigns * requests_per_campaign,
        "files": {name: file_sha256(output / name) for name in files},
        "classes": list(CLASSES),
    }
    atomic_json(output / "synthetic_manifest.json", report)
    return report

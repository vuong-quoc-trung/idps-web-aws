#!/usr/bin/env python3
"""Small terminal client for the real local HTTP/AI/policy API. No fake scores."""

import argparse
import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from idps_ai.common import atomic_json
from idps_ai.training.heartbeat import process_identity

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / ".local-dev/demo-v1"
POINTER = REPO / ".local-dev/demo-session.json"


def load(path):
    return json.loads(path.read_text())


def request(path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(
        "http://127.0.0.1:3001" + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(r, timeout=15) as response:
        return json.load(response)


def token():
    secret = load(RUNTIME / "credentials.json")
    return request(
        "/api/auth/login",
        {"username": "admin", "password": secret["security_admin_password"]},
    )["token"]


def start(listen="127.0.0.1", allow_cidr="127.0.0.0/8"):
    spec = importlib.util.spec_from_file_location(
        "demo_sensor", REPO / "scripts/three-source-shadow.py"
    )
    sensor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sensor)
    sensor.gateway_network(listen, allow_cidr)
    with (REPO / ".local-dev/hybrid-acceptance.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if POINTER.exists():
        current = load(POINTER)
        if process_identity(current["pid"]) == current.get("start_ticks"):
            raise RuntimeError("Existing demo supervisor alive; use health/status/stop")
    root = REPO / ".local-dev" / ("demo-session-" + str(time.time_ns())[-12:])
    with (REPO / ".local-dev/demo-session-launch.log").open("ab") as log:
        p = subprocess.Popen(
            [
                sys.executable,
                str(REPO / "scripts/hybrid-system-acceptance.py"),
                "--action",
                "demo",
                "--root",
                str(root),
            ],
            cwd=REPO,
            env=os.environ
            | {
                "IDPS_DEMO_RUNTIME": str(RUNTIME),
                "IDPS_DEMO_CONTAINER_PREFIX": "idps-demo-v1",
                "IDPS_DEMO_LISTEN": listen,
                "IDPS_DEMO_ALLOW_CIDR": allow_cidr,
            },
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    atomic_json(
        POINTER,
        {"root": str(root), "pid": p.pid, "start_ticks": process_identity(p.pid)},
    )
    print(
        json.dumps(
            {
                "state": "STARTING_NOT_YET_READY",
                "supervisor_pid": p.pid,
                "status": str(root / "wrapper-status.json"),
                "log": str(REPO / ".local-dev/demo-session-launch.log"),
            },
            indent=2,
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=[
            "start",
            "health",
            "normal",
            "test",
            "ai",
            "rules",
            "policy",
            "incident",
            "history",
            "response",
            "status",
            "stop",
            "manual-proof",
        ],
    )
    p.add_argument("--request-id")
    p.add_argument(
        "--listen", default="127.0.0.1", help="Specific host LAN IPv4; default loopback"
    )
    p.add_argument(
        "--allow-cidr", default="127.0.0.0/8", help="Authorized private lab subnet only"
    )
    p.add_argument("--operator-approved-isolated-client", action="store_true")
    a = p.parse_args()
    os.umask(0o077)
    if a.action == "start":
        start(a.listen, a.allow_cidr)
        return
    if a.action in ["status", "stop", "manual-proof"]:
        pointer = (
            POINTER if POINTER.exists() else REPO / ".local-dev/demo-acceptance.json"
        )
        session = load(pointer)
        root = Path(session["root"])
        if a.action == "status":

            def read(name):
                return load(root / name) if (root / name).exists() else {}

            final = read("final-status.json")
            wrapper = read("wrapper-status.json")
            current = read("worker-status.json")
            guard = read("guard/resource-status.json")
            alive = process_identity(session["pid"]) == session.get("start_ticks")
            print(
                json.dumps(
                    {
                        "run_id": root.name,
                        "supervisor_alive": alive,
                        "supervisor": read("supervisor.json"),
                        "phase": current.get("phase")
                        if current.get("state") == "RUNNING"
                        else wrapper.get("phase"),
                        "heartbeat_age_seconds": round(
                            time.time()
                            - read("supervisor-heartbeat.json").get(
                                "heartbeat", time.time()
                            ),
                            1,
                        ),
                        "guard": guard,
                        "demo": read("demo-ready.json"),
                        "local_release": final.get(
                            "local_release", "RUNNING" if alive else "STOPPED"
                        ),
                        "gates": final.get("gates"),
                        "failures": final.get("failures"),
                        "operator_proof": read("operator-proof-status.json"),
                        "evidence_directory": str(root),
                    },
                    indent=2,
                )
            )
            return
        if process_identity(session["pid"]) != session.get("start_ticks"):
            raise RuntimeError("Demo is already stopped; no process signaled")
        if a.action == "stop":
            (root / "STOP").touch(mode=0o600)
            print("GRACEFUL_STOP_REQUESTED; kiểm tra status, không xóa logs/DB")
            return
        if not a.operator_approved_isolated_client:
            raise RuntimeError(
                "Explicit --operator-approved-isolated-client required for actual firewall test"
            )
        if not (root / "demo-ready.json").exists():
            raise RuntimeError("Demo not ready")
        atomic_json(
            root / "OPERATOR_PROOF_REQUEST.json",
            {
                "operator_uid": os.getuid(),
                "approved_at": time.time(),
                "target": "DISPOSABLE_NAMESPACE_CLIENT_10.203.17.2_ONLY",
                "ttl_seconds": [15, 4],
                "actions": ["BLOCK", "UNBLOCK", "TTL_EXPIRY"],
                "host_firewall": False,
            },
        )
        print(
            "OPERATOR_APPROVAL_QUEUED; kết quả sẽ lưu trong status. Không tác động host firewall."
        )
        return
    if a.action == "health":
        value = request("/health")
        ai = request("/api/ai-shadow?limit=1", token=token())
        print(
            json.dumps(
                {
                    "Rust": value,
                    "AI_worker": ai["worker"],
                    "mode": ai["mode"],
                    "enforcement": ai["enforcement"],
                },
                indent=2,
            )
        )
        return
    if a.action in ["normal", "test"]:
        session = load(POINTER)
        root = Path(session["root"])
        assert (root / "demo-ready.json").exists(), "Demo gateway not ready"
        query = (
            ""
            if a.action == "normal"
            else "?" + urllib.parse.urlencode({"search": "1' OR 1=1--"})
        )
        gateway = load(root / "demo-ready.json")["gateway"]
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            gateway + "/api/auth/csrf" + query, timeout=20
        ) as response:
            response.read()
            value = {
                "case": a.action,
                "http_status": response.status,
                "request_id": response.headers["X-Request-Id"],
                "gateway": "NGINX via isolated passive Suricata gateway",
                "time": time.time(),
                "scope": "harmless query to existing CSRF endpoint; no exploit-success claim",
            }
        atomic_json(RUNTIME / "last-demo-receipt.json", value)
        print(json.dumps(value, indent=2))
        return
    if a.action == "history":
        print(json.dumps(request("/api/hybrid-incidents", token=token()), indent=2))
        return
    rid = a.request_id or load(RUNTIME / "last-demo-receipt.json")["request_id"]
    if len(rid) != 32 or any(c not in "0123456789abcdef" for c in rid):
        raise RuntimeError("Invalid request_id")
    auth = token()
    if a.action in ["ai", "rules"]:
        page = request("/api/ai-shadow?request_id=" + rid, token=auth)
        value = page["items"] if a.action == "ai" else page["detectors"]
        presentation = None
        if a.action == "ai":
            incidents = request("/api/hybrid-incidents?request_id=" + rid, token=auth)[
                "incidents"
            ]
            incident = incidents[0] if incidents else None
            presentation = [
                {
                    "REQUEST_ID": v["request_id"],
                    "INCIDENT_ID": incident["request_id"] if incident else None,
                    "INCIDENT_ID_SEMANTICS": "actual hybrid_incidents primary key request_id",
                    "MODEL_ID": v["model_version"],
                    "MODEL_VERSION": v["model_version"],
                    "FEATURE_SCHEMA_VERSION": v["feature_profile"],
                    "EVENT_SCHEMA_VERSION": v["schema_version"],
                    "AI_SCORE": v["score"],
                    "AI_THRESHOLD": v["threshold"],
                    "AI_SIGNAL": "AI_UNAVAILABLE"
                    if v["score"] is None
                    else "ABOVE_THRESHOLD_UNCALIBRATED"
                    if v["above_threshold"]
                    else "BELOW_THRESHOLD_UNCALIBRATED",
                    "INFERENCE_STATUS": v["status"],
                    "INFERENCE_LATENCY_MS": v["latency_ms"],
                    "SOURCE_EVIDENCE_IDS": incident["evidence_ids"]
                    if incident
                    else ["ai:" + v["event_id"]],
                }
                for v in value
            ]
        print(
            json.dumps(
                {
                    "request_id": rid,
                    "incident_key": "request_id is the actual hybrid_incidents primary key",
                    "kind": "REAL_PERSISTED_INFERENCE"
                    if a.action == "ai"
                    else "REAL_DETECTOR_EVIDENCE",
                    "items": value,
                    "presentation_of_persisted_evidence": presentation,
                    "score_semantics": "uncalibrated research score, not attack probability",
                },
                indent=2,
            )
        )
        return
    if a.action in ["policy", "incident"]:
        print(
            json.dumps(
                request("/api/hybrid-incidents?request_id=" + rid, token=auth), indent=2
            )
        )
        return
    if a.action == "response":
        print(
            json.dumps(
                {
                    "queue_audit": request("/api/audit", token=auth),
                    "firewall": request("/api/blocked-ips", token=auth),
                    "default_mode": "OFF; manual tests require explicit operator command",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

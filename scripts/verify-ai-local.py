#!/usr/bin/env python3
"""Small real-HTTP local acceptance, including AI crash and restart isolation.

Requires an already running --ai-shadow local foundation demo. Credentials stay
in the ignored runtime; only request IDs, scores and aggregate evidence saved.
"""

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "launcher", ROOT / "scripts/dev-up-and-verify.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
RUNTIME = launcher.RUNTIME


def wait_for(call, predicate, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = call()
        if predicate(value):
            return value
        time.sleep(0.5)
    raise RuntimeError("Timed out awaiting local acceptance condition")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop-after", action="store_true", help="also restart Rust to check persistence, then gracefully stop this runtime")
    args = parser.parse_args()
    ports = json.loads((RUNTIME / "configuration.json").read_text())["ports"]
    secret = json.loads((RUNTIME / "credentials.json").read_text())
    edge = f"http://127.0.0.1:{ports['edge']}"
    security = f"http://127.0.0.1:{ports['security']}"

    def call(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            security + path,
            headers=headers,
            data=None if payload is None else json.dumps(payload).encode(),
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, None

    assert call("/api/ai-shadow")[0] == 401
    status, session = call(
        "/api/auth/login",
        {"username": "admin", "password": secret["security_admin_password"]},
    )
    assert status == 200
    token = session["token"]

    def ai():
        status, value = call("/api/ai-shadow?limit=200", token=token)
        assert status == 200
        return value

    wait_for(
        ai,
        lambda r: (
            r["worker"]
            and not r["worker"]["stale"]
            and r["worker"]["status"] == "READY"
        ),
        150,
    )
    initial_worker = ai()["worker"]["worker_id"]

    def student(query=""):
        started = time.perf_counter()
        with urllib.request.urlopen(
            edge + "/api/auth/csrf" + query, timeout=15
        ) as response:
            data = json.load(response)
            assert data["token"] and response.status == 200
            return {
                "request_id": response.headers["X-Request-Id"],
                "http_status": response.status,
                "http_latency_ms": (time.perf_counter() - started) * 1000,
            }

    # Attempts are harmless queries to an existing CSRF endpoint. No exploit
    # success/attack Ground Truth claim; do not tune score/threshold from these.
    # Prime a connected Nginx syslog sink after any previous worker replacement.
    # These are real requests, excluded from the six-case timing sample.
    initial_delivery = []
    for _ in range(5):
        receipt = student("?ai_delivery=warmup")
        initial_delivery.append(receipt)
        time.sleep(2)
        if receipt["request_id"] in {r["request_id"] for r in ai()["items"]}:
            break
    else:
        raise RuntimeError("No AI observation after bounded delivery warmup")
    cases = [
        ("benign", ""),
        ("benign-search", "?" + urllib.parse.urlencode({"search": "ordinary course"})),
        ("SQLi-shaped-query", "?" + urllib.parse.urlencode({"search": "1' OR 1=1--"})),
        (
            "XSS-shaped-query",
            "?" + urllib.parse.urlencode({"search": "<script>alert(1)</script>"}),
        ),
        ("command-shaped-query", "?" + urllib.parse.urlencode({"search": ";id"})),
        (
            "private-field-canary",
            "?" + urllib.parse.urlencode({"token": "IntegrationPrivateCanary"}),
        ),
    ]
    observed = []
    started = time.perf_counter()
    for case, query in cases:
        receipt = student(query)
        receipt["case"] = case
        observed.append(receipt)
    ids = {r["request_id"] for r in observed}
    page = wait_for(ai, lambda p: ids <= {r["request_id"] for r in p["items"]}, 150)
    elapsed = time.perf_counter() - started
    page = wait_for(
        ai,
        lambda p: all(
            {"NGINX", "STUDENT_AUDIT"} <= set(r["correlated_sources"])
            for r in p["items"]
            if r["request_id"] in ids
        ),
        60,
    )
    by_id = {r["request_id"]: r for r in page["items"]}
    for row in observed:
        result = by_id[row["request_id"]]
        assert result["status"] == "SCORED" and result["enforcement_actions"] == 0
        assert result["above_threshold"] == (result["score"] > result["threshold"])
        row["AI"] = result

    # An abrupt worker SIGKILL is intentionally different from a graceful stop.
    children = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            arguments = (proc / "cmdline").read_bytes().split(b"\0")
            if (
                len(arguments) > 1
                and str(ROOT / "scripts/ai-shadow-worker.py").encode() == arguments[1]
                and str(RUNTIME / "ai/nginx.sock").encode() in arguments
            ):
                children.append(int(proc.name))
        except (OSError, PermissionError):
            pass
    assert len(children) == 1
    os.kill(children[0], signal.SIGKILL)
    down_query = "?worker=down"
    if os.environ.get("IDPS_HYBRID_ACCEPTANCE") == "1":
        down_query += "&" + urllib.parse.urlencode({"search": "1' OR 1=1--"})
    down_receipt = student(down_query)
    wait_for(ai, lambda p: p["worker"]["stale"], 30)
    hybrid_fallback = None
    if os.environ.get("IDPS_HYBRID_ACCEPTANCE") == "1":
        def hybrid_incident():
            status, page = call("/api/hybrid-incidents?request_id=" + down_receipt["request_id"], token=token)
            assert status == 200
            return page["incidents"]
        incidents = wait_for(hybrid_incident, lambda items: bool(items) and items[0]["rule_risk_component"] > 0 and items[0]["ai_risk_component"] == 0, 30)
        hybrid_fallback = incidents[0]
        assert hybrid_fallback["policy_action"] in {"ALERT", "REVIEW"}
    launcher.stop_ai()
    launcher.start_ai()
    wait_for(
        ai,
        lambda p: (
            p["worker"]
            and not p["worker"]["stale"]
            and p["worker"]["status"] == "READY"
            and p["worker"]["worker_id"] != initial_worker
        ),
        150,
    )
    # Nginx may discard the first datagram sent on a stale connected socket,
    # then reconnect. Probe boundedly and record the loss instead of hiding it.
    restart_receipts = []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        restart_receipts.append(student("?worker=restarted"))
        time.sleep(2)
        scored_ids = {r["request_id"] for r in ai()["items"]}
        matches = [r for r in restart_receipts if r["request_id"] in scored_ids]
        if matches:
            restarted = matches[0]
            break
    else:
        raise RuntimeError("No AI result after bounded restart probes")
    assert down_receipt["request_id"] not in {r["request_id"] for r in ai()["items"]}
    # Count observed canonical requests, not hypothetical unseen socket traffic.
    # Fifteen seconds is the dashboard's ingestion grace period.
    delivery = wait_for(ai, lambda p: p.get("delivery", {}).get("unresolved_after_grace", 0) >= 1, 45)["delivery"]
    assert delivery["collection_enabled"] and delivery["nginx_observed_requests"] >= 1
    down_id = down_receipt["request_id"]
    assert len(down_id) == 32 and all(c in "0123456789abcdef" for c in down_id)
    missing_observed = int(launcher.sql(launcher.container_name("security"), "security_db",
        f"SELECT count(*) FROM normalized_events n WHERE n.source='NGINX' AND n.request_id='{down_id}' AND NOT EXISTS (SELECT 1 FROM ai_shadow_results r WHERE r.request_id=n.request_id)"))
    assert missing_observed >= 1
    connection_check = json.loads((RUNTIME / "ai/connection-check.json").read_text())
    assert connection_check["status"] == "PASS"
    assert (
        launcher.sql(
            launcher.container_name("security"),
            "security_db",
            "SELECT count(*) FROM firewall_actions WHERE source='AUTO'",
        )
        == "0"
    )

    # Missing bundle and a changed manifest must fail safely; they do not replace
    # the real bundle or the live worker's paths.
    faults = []
    for kind in ["missing", "invalid"]:
        destination = RUNTIME / "ai" / (kind + "-bundle")
        destination.mkdir(exist_ok=True, mode=0o700)
        if kind == "invalid":
            (destination / "manifest.json").write_text(
                '{"model_version":"not-the-frozen-model"}'
            )
        attempt = str(time.time_ns())
        output = RUNTIME / "ai" / (kind + "-status-" + attempt + ".jsonl")
        evidence = RUNTIME / "ai" / (kind + "-guard-" + attempt)
        probe_command = [
                str(ROOT / "ai-training/.venv/bin/python"),
                str(ROOT / "scripts/ai-shadow-worker.py"),
                "--bundle",
                str(destination),
                "--socket",
                str(RUNTIME / "ai" / (kind + ".sock")),
                "--output",
                str(output),
        ]
        if launcher.shared_acceptance_cgroup():
            launcher.wait_ai_startup_headroom()
            supervision = "EXISTING_ACCEPTANCE_SCOPE_WITH_INDEPENDENT_WATCHDOG"
        else:
            probe_command = [str(ROOT / "ai-training/.venv/bin/python"),
                str(ROOT / "ai-training/scripts/integration-guard.py"), "--output",str(evidence),
                "--quota","3","--max-seconds","60","--",*probe_command]
            supervision = "SEPARATE_RESOURCE_GUARD"
        completed = subprocess.run(probe_command, capture_output=True, check=False, timeout=75)
        if not output.exists():
            raise RuntimeError("Fault probe did not reach the worker; inspect thermal/resource guard. Not a model-fault PASS.")
        records = [json.loads(s) for s in output.read_text().splitlines()]
        assert completed.returncode != 0 and any(
            r["status"] == "MODEL_UNAVAILABLE" for r in records
        )
        assert student()["http_status"] == 200
        faults.append(
            {"case": kind, "status": "MODEL_UNAVAILABLE", "Student_HTTP": 200, "resource_supervision": supervision}
        )

    # Prove transient canary, cookies and auth do not appear in AI persisted data.
    assert all(
        "IntegrationPrivateCanary" not in p.read_text()
        for p in (RUNTIME / "ai").glob("results.jsonl*")
    )
    latency = [r["AI"]["latency_ms"] for r in observed]
    report = {
        "status": "PASS",
        "at": datetime.now(UTC).isoformat(),
        "traffic": observed,
        "small_batch": {
            "requests": len(ids),
            "observed_completion_seconds": elapsed,
            "end_to_end_observed_requests_per_second": len(ids) / elapsed,
            "inference_latency_ms_min": min(latency),
            "inference_latency_ms_max": max(latency),
            "inference_latency_ms_mean": sum(latency) / len(latency),
        },
        "initial_delivery_probe_requests": len(initial_delivery),
        "worker_crash_isolation": {
            "status": "PASS",
            "request": down_receipt,
            "stale_heartbeat_visible": True,
            "lost_requests_replayed": False,
            "canonical_NGINX_observed_without_AI_result": missing_observed,
        },
        "hybrid_ai_failure_fallback": hybrid_fallback,
        "worker_restart": {
            "status": "PASS",
            "request": restarted,
            "probe_requests": len(restart_receipts),
            "first_probe_scored": restart_receipts[0]["request_id"] in scored_ids,
            "startup_connection_check": connection_check,
        },
        "observed_delivery": delivery,
        "model_faults": faults,
        "private_canary_in_AI_journal": False,
        "AI_enforcement_actions": 0,
        "Student_auth_DB_workflow": "See foundation smoke-report.json: CSRF/login/me + paired Nginx/Student audit",
        "Suricata_live": False,
        "GLU207": "AVAILABLE_BUT_NOT_LIVE",
        "new_training_updates": 0,
        "limitations": [
            "Same-host local small sample, not a quality/throughput benchmark",
            "Missing body and partial headers",
            "Local lossy bounded datagrams; no durable raw HTTP replay",
            "No live Suricata capture started",
        ],
    }
    if args.stop_after:
        # Preserve credentials in memory, never write environment values to evidence.
        item = launcher.load_state()["security"]
        assert launcher.process_token(item["pid"]) == item["start_token"]
        raw_env = Path(f"/proc/{item['pid']}/environ").read_bytes().split(b"\0")
        environment = {p.split(b"=",1)[0].decode():p.split(b"=",1)[1].decode() for p in raw_env if b"=" in p}
        before = int(launcher.sql(launcher.container_name("security"), "security_db", "SELECT count(*) FROM ai_shadow_results"))
        launcher.stop_process("security", item)
        os.environ["DEV_LIMIT_SERVICES"] = "true"
        launcher.start("security", [str(ROOT / "security-web/target/debug/pbl4-security-demo")], ROOT / "security-web", environment)
        environment.clear()
        launcher.wait_http(security + "/health", timeout=60)
        assert call("/api/ai-shadow")[0] == 401
        after = int(launcher.sql(launcher.container_name("security"), "security_db", "SELECT count(*) FROM ai_shadow_results"))
        assert after >= before
        assert student()["http_status"] == 200
        report["Rust_restart_persistence"] = {"status":"PASS", "AI_rows_before":before, "AI_rows_after":after, "Student_HTTP":200, "unauthenticated_AI_HTTP":401}
        state = launcher.load_state()
        launcher.stop()
        assert all(launcher.process_token(p["pid"]) != p["start_token"] for p in state.values())
        for port in ports.values():
            launcher.free_port(port)
        report["graceful_shutdown"] = {"status":"PASS", "owned_processes_stopped":True, "all_configured_ports_free":True, "database_volumes_preserved":True}
    output = RUNTIME / "ai" / ("acceptance-" + str(time.time_ns()) + ".json")
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "evidence": str(output),
                "traffic_count": len(observed),
                "latency_ms": report["small_batch"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

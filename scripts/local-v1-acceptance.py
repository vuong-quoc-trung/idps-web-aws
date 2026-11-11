#!/usr/bin/env python3
"""Finite local RC1 acceptance using existing launchers/sensor/fault tests.

The supervisor runs the existing independent guard in scope mode to preserve
authorized local user-namespace capture permissions. No training or promotion.
"""

import argparse
import hashlib
import http.cookiejar
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / ".local-dev/rc1"
SENSOR = REPO / ".local-dev/rc1-ids"
EVALUATION = (
    REPO / "ai-training/.artifacts/local_v1_rc1_20261110/evaluation-v1/evaluation.json"
)


def load(p):
    return json.loads(Path(p).read_text())


def atomic(p, value):
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = p.with_suffix(".writing")
    with temp.open("w") as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(p)


def environment():
    return os.environ | {
        "IDPS_DEMO_RUNTIME": str(RUNTIME),
        "IDPS_DEMO_CONTAINER_PREFIX": "idps-rc1",
        "IDPS_ACCEPTANCE_SHARED_CGROUP": "1",
        "NGINX_BIN": str(REPO / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }


def launcher():
    os.environ.update(environment())
    spec = importlib.util.spec_from_file_location(
        "local_launcher", REPO / "scripts/dev-up-and-verify.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def request_login():
    secret = load(RUNTIME / "credentials.json")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    edge = "http://127.0.0.1:18780"
    receipts = []
    with opener.open(edge + "/api/auth/csrf", timeout=30) as response:
        csrf = json.load(response)
        receipts.append(
            {
                "case": "legitimate-GET-CSRF",
                "request_id": response.headers["X-Request-Id"],
                "HTTP_STATUS": response.status,
            }
        )
    form = urllib.parse.urlencode(
        {"username": "foundation-admin", "password": secret["student_admin_password"]}
    ).encode()
    request = urllib.request.Request(
        edge + "/api/auth/login",
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            csrf["headerName"]: csrf["token"],
        },
    )
    with opener.open(request, timeout=30) as response:
        assert response.status == 204
        receipts.append(
            {
                "case": "legitimate-POST-login",
                "request_id": response.headers["X-Request-Id"],
                "HTTP_STATUS": response.status,
            }
        )
    with opener.open(edge + "/api/auth/me", timeout=30) as response:
        assert json.load(response)["role"] == "ADMIN"
        receipts.append(
            {
                "case": "legitimate-GET-me",
                "request_id": response.headers["X-Request-Id"],
                "HTTP_STATUS": response.status,
            }
        )
    secret.clear()
    return receipts


def wait_gateway(process):
    end = time.monotonic() + 90
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("Isolated sensor gateway exited; inspect sensor log")
        try:
            with socket.create_connection(("127.0.0.1" if os.environ.get("IDPS_DEMO_LISTEN") == "0.0.0.0" else os.environ.get("IDPS_DEMO_LISTEN", "127.0.0.1"), 18782), timeout=0.5):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Sensor gateway readiness deadline")


def protected_snapshot():
    names = subprocess.check_output(
        ["git", "ls-files", "student-web", "security-web"], cwd=REPO, text=True
    ).splitlines()
    result = {
        name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
        for name in names
        if (REPO / name).is_file()
    }
    for root in [
        "ai-training/.artifacts/request_intelligence_v2_20261104/run/model",
        "ai-training/.artifacts/research_glu207_bounded_final_20261104/run",
    ]:
        p = REPO / root
        pointer = load(p / "latest.json")
        generation = p / pointer["path"]
        assert (
            hashlib.sha256((generation / "manifest.json").read_bytes()).hexdigest()
            == pointer["manifest_sha256"]
        )
        for name, sha in load(generation / "manifest.json")["files"].items():
            assert hashlib.sha256((generation / name).read_bytes()).hexdigest() == sha
            result[str((generation / name).relative_to(REPO))] = sha
    return result


def receipt_evidence(m, receipts):
    def read_lines(path):
        return (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )

    nginx = read_lines(RUNTIME / "nginx/access.log")
    student = read_lines(RUNTIME / "student-audit/student-audit.log")
    ai = read_lines(RUNTIME / "ai/results.jsonl")
    correlations = read_lines(RUNTIME / "correlation/results.jsonl")
    proof = []
    for receipt in receipts:
        rid = receipt["request_id"]
        assert re.fullmatch(r"[a-f0-9]{32}", rid)
        n = [x for x in nginx if x.get("request_id") == rid]
        s = [x for x in student if x.get("request_id") == rid]
        scores = [
            x for x in ai if x.get("request_id") == rid and x.get("kind") == "inference"
        ]
        c = [x for x in correlations if x.get("request_id") == rid]
        linked = c[-1] if c else None
        score = scores[-1] if scores else None
        alerts = int(
            m.sql(
                m.container_name("security"),
                "security_db",
                f"SELECT count(*) FROM detector_alert_links l JOIN security_alerts a ON a.id=l.alert_id WHERE l.request_id='{rid}' AND a.source IN ('SURICATA','NGINX')",
            )
        )
        proof.append(
            {
                **receipt,
                "NGINX_LOG": bool(n),
                "STUDENT_LOG": bool(s),
                "SURICATA_EVIDENCE": linked
                if linked
                else "UNAVAILABLE_NO_REQUEST_BOUND_SENSOR_RECORD",
                "RULE_DECISION": {
                    "source_alerts": alerts,
                    "policy_mode": "OFF",
                    "auto_block": False,
                },
                "AI_MODEL": score.get("model_version") if score else None,
                "AI_SCORE": score.get("score") if score else None,
                "AI_SHADOW_STATUS": score.get("status")
                if score
                else "UNAVAILABLE_NO_RESULT",
                "AI_timestamp": score.get("observed_at") if score else None,
                "AI_latency_ms": score.get("latency_ms") if score else None,
                "CORRELATION_STATUS": linked["status"]
                if linked
                else "NGINX_STUDENT_ONLY",
            }
        )
    return proof


def worker(output, resumed_gates=None, startup_verified=False):
    assert (startup_verified or not (RUNTIME / "configuration.json").exists()) and not SENSOR.exists(), (
        "Fresh isolated runtime only; preserve prior runs"
    )
    output.mkdir(parents=True, exist_ok=True)
    m = launcher()
    assert m.shared_acceptance_cgroup()
    before = protected_snapshot()
    atomic(output / "protected-before.json", before)
    status = {"state": "RUNNING", "phase": "PREFLIGHT", "pid": os.getpid()}
    lock, done = threading.Lock(), threading.Event()

    def publish(**kw):
        with lock:
            status.update(kw)
            atomic(output / "worker-status.json", {**status, "heartbeat": time.time()})

    def loop():
        while not done.wait(0.5):
            publish()

    def run(name, command, cwd=REPO, timeout=600):
        publish(phase=name)
        if resumed_gates and name in {"RULES_POLICY_TESTS", "FRONTEND_TESTS", "LOCAL_STARTUP", "AI_FAULT_RECOVERY_AND_SHUTDOWN"}:
            gate = {"RULES_POLICY_TESTS":"RULES_POLICY", "FRONTEND_TESTS":"SECURITY_FRONTEND_TESTS", "LOCAL_STARTUP":"LOCAL_STARTUP", "AI_FAULT_RECOVERY_AND_SHUTDOWN":"INFERENCE_FALLBACK"}[name]
            if resumed_gates.get(gate) == "PASS":
                return
        publish(phase=name)
        with (output / (name + ".log")).open("wb") as log:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment(),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        if result.returncode:
            raise RuntimeError(name + " failed; inspect its private log")

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    gates, failures, sensor, receipts = {}, [], None, []
    try:
        # Existing harmless Rust fixtures validate Rule/Policy semantics; no event
        # is injected into the live firewall and no Security Web source is edited.
        try:
            run(
                "RULES_POLICY_TESTS",
                [
                    "cargo",
                    "test",
                    "--locked",
                    "--offline",
                    "-j",
                    "1",
                    *(["--test", "hybrid_policy_effect"] if os.environ.get("IDPS_HYBRID_ACCEPTANCE") == "1" else []),
                    "parser_tests",
                    "--",
                    "--test-threads=1",
                ],
                REPO / "security-web",
                600,
            )
            text = (output / "RULES_POLICY_TESTS.log").read_text()
            assert re.search(r"running [1-9][0-9]* tests", text), (
                "No actual Rust tests executed"
            )
            gates["RULES_POLICY"] = "PASS"
        except Exception as exc:  # noqa: BLE001 -- preserve failed gate and finish independent checks
            gates["RULES_POLICY"] = "FAIL"
            failures.append({"stage": "RULES_POLICY_TESTS", "reason": str(exc)})
        run("FRONTEND_TESTS", ["npm", "test"], REPO / "security-web/frontend", 120)
        gates["SECURITY_FRONTEND_TESTS"] = "PASS"
        run(
            "LOCAL_STARTUP",
            [str(REPO / "scripts/dev-up-and-verify.sh"), "--ai-shadow", "--skip-build"],
            timeout=600,
        )
        foundation = load(RUNTIME / "smoke-report.json")
        if foundation.get("status") != "PASS" or foundation.get("ai_shadow_startup") != "READY":
            raise RuntimeError(f"LOCAL_STARTUP not ready: foundation={foundation.get('status')}, ai={foundation.get('ai_shadow_startup')}; evidence={RUNTIME / 'smoke-report.json'}; AI diagnostics={RUNTIME / 'ai/startup-failure.json'}")
        gates.update(
            LOCAL_STARTUP="PASS",
            STUDENT_WEB_REGRESSION="PASS",
            SECURITY_WEB_HTTP="PASS",
        )
        publish(phase="LEGITIMATE_GET_POST")
        receipts += request_login()
        with urllib.request.urlopen("http://127.0.0.1:3001/", timeout=20) as response:
            assert response.status == 200 and b"<html" in response.read().lower()
        sensor_log = (output / "sensor.log").open("wb")
        try:
            publish(phase="SURICATA_GATEWAY_START")
            sensor = subprocess.Popen(
                [
                    sys.executable,
                    str(REPO / "scripts/three-source-shadow.py"),
                    "host",
                    "--runtime",
                    str(RUNTIME),
                    "--output",
                    str(SENSOR),
                ],
                env=environment(),
                stdout=sensor_log,
                stderr=subprocess.STDOUT,
            )
            wait_gateway(sensor)
            run(
                "THREE_SOURCE_HTTP",
                [
                    sys.executable,
                    str(REPO / "scripts/verify-three-source.py"),
                    "--runtime",
                    str(RUNTIME),
                    "--sensor",
                    str(SENSOR),
                ],
                timeout=480,
            )
            acceptance = load(max(SENSOR.glob("acceptance-*.json")))
            assert acceptance["status"] == "PASS"
            receipts += [
                {
                    "case": x["case"],
                    "request_id": x["request_id"],
                    "HTTP_STATUS": x["HTTP"],
                }
                for x in acceptance["receipts"]
            ]
            gates.update(
                SURICATA_LIVE="PASS", REQUEST_CORRELATION="PASS", SENSOR_RECOVERY="PASS"
            )
        except Exception as exc:  # noqa: BLE001 -- preserve failed gate and finish independent checks
            gates.update(SURICATA_LIVE="FAIL", REQUEST_CORRELATION="PARTIAL")
            failures.append({"stage": "THREE_SOURCE_HTTP", "reason": str(exc)})
        finally:
            if sensor and sensor.poll() is None:
                sensor.terminate()
                try:
                    sensor.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    sensor.kill()
                    sensor.wait()
            sensor_log.close()
        publish(phase="CAPTURE_REQUEST_PROOFS")
        proofs = receipt_evidence(m, receipts)
        atomic(output / "request-proofs-private.json", proofs)
        assert all(p["NGINX_LOG"] and p["STUDENT_LOG"] for p in proofs)
        legitimate = [p for p in proofs if p["case"].startswith("legitimate-")]
        assert all(p["AI_SHADOW_STATUS"] == "SCORED" for p in legitimate)
        assert (
            int(
                m.sql(
                    m.container_name("security"),
                    "security_db",
                    "SELECT count(*) FROM firewall_actions WHERE source='AUTO'",
                )
            )
            == 0
        )
        gates["NO_AI_ENFORCEMENT"] = "PASS"
        run(
            "AI_FAULT_RECOVERY_AND_SHUTDOWN",
            [sys.executable, str(REPO / "scripts/verify-ai-local.py"), "--stop-after"],
            timeout=600,
        )
        ai = load(max((RUNTIME / "ai").glob("acceptance-*.json")))
        assert ai["status"] == "PASS" and ai["graceful_shutdown"]["status"] == "PASS"
        gates.update(
            AI_SHADOW_INFERENCE="PASS",
            INFERENCE_FALLBACK="PASS",
            SERVICE_RECOVERY="PASS",
            LOCAL_SHUTDOWN="PASS",
            LIVE_HTTP_SMOKE="PASS",
        )
    except Exception as exc:  # noqa: BLE001 -- preserve failed gate and finish independent checks
        gates[status["phase"]] = "FAIL"
        failures.append({"stage": status["phase"], "type": type(exc).__name__, "reason": str(exc) or f"{type(exc).__name__} without message; inspect stage log", "log": str(output / (status["phase"] + ".log")), "runtime": str(RUNTIME)})
    finally:
        publish(phase="OWNED_RUNTIME_CLEANUP")
        try:
            with (output / "cleanup.log").open("ab") as log:
                result = subprocess.run(
                    [str(REPO / "scripts/dev-up-and-verify.sh"), "--stop"],
                    env=environment(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                    check=False,
                )
            if result.returncode:
                raise RuntimeError("Owned stack stop failed")
            for port in [8080, 5173, 3001, 18780, 55433, 55434, 18782]:
                m.free_port(port)
            gates["LOCAL_SHUTDOWN"] = "PASS"
        except Exception as exc:  # noqa: BLE001 -- preserve failed gate and finish independent checks
            gates["LOCAL_SHUTDOWN"] = "FAIL"
            failures.append({"stage": "CLEANUP", "reason": str(exc)})
        try:
            assert before == protected_snapshot()
            gates["PROTECTED_WEB_FROZEN_MODELS"] = "PASS"
        except Exception as exc:  # noqa: BLE001 -- preserve failed gate and finish independent checks
            gates["PROTECTED_WEB_FROZEN_MODELS"] = "FAIL"
            failures.append({"stage": "PRESERVATION", "reason": type(exc).__name__})
        atomic(
            output / "acceptance-results.json",
            {
                "release": "AI-IDPS-Local-v1.0-rc1",
                "gates": gates,
                "failures": failures,
                "resource_closure": "PENDING_SUPERVISOR",
                "publisher_anomaly": "EVALUATED_OFFLINE_LIVE_UNSUPPORTED",
                "GLU207": "UNCHANGED_CONTRACT_GATED; NOT_EXERCISED_IN_THIS_HTTP_SMOKE",
                "receipt_count": len(receipts),
                "new_training": False,
                "enforcement": "DISABLED",
                "sealed_access": False,
            },
        )
        publish(
            state="COMPLETED",
            phase="ACCEPTANCE_EVIDENCE_SAVED_RESOURCE_CLOSURE_PENDING",
        )
        done.set()
        thread.join()


def supervise(output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic(
        output / "supervisor.json",
        {
            "pid": os.getpid(),
            "run_id": "AI-IDPS-Local-v1.0-rc1",
            "started": time.time(),
            "state": "RUNNING",
        },
    )
    command = [
        sys.executable,
        str(REPO / "ai-training/scripts/integration-guard.py"),
        "--output",
        str(output / "guard"),
        "--scope",
        "--policy",
        "rolling",
        "--quota",
        "20",
        "--memory-gib",
        "8",
        "--cutoff",
        "100",
        "--tasks-max",
        "256",
        "--max-seconds",
        "2400",
        "--",
        sys.executable,
        str(Path(__file__)),
        "--mode",
        "worker",
        "--output",
        str(output),
    ]
    code = subprocess.run(command, cwd=REPO, env=environment(), check=False).returncode
    # The scope watchdog can kill the worker before its finally block. The
    # outside supervisor still stops only this named owned stack/DB containers.
    with (output / "supervisor-cleanup.log").open("ab") as log:
        cleanup = subprocess.run(
            [str(REPO / "scripts/dev-up-and-verify.sh"), "--stop"],
            cwd=REPO,
            env=environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    results = (
        load(output / "acceptance-results.json")
        if (output / "acceptance-results.json").exists()
        else {
            "gates": {},
            "failures": [
                {"stage": "WORKER", "reason": "No complete acceptance evidence"}
            ],
        }
    )
    guard = (
        load(output / "guard/resource-report.json")
        if (output / "guard/resource-report.json").exists()
        else {"status": "MISSING"}
    )
    results["gates"]["RESOURCE_SAFETY"] = (
        "PASS" if code == 0 and guard["status"] == "PASS" else "FAIL"
    )
    evaluation = load(EVALUATION)
    results["gates"]["MODEL_EVALUATION"] = evaluation["research_acceptance"]["state"]
    validation = load(
        REPO
        / "ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1/validation.json"
    )
    results["gates"]["DATASET_INTEGRITY"] = (
        "PASS"
        if validation["state"] == "PASS"
        and validation["dataset_fingerprint"] == evaluation["dataset_fingerprint"]
        else "FAIL"
    )
    if cleanup.returncode:
        results["gates"]["LOCAL_SHUTDOWN"] = "FAIL"
        results["failures"].append(
            {"stage": "SUPERVISOR_CLEANUP", "reason": "Owned stack stop failed"}
        )
    required = [
        "MODEL_EVALUATION",
        "DATASET_INTEGRITY",
        "RULES_POLICY",
        "NO_AI_ENFORCEMENT",
        "SECURITY_FRONTEND_TESTS",
        "LOCAL_STARTUP",
        "STUDENT_WEB_REGRESSION",
        "SECURITY_WEB_HTTP",
        "AI_SHADOW_INFERENCE",
        "REQUEST_CORRELATION",
        "SURICATA_LIVE",
        "SENSOR_RECOVERY",
        "INFERENCE_FALLBACK",
        "SERVICE_RECOVERY",
        "LOCAL_SHUTDOWN",
        "LIVE_HTTP_SMOKE",
        "PROTECTED_WEB_FROZEN_MODELS",
        "RESOURCE_SAFETY",
    ]
    allpass = all(results["gates"].get(k) == "PASS" for k in required)
    results.update(
        local_release="ACCEPTED"
        if allpass
        else "PARTIAL"
        if results["gates"].get("LOCAL_STARTUP") == "PASS"
        else "BLOCKED",
        resource_closure=guard,
        evaluation_report=str(EVALUATION),
        completed=time.time(),
    )
    atomic(output / "AI-IDPS-Local-v1.0-rc1.json", results)
    primary = evaluation["metrics"]["EVALUATION"]["final"]["CAL_balanced"]
    lines = [
        "# AI-IDPS-Local-v1.0-rc1",
        "",
        "LOCAL_RELEASE = " + results["local_release"],
        "",
        "Publisher anomaly model: evaluated offline only; live unsupported. Frozen Requestv2 serves the shadow path; no promotion/enforcement.",
        "",
        "Evaluation: "
        + str(
            {
                k: primary[k]
                for k in [
                    "precision",
                    "recall",
                    "F1",
                    "average_precision",
                    "FPR",
                    "confusion_matrix_normal_anomaly",
                ]
            }
        ),
        "",
        "Acceptance gates:",
    ]
    lines += ["- " + k + " = " + results["gates"].get(k, "NOT_RUN") for k in required]
    lines += [
        "",
        "Failures: " + json.dumps(results["failures"]),
        "",
        "See docs/44_AI_IDPS_LOCAL_V1_RC1.md for reproducible commands and scope. No production readiness or verified attack-family quality claim.",
    ]
    (output / "AI-IDPS-Local-v1.0-rc1.md").write_text("\n".join(lines) + "\n")
    atomic(
        output / "supervisor.json",
        {
            "pid": os.getpid(),
            "state": "COMPLETED",
            "local_release": results["local_release"],
            "completed": time.time(),
        },
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["supervise", "worker"], required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    if args.mode == "supervise":
        supervise(args.output.resolve())
    else:
        worker(args.output.resolve())

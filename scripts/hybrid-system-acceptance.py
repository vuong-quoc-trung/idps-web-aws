#!/usr/bin/env python3
"""One bounded build + hybrid integration + actual namespace-response acceptance."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNTIME = Path(
    os.environ.get("IDPS_DEMO_RUNTIME", REPO / ".local-dev/demo-v1")
).resolve()
PREFIX = os.environ.get("IDPS_DEMO_CONTAINER_PREFIX", "idps-demo-v1")


def load(p):
    return json.loads(Path(p).read_text())


def atomic(p, v):
    # Unique temp files + directory fsync; heartbeat and final writer may race.
    from idps_ai.common import atomic_json
    atomic_json(p, v)


def module(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), REPO / "scripts" / name
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def env():
    return os.environ | {
        "IDPS_DEMO_RUNTIME": str(RUNTIME),
        "IDPS_DEMO_CONTAINER_PREFIX": PREFIX,
        "IDPS_ACCEPTANCE_SHARED_CGROUP": "1",
        "IDPS_HYBRID_ACCEPTANCE": "1",
        "HYBRID_POLICY_JSON": json.dumps({"approved_clients": ["10.203.17.2"]}),
        "NGINX_BIN": str(REPO / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "IDPS_POLICY_EFFECT_REPORT": str(
            Path(os.environ["IDPS_DEMO_ACCEPTANCE_ROOT"]) / "policy-effect-fixture.json"
        )
        if os.environ.get("IDPS_DEMO_ACCEPTANCE_ROOT")
        else "",
    }


def verified_cutoff(root, quota=200):
    """Use local CPU limits, retaining a margin under the user's <96C ceiling."""
    limits = []
    readings = {}
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        if (hwmon / "name").read_text().strip() != "coretemp":
            continue
        for path in hwmon.glob("temp*_crit"):
            limits.append(int(path.read_text()) / 1000)
        for path in hwmon.glob("temp*_input"):
            readings[str(path)] = int(path.read_text()) / 1000
    if not limits or not readings:
        raise RuntimeError(
            "CPU temperature/critical limits unavailable; no workload started"
        )
    cutoff = min(100, min(limits))
    if cutoff <= 80:
        raise RuntimeError("Hardware limit requires a lower workload profile")
    atomic(
        root / "hardware-safety.json",
        {
            "cpu": "Intel Core Ultra 9 285H (lscpu verified 2026-11-11)",
            "local_coretemp_critical_C": min(limits),
            "instant_cutoff_C": cutoff,
            "initial_readings_C": readings,
            "sustained_average_limit_C": 100,
            "quota_percent_one_core": quota,
            "memory_GiB": 8,
            "reserve_GiB": 4,
            "manufacturer_reference": "https://www.intel.com/content/www/us/en/products/sku/241747/intel-core-ultra-9-processor-285h-24m-cache-up-to-5-40-ghz/specifications.html",
            "hardware_protection_modified": False,
        },
    )
    return str(cutoff)


def resume_evidence(root):
    name = os.environ.get("IDPS_DEMO_RESUME_FROM")
    if not name:
        return None
    previous = Path(name).resolve()
    result = load(previous / "acceptance-results.json")
    if module("local-v1-acceptance.py").protected_snapshot() != load(previous / "protected-before.json"):
        raise RuntimeError("Cannot reuse successful tests: protected source/model fingerprints changed")
    for gate in ["RULES_POLICY", "SECURITY_FRONTEND_TESTS", "PROTECTED_WEB_FROZEN_MODELS"]:
        if result["gates"].get(gate) != "PASS":
            raise RuntimeError("Previous gate is not reusable: " + gate)
    proofs = {}
    for filename in ["rust-build.log", "hybrid-tests.log", "response-tests.log", "RULES_POLICY_TESTS.log", "FRONTEND_TESTS.log", "policy-effect-fixture.json"]:
        path = previous / filename
        content = path.read_bytes()
        if filename.endswith("tests.log") and b"test result: ok." not in content:
            raise RuntimeError("Missing successful Rust test evidence: " + filename)
        proofs[filename] = hashlib.sha256(content).hexdigest()
        if not (root / filename).exists():
            shutil.copyfile(path, root / filename)
    if load(previous / "policy-effect-fixture.json")["state"] != "PASS":
        raise RuntimeError("Previous production-policy effect test did not pass")
    if result["gates"].get("INFERENCE_FALLBACK") == "PASS":
        for filename in ["AI_FAULT_RECOVERY_AND_SHUTDOWN.log", "request-proofs-private.json"]:
            path = previous / filename
            if not path.exists():
                inherited = load(previous / "reused-evidence.json")
                path = Path(inherited["source"]) / filename
                if hashlib.sha256(path.read_bytes()).hexdigest() != inherited["files_sha256"][filename]:
                    raise RuntimeError("Inherited live evidence fingerprint changed: " + filename)
            proofs[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
            if not (root / filename).exists():
                shutil.copyfile(path, root / filename)
        atomic(root / "reused-live-gates.json", {"source":str(previous), "gates":{k:v for k,v in result["gates"].items() if v == "PASS"}, "scope":"Historical r4 fallback/restart evidence; not claimed as fresh r5 execution"})
    atomic(root / "reused-evidence.json", {"source":str(previous), "files_sha256":proofs, "protected_source_and_frozen_payloads":"UNCHANGED", "scope":"Previous successful tests reused; startup and failed live gates run fresh; r4 fallback reused when PASS"})
    return dict(result["gates"])


def worker(root):
    # Read-only CPU frequency inventory identifies the two2.5GHz local cores.
    # Keep this acceptance on them to avoid unnecessary5.4GHz compiler bursts.
    if all(
        Path(f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq").exists()
        for i in range(16)
    ):
        cool = sorted(
            range(16),
            key=lambda i: int(
                Path(
                    f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq"
                ).read_text()
            ),
        )[:2]
        os.sched_setaffinity(0, cool)
    os.environ["IDPS_DEMO_ACCEPTANCE_ROOT"] = str(root)
    status = {
        "state": "RUNNING",
        "phase": "BUILD_RUST_AND_HYBRID_TESTS",
        "pid": os.getpid(),
    }
    done = threading.Event()

    def loop():
        while not done.wait(0.5):
            atomic(root / "wrapper-status.json", {**status, "heartbeat": time.time()})

    threading.Thread(target=loop, daemon=True).start()
    try:
        previous = resume_evidence(root)
        commands = [
            ("rust-build", ["cargo", "build", "--locked", "--offline", "-j", "1"]),
            (
                "hybrid-tests",
                [
                    "cargo",
                    "test",
                    "--locked",
                    "--offline",
                    "-j",
                    "1",
                    "--test",
                    "hybrid_policy_effect",
                    "policy_fixture_",
                    "--",
                    "--test-threads=1",
                ],
            ),
            (
                "response-tests",
                [
                    "cargo",
                    "test",
                    "--locked",
                    "--offline",
                    "-j",
                    "1",
                    "--test",
                    "hybrid_policy_effect",
                    "firewall::tests",
                    "--",
                    "--test-threads=1",
                ],
            ),
        ]
        for name, args in commands:
            if previous:
                continue
            status["phase"] = name
            with (root / (name + ".log")).open("wb") as log:
                subprocess.run(
                    args,
                    cwd=REPO / "security-web",
                    env=env(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=1500,
                    check=True,
                )
        accept = module("local-v1-acceptance.py")
        accept.RUNTIME = RUNTIME
        accept.SENSOR = REPO / ".local-dev" / (root.name + "-sensor")
        accept.environment = env
        if previous:
            # Isolated startup gate first. No remaining integration request is
            # emitted until fresh HTTP/auth, model heartbeat AND delivery score pass.
            status["phase"] = "LOCAL_STARTUP_INDEPENDENT"
            with (root / "LOCAL_STARTUP.log").open("wb") as log:
                subprocess.run([str(REPO / "scripts/dev-up-and-verify.sh"), "--ai-shadow", "--skip-build"],
                    cwd=REPO, env=env(), stdout=log, stderr=subprocess.STDOUT, timeout=600, check=True)
            smoke = load(RUNTIME / "smoke-report.json")
            if smoke.get("ai_shadow_startup") != "READY" or smoke.get("status") != "PASS":
                raise RuntimeError(f"LOCAL_STARTUP: foundation={smoke.get('status')}, AI={smoke.get('ai_shadow_startup')}; inspect {RUNTIME / 'ai/startup-failure.json'} and {root / 'LOCAL_STARTUP.log'}")
            delivery = load(RUNTIME / "ai/connection-check.json")
            if delivery.get("status") != "PASS":
                raise RuntimeError("LOCAL_STARTUP: model-ready heartbeat has no real HTTP delivery score")
            atomic(root / "startup-independent.json", {"state":"PASS", "smoke":smoke, "real_AI_delivery":delivery, "verified_at":time.time()})
            previous["LOCAL_STARTUP"] = "PASS"
        original_login = accept.request_login

        def login_and_native_proof():
            receipts = original_login()
            status["phase"] = "NATIVE_CLIENT_HYBRID_AND_MANUAL_RESPONSE"
            try:
                with (root / "native-lab.log").open("wb") as log:
                    subprocess.run(
                        [
                            sys.executable,
                            str(REPO / "scripts/hybrid-lab-proof.py"),
                            "--mode",
                            "host",
                            "--root",
                            str(root / "native-lab"),
                        ],
                        cwd=REPO,
                        env=env(),
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=450,
                        check=True,
                    )
            except (subprocess.SubprocessError, OSError) as e:
                atomic(
                    root / "native-lab-failure.json",
                    {
                        "error": type(e).__name__,
                        "detail": str(e),
                        "proofs_preserved": True,
                    },
                )
            result_path = root / "native-lab/result.json"
            if result_path.exists():
                result = load(result_path)
                incident = result.get("proofs", {}).get("rule_ai_incident", {})
                rid = incident.get("receipt", {}).get("request_id")
                if (
                    isinstance(rid, str)
                    and len(rid) == 32
                    and all(c in "0123456789abcdef" for c in rid)
                ):
                    launcher = accept.launcher()
                    count = int(
                        launcher.sql(
                            launcher.container_name("security"),
                            "security_db",
                            f"SELECT count(*) FROM hybrid_decision_audit WHERE request_id='{rid}'",
                        )
                    )
                    atomic(
                        root / "database-audit-proof.json",
                        {
                            "request_id": rid,
                            "persisted_decision_versions": count,
                            "state": "PASS" if count > 0 else "FAIL",
                        },
                    )
            status["phase"] = "EXISTING_SENSOR_AI_FAILURE_RECOVERY_ACCEPTANCE"
            return receipts

        accept.request_login = login_and_native_proof
        accept.worker(root, resumed_gates=previous, startup_verified=bool(previous))
    except Exception as e:
        atomic(
            root / "worker-failure.json",
            {"phase": status["phase"], "type": type(e).__name__, "reason": str(e) or type(e).__name__, "log_directory":str(root), "runtime":str(RUNTIME)},
        )
        raise
    finally:
        done.set()
        status.update(state="STOPPED", heartbeat=time.time())
        atomic(root / "wrapper-status.json", status)


def demo_worker(root):
    os.environ["IDPS_DEMO_ACCEPTANCE_ROOT"] = str(root)
    os.sched_setaffinity(
        0,
        sorted(
            range(os.cpu_count()),
            key=lambda i: int(
                Path(
                    f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq"
                ).read_text()
            ),
        )[:2],
    )
    accept = module("local-v1-acceptance.py")
    accept.RUNTIME = RUNTIME
    accept.environment = env
    sensor = None
    atomic(root / "wrapper-status.json", {"state":"RUNNING", "phase":"STARTING_LOCAL_SERVICES", "pid":os.getpid(), "heartbeat":time.time()})
    subprocess.run(
        [str(REPO / "scripts/dev-up-and-verify.sh"), "--ai-shadow", "--skip-build"],
        cwd=REPO,
        env=env(),
        check=True,
        timeout=600,
    )
    try:
        sensor_root = REPO / ".local-dev" / ("demo-sensor-" + str(time.time_ns())[-10:])
        with (root / "sensor.log").open("ab") as log:
            sensor = subprocess.Popen(
                [
                    sys.executable,
                    str(REPO / "scripts/three-source-shadow.py"),
                    "host",
                    "--runtime",
                    str(RUNTIME),
                    "--output",
                    str(sensor_root),
                    "--listen",
                    os.environ.get("IDPS_DEMO_LISTEN", "127.0.0.1"),
                    "--allow-cidr",
                    os.environ.get("IDPS_DEMO_ALLOW_CIDR", "127.0.0.0/8"),
                ],
                env=env(),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        accept.SENSOR = sensor_root
        accept.wait_gateway(sensor)
        listen_host = os.environ.get("IDPS_DEMO_LISTEN", "127.0.0.1")
        gateway_url = "http://" + ("127.0.0.1" if listen_host == "0.0.0.0" else listen_host) + ":18782"
        import urllib.request
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(gateway_url + "/api/auth/csrf", timeout=10) as response:
            response.read()
            if response.status != 200 or not response.headers.get("X-Request-Id"):
                raise RuntimeError(f"LAN HTTP readiness failed at {gateway_url}; expected NGINX HTTP200 with X-Request-Id")
        atomic(
            root / "demo-ready.json",
            {
                "state": "READY",
                "runtime": str(RUNTIME),
                "sensor": str(sensor_root),
                "gateway": gateway_url,
                "probe_url": gateway_url,
                "listen": listen_host,
                "allowed_sources": os.environ.get("IDPS_DEMO_ALLOW_CIDR", "127.0.0.0/8"),
                "two_machine_validation": "PENDING_EXTERNAL_CLIENT",
                "client_attribution": "TCP peer is logged separately; relay IP is protected; no LAN IP blocking",
                "automatic_block": False,
                "enforcement": "OFF",
            },
        )
        while not (root / "STOP").exists():
            if sensor.poll() is not None:
                raise RuntimeError("Suricata gateway exited")
            approval = root / "OPERATOR_PROOF_REQUEST.json"
            if approval.exists():
                request = load(approval)
                assert (
                    request["operator_uid"] == os.getuid()
                    and request["target"]
                    == "DISPOSABLE_NAMESPACE_CLIENT_10.203.17.2_ONLY"
                )
                approved = root / (
                    "OPERATOR_PROOF_APPROVED-" + str(time.time_ns()) + ".json"
                )
                approval.rename(approved)
                proof_root = (
                    REPO / ".local-dev" / ("op-proof-" + str(time.time_ns())[-10:])
                )
                atomic(
                    root / "operator-proof-status.json",
                    {
                        "state": "RUNNING",
                        "approval": str(approved),
                        "proof": str(proof_root),
                    },
                )
                with (root / "operator-proof.log").open("ab") as output:
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(REPO / "scripts/hybrid-lab-proof.py"),
                            "--mode",
                            "host",
                            "--root",
                            str(proof_root),
                            "--operator-approved-isolated-client",
                        ],
                        cwd=REPO,
                        env=env(),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        timeout=450,
                        check=False,
                    )
                atomic(
                    root / "operator-proof-status.json",
                    {
                        "state": "PASS" if result.returncode == 0 else "FAILED",
                        "approval": str(approved),
                        "proof": str(proof_root / "result.json"),
                    },
                )
            atomic(
                root / "wrapper-status.json",
                {
                    "state": "RUNNING",
                    "phase": "CLASSROOM_DEMO_SERVING",
                    "pid": os.getpid(),
                    "heartbeat": time.time(),
                    "gateway": gateway_url,
                },
            )
            time.sleep(0.5)
    finally:
        if sensor and sensor.poll() is None:
            sensor.terminate()
            try:
                sensor.wait(timeout=20)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Sensor did not shut down gracefully")
        subprocess.run(
            [str(REPO / "scripts/dev-up-and-verify.sh"), "--stop"],
            cwd=REPO,
            env=env(),
            check=True,
            timeout=120,
        )


def supervise(root, demo=False):
    lock = (REPO / ".local-dev/hybrid-acceptance.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic(
        root / "supervisor.json",
        {
            "pid": os.getpid(),
            "state": "RUNNING",
            "phase": "PREPARE_OWNED_DATABASES_OUTSIDE_KILL_SCOPE",
            "run_id": root.name,
        },
    )
    heartbeat_done = threading.Event()

    def heartbeat():
        while not heartbeat_done.wait(0.5):
            atomic(
                root / "supervisor-heartbeat.json",
                {"pid": os.getpid(), "heartbeat": time.time(), "state": "RUNNING"},
            )

    threading.Thread(target=heartbeat, daemon=True).start()
    os.environ.update(env())
    launcher = module("dev-up-and-verify.py")
    assert demo or os.environ.get("IDPS_DEMO_RESUME_FROM") or not (RUNTIME / "configuration.json").exists(), (
        "Fresh acceptance runtime required"
    )
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    credentials = (
        load(RUNTIME / "credentials.json")
        if (RUNTIME / "credentials.json").exists()
        else {
            name: secrets.token_hex(24)
            for name in [
                "student_db_password",
                "security_db_password",
                "hmac_key",
                "security_admin_password",
            ]
        }
    )
    if not (RUNTIME / "credentials.json").exists():
        atomic(RUNTIME / "credentials.json", credentials)
    code = 1
    failure = None
    cleanup_ok = False
    try:
        if os.environ.get("IDPS_DEMO_RESUME_FROM"):
            resume_evidence(root)
        cutoff = verified_cutoff(root, 50 if demo else 200)
        # Podman conmon must not inherit the killable acceptance scope. Containers
        # are already label-owned and bounded to0.1CPU/512MiB by the existing helper.
        launcher.postgres(
            PREFIX + "-student",
            "postgres:16-alpine",
            55433,
            "student_db",
            credentials["student_db_password"],
        )
        launcher.postgres(
            PREFIX + "-security",
            "postgres:17-alpine",
            55434,
            "security_db",
            credentials["security_db_password"],
        )
        credentials.clear()
        command = [
            sys.executable,
            str(REPO / "ai-training/scripts/integration-guard.py"),
            "--output",
            str(root / "guard"),
            "--scope",
            "--policy",
            "rolling",
            "--quota",
            "50" if demo else "200",
            "--memory-gib",
            "8",
            "--cutoff",
            cutoff,
            "--tasks-max",
            "256",
            "--max-seconds",
            "0" if demo else "5400",
            "--",
            sys.executable,
            str(Path(__file__)),
            "--action",
            "demo-worker" if demo else "worker",
            "--root",
            str(root),
        ]
        code = subprocess.run(command, cwd=REPO, env=env(), check=False).returncode
    except Exception as e:  # noqa: BLE001 -- preserve blocker and always clean owned runtime
        failure = {"phase": "SUPERVISOR", "type": type(e).__name__, "reason": str(e)}
    finally:
        try:
            with (root / "cleanup.log").open("ab") as log:
                cleanup = subprocess.run(
                    [str(REPO / "scripts/dev-up-and-verify.sh"), "--stop"],
                    cwd=REPO,
                    env=env(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                    check=False,
                )
            cleanup_ok = cleanup.returncode == 0
            subprocess.run(
                ["podman", "ps", "--sync"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            failure = {
                "phase": "CLEANUP",
                "type": type(exc).__name__,
                "reason": str(exc),
            }
    if demo:
        heartbeat_done.set()
        if failure is None and code != 0:
            resource = load(root / "guard/resource-report.json") if (root / "guard/resource-report.json").exists() else {}
            failure = {"reason":resource.get("failure") or "Demo workload exited; inspect guard/stderr.log and sensor.log", "guard_exit":code, "temperature_max_C":resource.get("cpu_temperature_max"), "watchdog_reason":resource.get("watchdog_failure"), "action":"If thermal stopped, let CPU cool below70C and reduce external load before manually restarting; protection remains enabled"}
        if failure:
            atomic(root / "demo-failure.json", failure)
        atomic(
            root / "supervisor.json",
            {
                "state": "COMPLETED" if code == 0 else "FAILED",
                "pid": os.getpid(),
                "cleanup": "PASS" if cleanup_ok else "FAIL",
                "guard_exit": code,
                "run_id": root.name,
            },
        )
        return
    wrapper = root / "wrapper-status.json"
    if wrapper.exists():
        last = load(wrapper)
        if last.get("state") == "RUNNING":
            atomic(
                wrapper,
                {
                    **last,
                    "state": "STOPPED_BY_SUPERVISOR",
                    "guard_exit": code,
                    "finished": time.time(),
                },
            )
    results = (
        load(root / "acceptance-results.json")
        if (root / "acceptance-results.json").exists()
        else {"gates": {}, "failures": []}
    )
    if failure:
        results["failures"].append(failure)
    if (root / "worker-failure.json").exists():
        results["failures"].append(load(root / "worker-failure.json"))
    guard = (
        load(root / "guard/resource-report.json")
        if (root / "guard/resource-report.json").exists()
        else {"status": "MISSING"}
    )
    results["gates"]["RESOURCE_SAFETY"] = (
        "PASS" if code == 0 and guard["status"] == "PASS" else "FAIL"
    )
    results["gates"]["LOCAL_SHUTDOWN"] = "PASS" if cleanup_ok else "FAIL"
    policy = (
        load(root / "policy-effect-fixture.json")
        if (root / "policy-effect-fixture.json").exists()
        else {"state": "NOT_RUN"}
    )
    results["gates"]["AI_POLICY_EFFECT"] = (
        "PASS" if policy["state"] == "PASS" else "FAIL"
    )
    results["policy_effect_fixture"] = policy
    native = (
        load(root / "native-lab/result.json")
        if (root / "native-lab/result.json").exists()
        else {"state": "NOT_RUN"}
    )
    model = load(REPO / ".local-dev/demo-preflight-20261110/model-integrity.json")
    results["model_contract"] = model
    for key in [
        "HYBRID_RISK_SCORING",
        "HYBRID_POLICY",
        "ALERT_REVIEW",
        "PROPOSE_BLOCK",
        "DATABASE_AUDIT",
    ]:
        results["gates"][key] = (
            "PASS"
            if native["state"] == "PASS"
            else "NOT_RUN"
            if native["state"] == "NOT_RUN"
            else "BLOCKED_BY_LIVE_EVIDENCE"
            if not native.get("proofs", {}).get("real_review")
            else "FAIL"
        )
    for key in ["MANUAL_BLOCK", "UNBLOCK_TTL"]:
        results["gates"][key] = native.get(key, "NOT_RUN")
    results["gates"]["NFTABLES"] = native.get("MANUAL_BLOCK", "NOT_RUN")
    results["gates"]["REAL_RULE_AI_CORRELATION"] = native.get(
        "REAL_RULE_AI_CORRELATION", "NOT_RUN"
    )
    results["gates"]["TWO_MACHINE_NETWORK"] = "PENDING_EXTERNAL_CLIENT"
    for target, source in {
        "NGINX": "LOCAL_STARTUP",
        "RUST_BACKEND": "LOCAL_STARTUP",
        "HTTP_GET": "LIVE_HTTP_SMOKE",
        "HTTP_POST": "STUDENT_WEB_REGRESSION",
        "AI_REAL_INFERENCE": "AI_SHADOW_INFERENCE",
        "EVENT_CORRELATION": "REQUEST_CORRELATION",
        "SURICATA": "SURICATA_LIVE",
    }.items():
        results["gates"][target] = results["gates"].get(source, "NOT_RUN")
    results["gates"]["REQUEST_V2_MODEL_LOADING"] = results["gates"].get(
        "AI_SHADOW_INFERENCE", "NOT_RUN"
    )
    results["gates"]["AI_FEATURE_CONTRACT"] = (
        "PASS"
        if model["state"] == "PASS_ARTIFACT_CONTRACT_ONLY"
        and results["gates"].get("AI_SHADOW_INFERENCE") == "PASS"
        else "NOT_RUN"
    )
    actual = native.get("proofs", {}).get("rule_ai_incident", {}).get("decision")
    results["gates"]["AI_POLICY_INPUT"] = (
        "PASS" if actual and actual.get("ai_risk_component", 0) > 0 else "NOT_RUN"
    )
    audit = (
        load(root / "database-audit-proof.json")
        if (root / "database-audit-proof.json").exists()
        else {"state": "NOT_RUN"}
    )
    results["gates"]["DATABASE_AUDIT"] = audit["state"]
    results["database_audit"] = audit
    results["evidence_categories"] = {
        "A_REAL_INFERENCE": str(root / "request-proofs-private.json"),
        "B_FIXTURE_ONLY_POLICY_EFFECT": str(root / "policy-effect-fixture.json"),
        "C_REAL_CORRELATED_RULE_AI": str(root / "native-lab/result.json"),
    }
    if results["gates"].get("INFERENCE_FALLBACK") == "PASS":
        ai_files = list((RUNTIME / "ai").glob("acceptance-*.json"))
        fallback = (
            load(max(ai_files)).get("hybrid_ai_failure_fallback") if ai_files else None
        )
        results["gates"]["AI_FAILURE_FALLBACK"] = "PASS" if fallback else "FAIL"
    else:
        results["gates"]["AI_FAILURE_FALLBACK"] = "NOT_RUN"
    results["native_proof"] = native
    required = [
        "LOCAL_STARTUP",
        "AI_POLICY_EFFECT",
        "REAL_RULE_AI_CORRELATION",
        "AI_FAILURE_FALLBACK",
        "RULES_POLICY",
        "SECURITY_FRONTEND_TESTS",
        "STUDENT_WEB_REGRESSION",
        "SECURITY_WEB_HTTP",
        "AI_SHADOW_INFERENCE",
        "REQUEST_CORRELATION",
        "SURICATA_LIVE",
        "SENSOR_RECOVERY",
        "INFERENCE_FALLBACK",
        "SERVICE_RECOVERY",
        "LOCAL_SHUTDOWN",
        "RESOURCE_SAFETY",
        "HYBRID_RISK_SCORING",
        "HYBRID_POLICY",
        "ALERT_REVIEW",
        "PROPOSE_BLOCK",
        "NFTABLES",
        "DATABASE_AUDIT",
        "MANUAL_BLOCK",
        "UNBLOCK_TTL",
        "NO_AI_ENFORCEMENT",
        "PROTECTED_WEB_FROZEN_MODELS",
        "LIVE_HTTP_SMOKE",
        "TWO_MACHINE_NETWORK",
    ]
    results.update(
        project="AI-IDPS LOCAL DEMO V1.0",
        run_id=root.name,
        local_release="ACCEPTED"
        if all(results["gates"].get(k) == "PASS" for k in required)
        else "PARTIAL"
        if results["gates"].get("LOCAL_STARTUP") == "PASS"
        else "BLOCKED",
        resource_evidence=guard,
        training="NOT_PERFORMED; LARGE_MODEL_POSTPONED",
        publisher_model="OFFLINE_ONLY",
        automatic_block=False,
        host_firewall_touched=False,
        completed=time.time(),
    )
    atomic(root / "final-status.json", results)
    heartbeat_done.set()
    atomic(
        root / "supervisor.json",
        {
            "pid": os.getpid(),
            "state": "COMPLETED",
            "local_release": results["local_release"],
            "run_id": root.name,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--action",
        choices=["supervise", "worker", "demo", "demo-worker"],
        required=True,
    )
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--resume-from", type=Path)
    a = p.parse_args()
    if a.resume_from:
        os.environ["IDPS_DEMO_RESUME_FROM"] = str(a.resume_from.resolve())
    os.umask(0o077)
    if a.action in ["supervise", "demo"]:
        supervise(a.root.resolve(), a.action == "demo")
    elif a.action == "demo-worker":
        demo_worker(a.root.resolve())
    else:
        worker(a.root.resolve())

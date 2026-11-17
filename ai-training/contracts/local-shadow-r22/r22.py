"""Exercise pinned R20 shadow, RI v2 and Rust Hybrid in disposable Local KVM."""

import argparse
import importlib.util
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from bundle import ONNX, RUST, SCOPE, stage, verify
from evidence import append, labels, observed_sources, read, require, summarize

from idps_ai.common import REPO_ROOT, atomic_json, digest, file_sha256
from idps_ai.export.onnx import cpu_session
from idps_ai.features.request_time import from_request, schema

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "local-acceptance-v1"))
import r12  # noqa: E402

PHASES = ("csrf", "login", "collector_held", "shadow_down", "shadow_recovered", "ri_only_rollback")
HTTP = (200, 204, 200, 200, 200, 200)
BINARY_SHA = "da09c2eb4dc766e9612028cc27b58bc9f4d7f4ff03da81e33d590403949998a5"
SCORER_PATH = REPO_ROOT / "ai-training/.artifacts/t09-r20-quality-OktqJbDt/uri76-shadow"
FEATURES = ("structure_available", "uri_lexical_available", "query_lexical_available")


def base_module():
    spec = importlib.util.spec_from_file_location("r22_accelerated", r12.BASE)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def benign_roster(rows):
    # An existing session need not issue a fresh cookie on a CSRF read. Use
    # the authenticated principal Oracle for all post-login lifecycle probes.
    return [rows[j] | {"attempt": i} for i, j in enumerate((0, 1, 2, 2, 2, 2), 1)]


def stage_guest(base, root, pins, model_dir):
    vm = base.unified.vm
    paths = {
        HERE / "guest.py": "/lab/r22_guest.py",
        REPO_ROOT / "security-web/deploy/ai-shadow/telemetry.conf": "/lab/r22-telemetry.conf",
        model_dir / "swiglu.onnx": "/lab/uri76-model/swiglu.onnx",
        model_dir / "model-scope.json": "/lab/uri76-model/model-scope.json",
    }
    # The inherited stage installs its historical logistic metadata first.
    # Drop that guest copy explicitly because copy_file preserves existing files.
    (root / "lab/uri76-model/model-scope.json").unlink()
    for path, relative in paths.items():
        vm.copy_file(path, root, relative)
        pins[relative] = file_sha256(root / relative.lstrip("/"))
    require(
        pins["/lab/uri76-model/model-scope.json"] == SCOPE
        and pins["/lab/uri76-model/swiglu.onnx"] == ONNX
        and pins["/lab/uri76-shadow"] == RUST,
        "Staged shadow bytes differ from pins",
    )
    config = root / "lab/t083/nginx.conf"
    swap = base.replace_once
    config.write_text(
        swap(
            config.read_text(),
            "    access_log nginx.jsonl t082;",
            "    include /lab/r22-telemetry.conf;\n    access_log nginx.jsonl t082;\n    access_log r22-ri.jsonl pbl4_ai_telemetry if=$pbl4_ai_api;",
        )
    )
    guest = root / "lab/acquire.py"
    code = swap(
        guest.read_text(),
        "import campaign_guest as t08\n",
        "import campaign_guest as t08\nfrom r22_guest import hold_collector, stop_scorer, witness\n",
    )
    code = swap(
        code,
        "            scorer, _ = t08.BASE.start_process(\n",
        f'''            command = ["/lab/uri76-shadow", str(score), "/lab/uri76-model", "swiglu", "/lab/ort.so", "--research-manifest-sha", "{SCOPE}"]
            previous_scorer = None
            scorer, _ = t08.BASE.start_process(
''',
    )
    code = swap(
        code,
        """                [
                    "/lab/uri76-shadow",
                    str(score),
                    "/lab/uri76-model",
                    "logistic",
                    "/lab/ort.so",
                ],""",
        "                command,",
    )
    code = swap(
        code,
        '                    "--rust-shadow-socket",',
        '                    "--representation-history",\n                    "--rust-shadow-socket",',
    )
    code = swap(
        code,
        "                    count += 1\n",
        """                    if index in (4, 6):
                        stop_scorer(scorer, score)
                    if index == 5 and scorer.poll() is not None:
                        previous_scorer = scorer.pid
                        scorer, _ = t08.BASE.start_process("r22-shadow-recovered", command, processes)
                        unified.wait_socket(score, scorer)
                    count += 1
""",
    )
    code = swap(
        code,
        "                    start = time.monotonic_ns()\n",
        """                    if index == 3:
                        hold_collector(capture)
                    start = time.monotonic_ns()
""",
    )
    code = swap(
        code,
        '                            result["uri76"] = attach(result, projections[0], rid, boot)\n',
        """                            result["uri76"] = attach(result, projections[0], rid, boot)
                            result["uri76"]["history"] = projections[0]["history_diagnostic"]
""",
    )
    code = swap(
        code,
        '                    PILOT.emit("ATTEMPT", attempt=index, **result)\n',
        """                    PILOT.emit("ATTEMPT", attempt=index, **result)
                    witness(PILOT.RUN, index, result, rid, PILOT.emit, scorer, previous_scorer)
""",
    )
    guest.write_text(code)
    compile(code, str(guest), "exec")
    for path in (config, guest):
        pins["/" + str(path.relative_to(root))] = file_sha256(path)


def capture(args):
    base = base_module()
    args.index, args.campaign = 0, args.output.name + "-benign"
    model_dir = args.output / "bundle"
    verify(model_dir)
    require(file_sha256(args.scorer) == RUST, "Rust shadow binary digest mismatch")
    base.unified.RUST = args.scorer
    original_roster, original_extend, durable = base.roster, base.extend, base.pilot.durable
    base.roster = lambda index: benign_roster(original_roster(index))

    def extend(root, pins):
        original_extend(root, pins)
        stage_guest(base, root, pins, model_dir)

    ri = None

    def bridge(log, record):
        nonlocal ri
        durable(log, record)
        if record["kind"] == "READY":
            require(ri is None, "Duplicate RI v2 worker")
            ri = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(REPO_ROOT / "scripts/ai-shadow-worker.py"),
                    "--socket",
                    str(args.runtime / "ri.sock"),
                    "--output",
                    str(args.runtime / "ri.jsonl"),
                ]
            )
            r12.wait((args.runtime / "ri.sock").is_socket, timeout=8, process=ri)
            require(
                Path(f"/proc/{ri.pid}/cgroup").read_text() == Path("/proc/self/cgroup").read_text(),
                "RI v2 ownership",
            )
        if record.get("component") == "r22_live_edge":
            ack = args.output / f"ack-{record['attempt']}.json"
            r12.wait(ack.is_file, timeout=20)
            require(
                read(ack) == {"receipt_sha256": record["receipt_sha256"]},
                "Unbound host acknowledgement",
            )

    base.extend, base.pilot.durable = extend, bridge
    try:
        return base.worker(args)
    finally:
        if ri is not None:
            r12.live.terminate(ri)
            atomic_json(
                args.output / "ri-lifecycle.json",
                {
                    "pid": ri.pid,
                    "returncode": ri.returncode,
                    "socket_removed": not (args.runtime / "ri.sock").exists(),
                },
            )


def matching(path, **fields):
    return [
        row
        for row in r12.live.rows(path)
        if all(row.get(key) == value for key, value in fields.items())
    ]


def collect(out, pg, runtime, ledger, vm, reviewed):
    sys.path.insert(0, str(r12.live.BUNDLE))
    from infer import RequestPredictor

    reference = RequestPredictor(r12.live.BUNDLE)
    challenger = cpu_session(out / "bundle/swiglu.onnx", 1)
    model = verify(out / "bundle")
    cut = model["tuning_calibration"]["threshold"]
    plan_path = ledger.with_name("unified-stage.json")
    history = []
    ids = set()
    review = labels(reviewed)
    for i, phase in enumerate(PHASES, 1):
        [witness] = r12.wait(
            lambda: matching(ledger, component="r22_live_edge", attempt=i),
            timeout=170 if i == 1 else 28,
            process=vm,
        )
        [row] = matching(ledger, kind="ATTEMPT", attempt=i)
        [permit] = matching(ledger, kind="PERMIT", attempt=i)
        planned = read(plan_path)["plan"]["rows"][i - 1]
        require(
            digest(row) == witness["receipt_sha256"] and bool(permit.get("resource_gate")),
            "Receipt or permit binding",
        )
        r12.readiness.native_sources(row)
        require(
            row["oracle_verified"]
            and row["http_status"] == HTTP[i - 1]
            and row["structural_mask"] == "NSA"
            and not row["invalid_source_rows"],
            "Oracle, HTTP or structural integrity",
        )
        require(
            i != 2
            or (
                row["oracle_basis"] == "JDBC_LOGIN_MUTATION_AND_SESSION_ROTATION"
                and "bodyless_204" in row["http"]["offsets_ns"]
            ),
            "Login Oracle or bodyless 204 timing",
        )
        if phase == "collector_held":
            require(row["native_mask"] == "NONE", "Delayed collector leaked into cutoff")
        sources = {event["source"]: event for event in row["events"]}
        require(set(sources) == set("NSA"), "Missing structural source")
        telemetry = witness["telemetry"]
        rid = telemetry["request_id"]
        require(
            re.fullmatch(r"[a-f0-9]{32}", rid) is not None
            and rid not in ids
            and telemetry["method"] == planned["method"],
            "Trusted request identity mismatch",
        )
        ids.add(rid)
        proj = row["uri76"]
        vector_sha = r12.readiness.projection(
            row, {"boot_scope": proj["boot_scope"], "campaign": proj["campaign"]}
        )
        vector = np.array(proj["vector"], dtype="<f4")
        require(
            vector_sha is not None
            and vector.tobytes() == from_request(planned["target"], planned["method"]).tobytes(),
            "URI76 preprocessing or cutoff mismatch",
        )
        sensor = sources["S"]
        flow, tx = sensor["sensor_tx"]
        rusty = proj["shadow"]
        down = phase in {"shadow_down", "ri_only_rollback"}
        elapsed = rusty["available_monotonic_ns"] - row["send_monotonic_ns"]
        r20 = {
            "status": rusty["status"],
            "model_version": "uri76-swiglu-dev-v1",
            "sha256": ONNX,
            "availability_offset_ns": elapsed,
            "threshold_scope": "WAF_DEVELOPMENT_ONLY",
        }
        if down:
            require(
                rusty["status"] == "ABSTAIN"
                and rusty["reason"] == "SCORER_UNAVAILABLE"
                and not witness["scorer"]["running"],
                "Shadow failover was not isolated",
            )
            r20.update(
                reason="ROLLBACK_DISABLED" if phase == "ri_only_rollback" else rusty["reason"]
            )
        else:
            expected = float(challenger.run(["score"], {"input": vector[None, :]})[0][0])
            require(
                rusty["status"] == "SCORED"
                and rusty["model_sha256"] == ONNX
                and rusty["model_version"] == r20["model_version"]
                and rusty["hybrid_allowed"] is False
                and proj["shadow_in_time"]
                and witness["scorer"]["running"],
                "R20 score did not bind before cutoff",
            )
            require(
                abs(rusty["score"] - expected) <= 1e-7
                and (rusty["score"] > cut) == (expected > cut),
                "Calibrated Rust/Python numerical or threshold mismatch",
            )
            r20.update(
                score=rusty["score"],
                parity_abs_error=abs(rusty["score"] - expected),
                latency_ms=rusty["inference_ns"] / 1e6,
                above_threshold=rusty["score"] > cut,
            )
        if phase == "shadow_recovered":
            require(
                witness["scorer"]["previous_pid"]
                == history[0]["scorer"]["pid"]
                != witness["scorer"]["pid"],
                "Recovery did not launch a new scorer",
            )
        stamp = datetime.fromisoformat(telemetry["timestamp"])
        require(abs((datetime.now(UTC) - stamp).total_seconds()) < 30, "Stale bridge receipt")
        proof_sha = digest([witness["receipt_sha256"], row["structural_edges"]])
        correlated = {
            "schema_version": "three-source-1",
            "request_id": rid,
            "sensor_instance": digest([out.name, proj["boot_scope"]])[:32],
            "observed_at": telemetry["timestamp"],
            "status": "MATCHED",
            "sources": ["NGINX", "SURICATA", "STUDENT_AUDIT"],
            "flow_id": flow,
            "tx_id": tx,
            "duplicate_events": row["duplicates"],
            "flow_context_alerts": 0,
            "late_event": row["native_mask"] != "NSA",
            "basis": "EDGE_RESPONSE_ID_AND_HTTP_CONSISTENCY",
            "proof_sha256": proof_sha,
            "glu": None,
            "enforcement_actions": 0,
        }
        r12.add(runtime / "correlation.jsonl", correlated)
        r12.wait(
            lambda: r12.pg_query(pg, "SELECT report->>'status' FROM ai_shadow_worker") == "READY",
            timeout=6,
        )
        start = time.monotonic_ns()
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as bridge:
            bridge.sendto(b"ai_shadow: " + json.dumps(telemetry).encode(), str(runtime / "ri.sock"))
        [ri] = r12.wait(
            lambda: matching(runtime / "ri.jsonl", request_id=rid), timeout=8, process=vm
        )
        headers = "\r\n".join(
            f"{key}: {value}"
            for key, value in telemetry["headers"].items()
            if value not in ("-", "")
        )
        expected = reference.predict(
            {
                "schema_version": "integration-request-1",
                "record_id": rid,
                "http_request": {
                    "method": telemetry["method"],
                    "url": telemetry["url"],
                    "headers": headers,
                    "body": None,
                },
            }
        )["score"]
        require(
            ri["status"] == "SCORED"
            and ri["manifest_sha256"] == r12.live.MODEL_SHA
            and ri["model_version"] == r12.RI_VERSION
            and abs(ri["score"] - expected) <= 1e-7
            and ri["enforcement_actions"] == 0,
            "RI v2 parity or model identity",
        )

        def persisted():
            raw = r12.pg_query(
                pg,
                f"""
                SELECT json_build_object('policy', h.decision, 'correlation', c.result,
                  'ri', a.result, 'fingerprint', h.evidence_fingerprint)
                FROM hybrid_incidents h JOIN request_correlations c USING(request_id)
                JOIN ai_shadow_results a USING(request_id) WHERE h.request_id='{rid}'
            """,
            )
            result = json.loads(raw) if raw else None
            if result and f"ai:{ri['event_id']}" in result["policy"]["evidence_ids"]:
                return result
            return None

        stored = r12.wait(persisted, timeout=8, process=vm)
        policy, correlation = stored["policy"], stored["correlation"]
        require(
            policy["request_id"] == correlation["request_id"] == stored["ri"]["request_id"] == rid
            and stored["ri"]["event_id"] == ri["event_id"]
            and correlation["proof_sha256"] == proof_sha
            and correlation["late_event"] == correlated["late_event"]
            and (correlation["flow_id"], correlation["tx_id"]) == (flow, tx),
            "Rust correlation or RI v2 identity mismatch",
        )
        require(
            policy["automatic_block"] is False
            and policy["fresh"] is True
            and policy["ai"]["model_id"] == r12.RI_VERSION
            and abs(policy["ai"]["score"] - ri["score"]) <= 1e-12,
            "Hybrid received wrong model or score",
        )
        require(
            policy["rule_risk_component"] == 0
            and policy["policy_action"] == ("ALERT" if ri["above_threshold"] else "LOG_ONLY"),
            "Unexpected benign policy decision",
        )
        item = {
            "phase": phase,
            "attempt": i,
            "request_id": rid,
            "request_key": row["request_key"],
            "lineage": {
                "campaign": proj["campaign"],
                "boot_scope": proj["boot_scope"],
                "workflow": planned["oracle"],
                "session_scope": "SAME_LAB_SESSION_ENGINEERING_ONLY",
            },
            "role": "ENGINEERING_UNASSIGNED",
            "receipt_sha256": witness["receipt_sha256"],
            "cutoff_ns": row["cutoff_ns"],
            "guard_ns": row["clock_guard_ns"],
            "clock_span_ns": row["clock_offset_span_ns"],
            "source_mask_at_cutoff": row["native_mask"],
            "structural_mask": row["structural_mask"],
            "scope": "CONTROLLED_COLLECTOR_DELAY"
            if phase == "collector_held"
            else "NATURAL_ACQUISITION",
            "sources": observed_sources(row["events"]),
            "cutoff_edges": row["cutoff_edges"],
            "correlation_sha256": proof_sha,
            "uri76": {
                "sha256": vector_sha,
                "transform_sha256": proj["transform_sha256"],
                "vector": proj["vector"],
                "observed_offset_ns": proj["mirror_receipt_offset_ns"],
                "available_offset_ns": proj["projection_offset_ns"],
                "feature_availability": {
                    name: bool(vector[schema()["columns"].index(name)]) for name in FEATURES
                },
                "history": proj["history"],
            },
            "r20": r20,
            "ri_v2": {
                k: ri[k]
                for k in (
                    "status",
                    "event_id",
                    "model_version",
                    "manifest_sha256",
                    "feature_availability",
                    "observed_at",
                    "score",
                    "above_threshold",
                    "latency_ms",
                )
            }
            | {"scope": "POST_OBSERVATION_RI_V2_BRIDGE"},
            "rule": {
                "request_rule_risk": policy["rule_risk_component"],
                "sources": policy["rule_sources"],
            },
            "hybrid": {
                "action": policy["policy_action"],
                "score_model": policy["ai"]["model_id"],
                "automatic_block": False,
                "decision_fingerprint": stored["fingerprint"],
                "bridge_elapsed_ns": time.monotonic_ns() - start,
            },
            "oracle": {
                "verified": row["oracle_verified"],
                "basis": row["oracle_basis"],
                "available_offset_ns": row["oracle_observed_offset_ns"],
                "jdbc": row["jdbc"],
            },
            "label": review.get(
                row["request_key"], {"kind": "UNLABELED_OBSERVATION", "class": None}
            ),
            "http_status": row["http_status"],
            "http_offsets_ns": row["http"]["offsets_ns"],
            "scorer": witness["scorer"],
        }
        append(out / "quality-ledger.json", out.name, len(PHASES), item)
        history.append(item)
        atomic_json(out / f"ack-{i}.json", {"receipt_sha256": witness["receipt_sha256"]})
    require(
        any(
            r["source_mask_at_cutoff"] == "NSA" and r["r20"]["status"] == "SCORED" for r in history
        ),
        "No natural NSA with paired scores",
    )
    return history


def workload(args, database, pg, reviewed):
    out = args.output
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "RUST_LOG": "info",
        "TOKIO_WORKER_THREADS": "2",
    }
    with tempfile.TemporaryDirectory(prefix="idps-r22-") as directory:
        runtime = Path(directory)
        logs = {
            k: runtime / k
            for k in ("SURICATA_EVE_PATH", "NGINX_ACCESS_PATH", "STUDENT_AUDIT_LOG_PATH")
        }
        for path in (*logs.values(), runtime / "correlation.jsonl", runtime / "ri.jsonl"):
            path.touch(mode=0o600)
        password_hash = subprocess.run(
            [r12.BINARY, "--hash-password"],
            input=secrets.token_urlsafe(32) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=6,
            env=env,
        ).stdout.strip()
        require(password_hash.startswith("$argon2"), "Private executor password setup")
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        security = subprocess.Popen(
            [r12.BINARY],
            cwd=runtime,
            env=env
            | {k: str(p) for k, p in logs.items()}
            | {
                "DATABASE_URL": database,
                "ADMIN_USERNAME": "r22",
                "ADMIN_PASSWORD_HASH": password_hash,
                "APP_ADDR": f"127.0.0.1:{port}",
                "ENFORCEMENT_MODE": "OFF",
                "AUTO_BLOCK": "false",
                "PBL4_FIREWALL_CMD": "/bin/false",
                "AI_SHADOW_RESULTS_PATH": str(runtime / "ri.jsonl"),
                "THREE_SOURCE_RESULTS_PATH": str(runtime / "correlation.jsonl"),
            },
        )
        vm = None
        try:

            def ready():
                with socket.socket() as sock:
                    sock.settimeout(0.1)
                    return sock.connect_ex(("127.0.0.1", port)) == 0

            r12.wait(ready, timeout=8, process=security)
            resource = out / "guest-resource"
            vm = subprocess.Popen(
                r12.resource_command(
                    resource,
                    "DATA",
                    100,
                    3072,
                    [
                        sys.executable,
                        "-B",
                        str(Path(__file__).resolve()),
                        "capture",
                        str(out),
                        "--runtime",
                        str(runtime),
                        "--iso",
                        str(args.iso),
                        "--h2",
                        str(args.h2),
                        "--numpy",
                        str(args.numpy),
                        "--scorer",
                        str(args.scorer),
                    ],
                )
            )
            ledger = resource / "guest/receipt-ledger.jsonl"
            cases = collect(out, pg, runtime, ledger, vm, reviewed)
            require(vm.wait(timeout=18) == 0, "Guest finalizer failed")
            adapter, qemu = read(resource / "result.json"), read(resource / "guest/qemu.json")
            lifecycle = read(out / "ri-lifecycle.json")
            require(
                adapter["reason"] == "COMPLETED"
                and adapter["cleanup_verified"]
                and qemu["qemu_returncode"] == 0
                and qemu["dispatched"] == qemu["outcomes"] == len(PHASES)
                and lifecycle["returncode"] == 0
                and lifecycle["socket_removed"],
                "Guest, QEMU or host worker cleanup",
            )
            require(
                r12.pg_query(pg, "SELECT count(*) FROM firewall_actions") == "0"
                and r12.pg_query(pg, "SELECT count(*) FROM hybrid_proposals") == "0",
                "Actuator or proposal unexpectedly used",
            )
            atomic_json(
                out / "quality-summary.json",
                summarize(cases)
                | {
                    "ledger_sha256": file_sha256(out / "quality-ledger.json"),
                    "guest_ledger_sha256": file_sha256(ledger),
                    "adapter": adapter,
                    "qemu": qemu,
                    "firewall_actions": 0,
                    "hybrid_proposals": 0,
                },
            )
        finally:
            r12.live.terminate(security)
            if vm is not None and vm.poll() is None:
                # Missing host ack terminates the guest's bounded dispatch.
                vm.wait(timeout=35)


def supervise(args):
    out = args.output
    out.mkdir(mode=0o700, exist_ok=True)
    with (out / "supervisor.lock").open("x", encoding="utf-8") as claim:
        claim.write(os.environ.get("INVOCATION_ID", str(os.getpid())) + "\n")
    atomic_json(out / "status.json", {"state": "RUNNING", "run_id": out.name, "pid": os.getpid()})
    try:
        require(
            file_sha256(r12.BINARY) == BINARY_SHA
            and file_sha256(r12.live.BUNDLE / "manifest.json") == r12.live.MODEL_SHA,
            "Private Rust executor or RI v2 digest changed",
        )
        for path in (args.iso, args.h2, args.numpy, args.scorer):
            require(path.is_file(), "Missing local guest dependency")
        stage(out / "bundle")
        reviewed = r12.readiness.reviewed(args.handoff)
        atomic_json(out / "admission.json", {k: v for k, v in reviewed.items() if k != "requests"})
        r12.replay.run(out, lambda work, db, pg: workload(args, db, pg, reviewed))
        require(read(out / "postgres-resource.json")["cleanup"] is True, "PostgreSQL cleanup")
        atomic_json(
            out / "status.json",
            {
                "state": "COMPLETED",
                "run_id": out.name,
                "shadow": "PASS",
                "hybrid_release": "BLOCKED_T07_NATIVE_INDEPENDENT_COHORT",
                "summary_sha256": file_sha256(out / "quality-summary.json"),
            },
        )
    except Exception as exc:
        atomic_json(
            out / "status.json",
            {
                "state": "BLOCKED",
                "run_id": out.name,
                "reason": type(exc).__name__,
                "checkpoint_cursor": read(out / "quality-ledger.json")["cursor"]
                if (out / "quality-ledger.json").exists()
                else 0,
            },
        )
        raise


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("supervise", "capture"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--handoff", type=Path)
    parser.add_argument(
        "--iso", type=Path, default=Path.home() / "Downloads/ubuntu-26.04-live-server-amd64.iso"
    )
    parser.add_argument(
        "--h2",
        type=Path,
        default=Path.home() / ".m2/repository/com/h2database/h2/2.4.240/h2-2.4.240.jar",
    )
    parser.add_argument("--numpy", type=Path, default=r12.NUMPY)
    parser.add_argument("--scorer", type=Path, default=SCORER_PATH)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.action == "capture":
        require(args.runtime is not None, "Private runtime required")
        raise SystemExit(capture(args))
    supervise(args)

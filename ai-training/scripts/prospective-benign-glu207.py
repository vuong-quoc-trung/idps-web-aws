"""Frozen, bounded benign evaluation in the owned Student/Nginx/Suricata lab.

The collector labels only predeclared, semantically verified lab workflows.
It never derives labels from model predictions, status alone, or EVE alerts.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import psutil

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import collect, iter_rows, verify_dataset
from idps_ai.data.lab_capture import LabClient
from idps_ai.data.lab_runtime import start_lab, stop_lab, verify_lab_cleanup
from idps_ai.data.privacy import pseudonym
from idps_ai.data.readers import Input
from idps_ai.data.sensor_decode import _EveHandler, _EveServer
from idps_ai.data.sensor_lab import _Relay, _RelayHandler
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import FeatureExtractor, feature_columns, transform
from idps_ai.training.checkpoint import load_checkpoint

AI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parent
MODEL = AI_ROOT / ".artifacts/research_glu207_bounded_final_20261104"
SPEC = AI_ROOT / ".artifacts/scale_upgrade_20261030/prepared-v5/feature_spec.json"
NGINX = REPO_ROOT / ".local-dev/foundation/tools/runtime/usr/sbin/nginx"
RUNTIME = AI_ROOT / ".artifacts/upgrade_20261028/tools/runtime"
DEFAULT_ROOT = AI_ROOT / ".artifacts/pb27_1104c"
_LIVE_SPEC = importlib.util.spec_from_file_location(
    "idps_ai_live_shadow_lab", Path(__file__).with_name("live-shadow-lab.py")
)
if _LIVE_SPEC is None or _LIVE_SPEC.loader is None:
    raise PipelineError("Existing live sensor helper is unavailable")
_LIVE_MODULE = importlib.util.module_from_spec(_LIVE_SPEC)
_LIVE_SPEC.loader.exec_module(_LIVE_MODULE)
_ReceiptLog = _LIVE_MODULE._ReceiptLog
_sensor_config = _LIVE_MODULE._sensor_config


def campaign():
    items = [
        {"offset": 0, "kind": "csrf", "path": "/api/auth/csrf"},
        {"offset": 2, "kind": "login", "path": "/api/auth/login"},
        {"offset": 4, "kind": "csrf", "path": "/api/auth/csrf"},
        {"offset": 6, "kind": "me", "path": "/api/auth/me"},
    ]
    routes = ("faculties", "majors", "classes", "training-programs")
    for index in range(23):
        kind = "create" if index == 7 else "created_get" if index == 8 else "page"
        if kind == "create":
            path = "/api/faculties"
        elif kind == "created_get":
            path = "/api/faculties/{created_id}"
        else:
            route = routes[index % len(routes)]
            query = {"page": str(index % 3), "size": str(2 + index % 7)}
            if index in (3, 11, 17, 21):
                query["q"] = ("C++ basics", "100% complete", "a&b", "Nguyễn học tập")[
                    (3, 11, 17, 21).index(index)
                ]
            path = "/api/" + route + "?" + urlencode(query)
        items.append({"offset": 20 + index * 20, "kind": kind, "path": path})
    return items


def plan_data():
    return {
        "format_version": 1,
        "purpose": "prospective_benign_lab_score_diagnostic_no_threshold",
        "campaign_id": "benign-prospective-20261104-01",
        "scope": "AI-owned disposable loopback Student lab; valid workflows only",
        "script_sha256": file_sha256(__file__),
        "checkpoint_manifest_sha256": file_sha256(
            MODEL / "run/checkpoints/step-000000000652-90272717f88f/manifest.json"
        ),
        "onnx_sha256": file_sha256(MODEL / "research-final.onnx"),
        "feature_spec_sha256": file_sha256(SPEC),
        "nginx_sha256": file_sha256(NGINX),
        "suricata_sha256": file_sha256(RUNTIME / "usr/bin/suricata"),
        "threshold": None,
        "threshold_reason": "Research step652 checkpoint has no valid locked calibration threshold",
        "observation_seconds": 460,
        "early_before_seconds": 65,
        "warm_after_seconds": 300,
        "request_manifest": campaign(),
        "oracle": "Expected authenticated fixture identity, schema and pagination, plus created-faculty identity readback. A status code alone never verifies benign intent.",
        "dedup": "unique client X-Request-Id and one Student, one Nginx, one EVE HTTP observation per request; unique float32 vector SHA counted separately",
        "metrics": [
            "physical_request_count",
            "three_source_count",
            "lab_benign_verified",
            "unknown",
            "unique_float32_views",
            "prior_flow_by_phase",
            "history_flags_by_phase",
            "score_distribution_by_phase",
            "ONNX_forward_latency_ms",
            "FPR_if_valid_threshold_else_null",
        ],
        "attack_recall": None,
        "model_selection": False,
        "holdout_access": False,
    }


def prepare(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic_json(root / "plan.json", plan_data())
    print(json.dumps({"plan": str(root / "plan.json"), "sha256": file_sha256(root / "plan.json")}))


def oracle(kind, response, data, expected_path, created):
    status = response["status_code"]
    if kind == "login":
        return status == 204 and data == b"", {}, None
    if status not in (200, 201):
        return False, {"status": status}, None
    try:
        value = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False, {"json_valid": False}, None
    if kind == "csrf":
        valid = (
            isinstance(value, dict)
            and value.get("headerName") == "X-CSRF-TOKEN"
            and isinstance(value.get("token"), str)
            and len(value["token"]) >= 16
        )
        return valid, {"csrf_shape_valid": bool(valid)}, None
    if kind == "me":
        valid = (
            isinstance(value, dict)
            and value.get("username") == "ai_lab_02"
            and value.get("role") == "ADMIN"
            and value.get("enabled") is True
        )
        return valid, {"fixture_identity_valid": bool(valid)}, None
    if kind == "create":
        valid = (
            status == 201
            and isinstance(value, dict)
            and isinstance(value.get("id"), int)
            and value.get("shortCode") == "BENIGN01"
            and value.get("name") == "O'Connor Research"
            and value.get("active") is True
        )
        return valid, {"created_identity_valid": bool(valid)}, value["id"] if valid else None
    if kind == "created_get":
        valid = (
            isinstance(value, dict)
            and value.get("id") == created
            and value.get("shortCode") == "BENIGN01"
            and value.get("name") == "O'Connor Research"
        )
        return valid, {"created_readback_valid": bool(valid)}, None
    query = expected_path.split("?", 1)[1]
    params = dict(part.split("=", 1) for part in query.split("&"))
    valid = (
        isinstance(value, dict)
        and isinstance(value.get("content"), list)
        and value.get("page") == int(params["page"])
        and value.get("size") == int(params["size"])
        and isinstance(value.get("totalElements"), int)
        and isinstance(value.get("totalPages"), int)
    )
    return valid, {"page_shape_and_parameters_valid": bool(valid)}, None


def worker(root, plan):
    def stop(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    lab = root / "lab"
    marker = load_json(lab / "owned-lab.json")
    config = "user root;\n" + (lab / "nginx.conf").read_text()
    config = config.replace("127.0.0.1:18880", "unix:" + str(lab / "student.sock"))
    (lab / "live-nginx.conf").write_text(config)
    nginx_log = (root / "live-nginx.log").open("wb")
    nginx = subprocess.Popen(
        [
            marker["nginx_binary"],
            "-p",
            str(lab) + "/",
            "-c",
            str(lab / "live-nginx.conf"),
            "-g",
            "daemon off;",
        ],
        stdout=nginx_log,
        stderr=nginx_log,
    )
    config_path = _sensor_config(root, RUNTIME)
    eve_file = (root / "eve.json").open("x")
    eve_file.reconfigure(line_buffering=True)
    (root / "eve.json").chmod(0o600)
    eve_server = _EveServer(str(root / "eve.sock"), _EveHandler)
    (root / "eve.sock").chmod(0o600)
    eve_server.destination = eve_file
    eve_server.query_numeric = True
    eve_server.query_version = 2
    eve_server.request_structure = False
    eve_server.completed = threading.Event()
    eve_server.failed = False
    thread = threading.Thread(target=eve_server.serve_forever, daemon=True)
    thread.start()
    env = dict(os.environ, LD_LIBRARY_PATH=str(RUNTIME / "usr/lib/x86_64-linux-gnu"))
    sensor_log = (root / "live-suricata.log").open("wb")
    sensor = subprocess.Popen(
        [
            str(RUNTIME / "usr/bin/suricata"),
            "-c",
            str(config_path),
            "--runmode",
            "single",
            "-k",
            "none",
            "-i",
            "lo",
            "-l",
            str(root),
            "--set",
            "detect.profile=low",
        ],
        env=env,
        stdout=sensor_log,
        stderr=sensor_log,
    )
    trackers = []
    try:
        time.sleep(3)
        if sensor.poll() is not None or nginx.poll() is not None or eve_server.failed:
            raise PipelineError("Nginx or live sensor did not start")
        trackers = [
            _ReceiptLog(
                lab / "student-audit.log", "student", (lab / "student-audit.log").stat().st_size
            ),
            _ReceiptLog(lab / "access.log", "nginx", (lab / "access.log").stat().st_size),
            _ReceiptLog(root / "eve.json", "suricata"),
        ]
        client = LabClient(18881, "127.0.0.250")
        password = load_json(lab / "accounts-private.json")["password"]
        started = time.monotonic()
        records = []
        created_id = None
        for index, item in enumerate(plan["request_manifest"]):
            while time.monotonic() - started < item["offset"]:
                time.sleep(min(0.25, item["offset"] - (time.monotonic() - started)))
            path = item["path"].replace("{created_id}", str(created_id))
            if "None" in path:
                raise PipelineError("Created faculty readback has no ID")
            body = None
            if item["kind"] == "login":
                body = urlencode({"username": "ai_lab_02", "password": password})
            elif item["kind"] == "create":
                body = {
                    "shortCode": "BENIGN01",
                    "name": "O'Connor Research",
                    "description": "Disposable owned lab fixture",
                    "active": True,
                }
            sent = time.time()
            response, data = client.request("POST" if body is not None else "GET", path, body)
            if item["kind"] == "csrf":
                try:
                    client.csrf = json.loads(data)
                except ValueError:
                    client.csrf = None
            valid, fact, new_id = oracle(item["kind"], response, data, path, created_id)
            if new_id is not None:
                created_id = new_id
            rid = response["request_id"]
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not all(rid in t.receipts for t in trackers):
                if sensor.poll() is not None or eve_server.failed:
                    break
                time.sleep(0.02)
            receipt = {t.source: len(t.receipts.get(rid, [])) for t in trackers}
            records.append(
                {
                    "index": index,
                    "request_id": rid,
                    "timestamp": response["timestamp"],
                    "sent_unix": sent,
                    "offset_seconds": time.monotonic() - started,
                    "phase": "EARLY"
                    if item["offset"] < 65
                    else "WARMING"
                    if item["offset"] < 300
                    else "WARM",
                    "kind": item["kind"],
                    "method": "POST" if body is not None else "GET",
                    "path_sha256": hashlib.sha256(path.encode()).hexdigest(),
                    "response_sha256": hashlib.sha256(data).hexdigest(),
                    "response_status": response["status_code"],
                    "oracle_valid": bool(valid),
                    "oracle_fact": fact,
                    "receipts": receipt,
                    "receipt_delays_ms": {
                        t.source: (t.receipts[rid][0] - sent) * 1000
                        for t in trackers
                        if rid in t.receipts
                    },
                }
            )
            atomic_json(
                root / "capture-progress.json",
                {
                    "done": len(records),
                    "planned": len(plan["request_manifest"]),
                    "elapsed_seconds": time.monotonic() - started,
                },
            )
        if any(t.error for t in trackers) or eve_server.failed:
            raise PipelineError("Receipt tracker or EVE redaction failed")
        if len(records) >= 4 and not records[3]["oracle_valid"]:
            records[1]["oracle_valid"] = False
            records[1]["oracle_fact"]["subsequent_fixture_identity_valid"] = False
        elif len(records) >= 4:
            records[1]["oracle_fact"]["subsequent_fixture_identity_valid"] = True
        atomic_json(
            root / "observer.json",
            {
                "plan_sha256": file_sha256(root / "plan.json"),
                "requests": records,
                "duration_seconds": time.monotonic() - started,
                "eve_counts_during": dict(trackers[2].counts),
            },
        )
    finally:
        for tracker in trackers:
            tracker.close()
        sensor.send_signal(signal.SIGINT)
        sensor.wait(timeout=20)
        nginx.send_signal(signal.SIGQUIT)
        nginx.wait(timeout=20)
        eve_server.shutdown()
        eve_server.server_close()
        (root / "eve.sock").unlink(missing_ok=True)
        eve_file.close()
        sensor_log.close()
        nginx_log.close()


def run(root):
    plan = load_json(root / "plan.json")
    if plan != plan_data() or plan["script_sha256"] != file_sha256(__file__):
        raise PipelineError("Frozen plan, code, model, or preprocessing hash changed")
    if len(plan["request_manifest"]) != 27 or plan["observation_seconds"] != 460:
        raise PipelineError("Unexpected prospective manifest")
    (root / "pseudonym-key.bin").write_bytes(os.urandom(32))
    (root / "pseudonym-key.bin").chmod(0o600)
    start_lab(root / "lab", NGINX, campaigns=15, input_profile="safe_query_numeric_v2")
    lab = root / "lab"
    relay = None
    worker_started = False
    try:
        marker = load_json(lab / "owned-lab.json")
        old_nginx = psutil.Process(marker["processes"]["nginx"]["pid"])
        if old_nginx.create_time() != marker["processes"]["nginx"]["create_time"]:
            raise PipelineError("Owned Nginx identity changed")
        old_nginx.send_signal(signal.SIGQUIT)
        old_nginx.wait(timeout=15)
        marker["processes"].pop("nginx")
        atomic_json(lab / "owned-lab.json", marker)
        relay = _Relay(str(lab / "student.sock"), _RelayHandler)
        (lab / "student.sock").chmod(0o600)
        relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
        relay_thread.start()
        with (root / "worker.log").open("wb") as log:
            process = subprocess.Popen(
                ["unshare", "-Urn", sys.executable, __file__, "worker", "--root", str(root)],
                stdout=log,
                stderr=log,
            )
            worker_started = True
            marker["processes"]["sensor_namespace"] = {
                "pid": process.pid,
                "create_time": psutil.Process(process.pid).create_time(),
            }
            atomic_json(lab / "owned-lab.json", marker)
            try:
                code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=20)
                raise PipelineError("Prospective worker exceeded 600 seconds") from None
            if code:
                raise PipelineError("Prospective worker failed; private logs retained")
    finally:
        if relay:
            relay.shutdown()
            relay.server_close()
            (lab / "student.sock").unlink(missing_ok=True)
        stop_lab(lab)
        if worker_started:
            verify_lab_cleanup(lab)
    score(root, plan)


def score(root, plan):
    observer = load_json(root / "observer.json")
    if observer["plan_sha256"] != file_sha256(root / "plan.json"):
        raise PipelineError("Observer plan checksum mismatch")
    inputs = [
        Input("student", root / "lab/student-audit.log"),
        Input("nginx", root / "lab/access.log"),
        Input("suricata", root / "eve.json"),
    ]
    key = (root / "pseudonym-key.bin").read_bytes()
    collect(inputs, root / "collected", key, input_profile="safe_query_numeric_v2")
    verify_dataset(root / "collected", "collected")
    request_map = {pseudonym(key, "request", r["request_id"]): r for r in observer["requests"]}
    if len(request_map) != len(observer["requests"]):
        raise PipelineError("Duplicate planned physical request ID")
    spec = load_json(SPEC)
    if len(spec["columns"]) != 207 or spec["columns"] != feature_columns(
        input_profile="safe_query_numeric_v2", behavior_dynamics=True
    ):
        raise PipelineError("207-feature contract mismatch")
    extractor = FeatureExtractor(**spec["state_limits"])
    session = cpu_session(MODEL / "research-final.onnx", max_threads=4)
    model = load_checkpoint(MODEL / "run").model
    if model.steps != 652 or sum(p.size for p in model.parameters.values()) != 9_675_784:
        raise PipelineError("Frozen GLU checkpoint mismatch")
    records = []
    seen = set()
    for row in iter_rows(root / "collected/requests.parquet"):
        values = extractor.observe(row)
        request = request_map.get(row["request_key"])
        if request is None:
            continue
        if row["request_key"] in seen:
            raise PipelineError("Duplicate fused request")
        seen.add(row["request_key"])
        complete = (
            set(row["sources"]) == {"STUDENT_AUDIT", "NGINX", "SURICATA"}
            and row["correlation"] == "request_id"
            and all(v == 1 for v in request["receipts"].values())
        )
        numeric = json.loads(row["numeric_json"] or "{}")
        required_inputs = all(
            row.get(name) is not None
            for name in ("status_code", "latency_ms", "request_bytes", "response_bytes")
        ) and all(
            numeric.get(name) == 1.0
            for name in ("uri_lexical_available", "query_lexical_available", "structure_available")
        )
        vector = transform(spec, values)
        valid_vector = vector.shape == (207,) and bool(np.isfinite(vector).all())
        latency = None
        score_value = None
        parity = None
        if complete and valid_vector and required_inputs:
            start = time.perf_counter_ns()
            output, probabilities = session.run(None, {"input": vector[None, :]})
            latency = (time.perf_counter_ns() - start) / 1e6
            native, native_probabilities = model.predict(vector[None, :])
            parity = bool(
                np.allclose(output, native, rtol=1e-5, atol=1e-6)
                and np.allclose(probabilities, native_probabilities, rtol=1e-5, atol=1e-6)
            )
            score_value = float(output[0])
        records.append(
            {
                "index": request["index"],
                "phase": request["phase"],
                "oracle_valid": request["oracle_valid"],
                "three_source": complete,
                "vector_complete": valid_vector,
                "required_inputs_present": required_inputs,
                "ground_truth_tier": "BENIGN_VERIFIED_LAB_WORKFLOW"
                if complete and request["oracle_valid"]
                else "UNKNOWN",
                "prior_flow": values["flow_duration_seconds_missing"] == 0,
                "history": {
                    name: values[name] == 0
                    for name in (
                        "ip_10s_context_incomplete",
                        "ip_60s_context_incomplete",
                        "ip_300s_context_incomplete",
                        "user_10s_context_incomplete",
                        "user_60s_context_incomplete",
                        "user_300s_context_incomplete",
                    )
                },
                "score": score_value,
                "onnx_forward_ms": latency,
                "onnx_native_parity": parity,
                "view_sha256": hashlib.sha256(vector.tobytes()).hexdigest()
                if valid_vector
                else None,
            }
        )
    if len(records) != len(request_map):
        raise PipelineError("Some planned requests did not appear in fused collector")
    by_phase = {}
    for phase in ("EARLY", "WARMING", "WARM"):
        group = [r for r in records if r["phase"] == phase]
        scores = [r["score"] for r in group if r["score"] is not None]
        by_phase[phase] = {
            "requests": len(group),
            "benign_verified_lab": sum(
                r["ground_truth_tier"] == "BENIGN_VERIFIED_LAB_WORKFLOW" for r in group
            ),
            "prior_flow": sum(r["prior_flow"] for r in group),
            "history_complete": {
                name: sum(r["history"][name] for r in group) for name in records[0]["history"]
            },
            "score_median": float(np.median(scores)) if scores else None,
            "score_p95": float(np.percentile(scores, 95)) if scores else None,
        }
    scored = [r for r in records if r["score"] is not None]
    latencies = [r["onnx_forward_ms"] for r in scored]
    report = {
        "status": "PROSPECTIVE_BENIGN_LAB_SCORE_DIAGNOSTIC",
        "plan_sha256": file_sha256(root / "plan.json"),
        "observer_sha256": file_sha256(root / "observer.json"),
        "source_sha256": {i.source: file_sha256(i.path) for i in inputs},
        "collected_manifest_sha256": file_sha256(root / "collected/dataset_manifest.json"),
        "capture_seconds": observer["duration_seconds"],
        "physical_requests": len(records),
        "three_source": sum(r["three_source"] for r in records),
        "benign_verified_lab": sum(
            r["ground_truth_tier"] == "BENIGN_VERIFIED_LAB_WORKFLOW" for r in records
        ),
        "unknown": sum(r["ground_truth_tier"] == "UNKNOWN" for r in records),
        "unique_feature_views": len({r["view_sha256"] for r in records if r["view_sha256"]}),
        "vector_complete": sum(r["vector_complete"] for r in records),
        "prior_flow": sum(r["prior_flow"] for r in records),
        "scored": len(scored),
        "onnx_native_parity_all": all(r["onnx_native_parity"] is True for r in scored),
        "onnx_forward_ms_p50": float(np.median(latencies)) if latencies else None,
        "onnx_forward_ms_p95": float(np.percentile(latencies, 95)) if latencies else None,
        "by_phase": by_phase,
        "threshold": None,
        "false_positives": None,
        "fpr": None,
        "fpr_confidence_interval": None,
        "recall": None,
        "formal_admitted": 0,
        "per_request_private": records,
        "quality_scope": "Single owned lab, runner-and-oracle benign tier, no independent label or cross-environment generalization; no calibrated threshold; scores do not establish FPR",
    }
    atomic_json(root / "report.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "physical_requests",
                    "three_source",
                    "benign_verified_lab",
                    "unknown",
                    "unique_feature_views",
                    "prior_flow",
                    "scored",
                    "by_phase",
                )
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run", "worker"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == "prepare":
        prepare(root)
    elif args.mode == "worker":
        plan = load_json(root / "plan.json")
        worker(root, plan)
    else:
        run(root)


if __name__ == "__main__":
    main()

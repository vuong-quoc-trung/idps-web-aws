#!/usr/bin/env python3
"""Local one-way Nginx telemetry -> frozen RIv2 -> bounded metadata journal.

Raw URI/selected headers exist only in a bounded in-memory queue, never a spool.
Socket delivery is lossy: serving never waits for inference. No enforcement API.
Run under integration-guard.py for independent thermal/cgroup supervision.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import queue
import re
import signal
import socket
import stat
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = (
    ROOT / "ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle"
)
MODEL = "request-intelligence-v2-frozen-step3072"
THRESHOLD = 0.8826237916946411
# Pin the manifest independently of the files it lists. Never trust a new model
# merely because its own manifest declares internally consistent file hashes.
MANIFEST_SHA = "b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c"


def now():
    return datetime.now(UTC).isoformat()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def read_message(raw):
    # Nginx syslog prefix is generated locally; require the specific tag.
    prefix, separator, payload = raw.partition(b"ai_shadow: ")
    if not separator or len(prefix) > 256 or len(raw) > 8192:
        raise ValueError("invalid envelope")
    value = json.loads(payload)
    if set(value) != {
        "schema_version",
        "request_id",
        "timestamp",
        "method",
        "url",
        "headers",
    }:
        raise ValueError("unexpected telemetry fields")
    if value["schema_version"] != "nginx-ai-1" or not re.fullmatch(
        r"[a-f0-9]{32}", value["request_id"]
    ):
        raise ValueError("invalid correlation")
    stamp = datetime.fromisoformat(value["timestamp"])
    if stamp.tzinfo is None or abs((datetime.now(UTC) - stamp).total_seconds()) > 60:
        raise ValueError("stale telemetry")
    if not isinstance(value["headers"], dict) or set(value["headers"]) != {
        "User-Agent",
        "Accept",
        "Content-Type",
    }:
        raise ValueError("unexpected headers")
    if not all(
        isinstance(v, str) and len(v) <= 1024 for v in value["headers"].values()
    ):
        raise ValueError("invalid headers")
    if (
        not isinstance(value["url"], str)
        or not value["url"].startswith("/")
        or len(value["url"]) > 4096
    ):
        raise ValueError("invalid target")
    if value["method"] not in {
        "GET",
        "POST",
        "HEAD",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "TRACE",
        "CONNECT",
    }:
        raise ValueError("invalid method")
    return value


class Journal:
    def __init__(self, path, limit=2 * 1024**2):
        self.path, self.limit = Path(path), limit
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.lock = threading.Lock()

    def append(self, value):
        encoded = (
            json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n"
        ).encode()
        with self.lock:
            if (
                self.path.exists()
                and self.path.stat().st_size + len(encoded) > self.limit
            ):
                # Keep three bounded generations; no raw request material here.
                for index in (2, 1):
                    source = self.path.with_name(self.path.name + f".{index}")
                    if source.exists():
                        source.replace(
                            self.path.with_name(self.path.name + f".{index + 1}")
                        )
                self.path.replace(self.path.with_name(self.path.name + ".1"))
            fd = os.open(
                self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "ab") as stream:
                stream.write(encoded)


def model_record(value):
    # The frozen API consumes header text, never a Python object.
    headers = "\r\n".join(
        f"{name}: {value['headers'][name]}"
        for name in ("User-Agent", "Accept", "Content-Type")
        if value["headers"][name] not in {"", "-"}
    )
    return {
        "schema_version": "integration-request-1",
        "record_id": value["request_id"],
        "http_request": {
            "method": value["method"],
            "url": value["url"],
            "headers": headers,
            "body": None,
        },
    }


def startup_status(temperature, available_bytes):
    if temperature >= 75:
        return "THERMAL_STOP"
    if available_bytes < 4 * 1024**3:
        return "RAM_STOP"
    return "READY"


def serve(args):
    import psutil

    os.umask(0o077)
    worker_id = uuid.uuid4().hex
    journal = Journal(args.output)
    counters = {
        "processed": 0,
        "rejected": 0,
        "queue_dropped": 0,
        "inference_errors": 0,
    }
    stop = threading.Event()
    ready = threading.Event()
    model_loaded = threading.Event()
    state = {"status": "STARTING", "cpu_temperature_c": None, "system_used_bytes": 0}
    inbox = queue.Queue(maxsize=64)
    thermal = module(ROOT / "ai-training/scripts/p0-thermal-run.py", "thermal_reader")

    def record(kind, status, request_id=None, score=None, latency=None, feature=None):
        return {
            "schema_version": "ai-shadow-1",
            "kind": kind,
            "event_id": uuid.uuid4().hex,
            "worker_id": worker_id,
            "request_id": request_id,
            "observed_at": now(),
            "model_version": MODEL,
            "manifest_sha256": MANIFEST_SHA,
            "threshold": THRESHOLD,
            "score": score,
            "above_threshold": None if score is None else score > THRESHOLD,
            "status": status,
            "mode": "shadow",
            "enforcement_actions": 0,
            "latency_ms": latency,
            "feature_availability": feature,
            "telemetry_source": "NGINX_UNIX_SYSLOG",
            "feature_profile": "selected_headers_no_body",
            "metrics": {
                **counters,
                "queue_depth": inbox.qsize(),
                "cpu_temperature_c": state["cpu_temperature_c"],
                "system_used_bytes": state["system_used_bytes"],
                "worker_rss_bytes": psutil.Process().memory_info().rss,
            },
        }

    def heartbeat(status=None):
        journal.append(record("heartbeat", status or state["status"]))

    def monitor():
        previous, previous_at = None, time.monotonic()
        last_heartbeat, cool_since = 0, None
        heat = module(
            ROOT / "ai-training/scripts/rolling-resource-policy.py", "rolling_resource"
        ).HeatWindow()
        while not stop.is_set():
            try:
                temp = max(v["celsius"] for v in thermal.cpu_sensors().values())
                mem = psutil.virtual_memory()
                used = mem.total - mem.available
                current = time.monotonic()
                rate = (
                    0
                    if previous is None
                    else (temp - previous) / max(0.1, current - previous_at)
                )
                previous, previous_at = temp, current
                state.update(cpu_temperature_c=temp, system_used_bytes=used)
                heat_metrics = heat.add(
                    current, temp, state["status"] == "THERMAL_PAUSED"
                )
                if temp >= 90 or mem.available < 4 * 1024**3:
                    ready.clear()
                    state["status"] = "THERMAL_STOP" if temp >= 90 else "RAM_STOP"
                    heartbeat()
                    stop.set()
                    break
                if (
                    heat_metrics["rolling_300s_c"] >= 80
                    or temp >= 87
                    or (temp >= 78 and rate >= 3)
                ):
                    ready.clear()
                    state["status"] = "THERMAL_PAUSED"
                    cool_since = None
                elif state["status"] == "THERMAL_PAUSED":
                    cool_since = (
                        (cool_since or current)
                        if temp < 75 and heat_metrics["rolling_300s_c"] < 77
                        else None
                    )
                    if cool_since and current - cool_since >= 15:
                        state["status"] = (
                            "READY" if model_loaded.is_set() else "STARTING"
                        )
                        if model_loaded.is_set():
                            ready.set()
                if current - last_heartbeat >= 2:
                    heartbeat()
                    last_heartbeat = current
                stop.wait(0.2)
            except Exception:  # noqa: BLE001 -- fail closed on any sensor/control failure
                ready.clear()
                state["status"] = "THERMAL_CONTROL_NOT_VERIFIED"
                stop.set()
                try:
                    heartbeat()
                except OSError:
                    pass  # Output failure must also stop scoring.

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    # Prove a sensor reading before importing/loading inference dependencies.
    try:
        temp = max(v["celsius"] for v in thermal.cpu_sensors().values())
        memory = psutil.virtual_memory()
        state["cpu_temperature_c"] = temp
        state["system_used_bytes"] = memory.total - memory.available
        status = startup_status(temp, memory.available)
        if status != "READY":
            print(json.dumps({"startup": status, "cpu_temperature_c": temp,
                              "available_gib": round(memory.available / 1024**3, 2),
                              "required_available_gib": 4}), flush=True)
            heartbeat(status)
            return 3
    except Exception:  # noqa: BLE001 -- sensor validation is a fail-closed boundary
        heartbeat("THERMAL_CONTROL_NOT_VERIFIED")
        return 3
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    try:
        if (
            hashlib.sha256((args.bundle / "manifest.json").read_bytes()).hexdigest()
            != MANIFEST_SHA
        ):
            raise ValueError("untrusted model manifest")
        predictor = module(
            args.bundle / "infer.py", "frozen_request_infer"
        ).RequestPredictor(args.bundle)
        if (
            predictor.manifest["model_version"] != MODEL
            or predictor.threshold != THRESHOLD
        ):
            raise ValueError("unexpected model")
    except Exception:  # noqa: BLE001 -- model failure cannot affect request serving
        heartbeat("MODEL_UNAVAILABLE")
        stop.set()
        monitor_thread.join(timeout=2)
        return 2
    args.socket.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if args.socket.exists():
        if not stat.S_ISSOCK(args.socket.lstat().st_mode):
            raise RuntimeError("Refusing to replace non-socket path")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as probe:
            try:
                probe.connect(str(args.socket))
            except ConnectionRefusedError:
                args.socket.unlink()
            else:
                raise RuntimeError("Another receiver already owns socket")
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 128 * 1024)
    receiver.bind(str(args.socket))
    args.socket.chmod(int(getattr(args, "socket_mode", "600"), 8))
    receiver.settimeout(0.2)

    def receive():
        while not stop.is_set():
            try:
                raw, _, flags, _ = receiver.recvmsg(8193)
                if flags & socket.MSG_TRUNC or len(raw) > 8192:
                    counters["rejected"] += 1
                    continue
                try:
                    inbox.put_nowait(raw)
                except queue.Full:
                    counters["queue_dropped"] += 1
            except TimeoutError:
                pass
            except OSError:
                stop.set()

    consumer = threading.Thread(target=receive, daemon=True)
    consumer.start()
    model_loaded.set()
    if state["status"] == "STARTING":
        state["status"] = "READY"
        ready.set()
    heartbeat()
    try:
        while not stop.is_set():
            if not ready.wait(0.2):
                continue
            try:
                raw = inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                value = read_message(raw)
            except (ValueError, TypeError, KeyError):
                counters["rejected"] += 1
                continue
            rid = value["request_id"]
            started = time.perf_counter()
            try:
                result = predictor.predict(model_record(value))
                if stop.is_set():
                    break
                elapsed = (time.perf_counter() - started) * 1000
                feature = {
                    "uri_observed": True,
                    "headers_observed": True,
                    "headers_complete": False,
                    "body_observed": False,
                    "numeric_dropped_query_fields": result["feature_availability"][
                        "numeric_dropped_query_fields"
                    ],
                }
                journal.append(
                    record(
                        "inference", "SCORED", rid, result["score"], elapsed, feature
                    )
                )
                counters["processed"] += 1
            except Exception:  # noqa: BLE001 -- redact all model/input exception details
                counters["inference_errors"] += 1
                journal.append(record("inference", "INFERENCE_ERROR", rid))
            finally:
                # No raw HTTP value escapes to logs, disk, exceptions or reports.
                del raw, value
    finally:
        stop.set()
        consumer.join(timeout=2)
        receiver.close()
        args.socket.unlink(missing_ok=True)
        monitor_thread.join(timeout=2)
        heartbeat(
            state["status"]
            if state["status"]
            in {"THERMAL_STOP", "RAM_STOP", "THERMAL_CONTROL_NOT_VERIFIED"}
            else "STOPPED"
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--socket-mode", choices=["600", "620"], default="600",
                        help="620 allows write-only access to the service primary group")
    try:
        raise SystemExit(serve(parser.parse_args()))
    except (OSError, RuntimeError, ValueError):
        print("AI shadow stopped safely; raw content suppressed", flush=True)
        raise SystemExit(2)

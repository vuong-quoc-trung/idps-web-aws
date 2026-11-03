"""Bounded AI-owned live sensor and post-response shadow probe.

This is a diagnostic for an isolated disposable lab, not an edge deployment.
It never sends a blocking decision or writes a label.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import psutil
import yaml

from idps_ai.common import REPO_ROOT, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import collect, iter_rows
from idps_ai.data.lab_capture import LabClient
from idps_ai.data.lab_runtime import start_lab, stop_lab, verify_lab_cleanup
from idps_ai.data.privacy import pseudonym
from idps_ai.data.query_numeric import project_query
from idps_ai.data.readers import Input, eve_request_id
from idps_ai.data.sensor_decode import _EveHandler, _EveServer
from idps_ai.data.sensor_lab import _Relay, _RelayHandler
from idps_ai.inference import InferencePipeline


class _ReceiptLog:
    def __init__(self, path, source, initial_offset=0):
        self.path, self.source, self.offset = path, source, initial_offset
        self.receipts = {}
        self.counts = Counter()
        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._follow, daemon=True)
        self.thread.start()

    def _follow(self):
        try:
            while self.running:
                if self.path.exists():
                    with self.path.open("rb") as stream:
                        stream.seek(self.offset)
                        while line := stream.readline(65537):
                            if len(line) > 65536 or not line.endswith(b"\n"):
                                break
                            self.offset = stream.tell()
                            value = json.loads(line)
                            rid = (
                                eve_request_id(value.get("http") or {})
                                if self.source == "suricata"
                                else value.get("request_id")
                            )
                            if self.source != "suricata" or value.get("event_type") == "http":
                                if rid:
                                    self.receipts.setdefault(rid, []).append(time.time())
                            self.counts[value.get("event_type", "http")] += 1
                time.sleep(0.01)
        except (OSError, ValueError, TypeError) as exc:
            self.error = type(exc).__name__

    def close(self):
        self.running = False
        self.thread.join(timeout=2)


def _sensor_config(root, runtime):
    original = REPO_ROOT / "security-web/config/suricata/suricata.yaml"
    rules = REPO_ROOT / "security-web/suricata/pbl4.rules"
    config = yaml.safe_load(original.read_text())
    config["vars"]["address-groups"]["HOME_NET"] = "[127.0.0.0/8]"
    config["vars"]["port-groups"]["HTTP_PORTS"] = "18881"
    config["default-rule-path"] = str(rules.parent)
    config["rule-files"] = [str(rules)]
    config["classification-file"] = str(runtime / "etc/suricata/classification.config")
    config["reference-config-file"] = str(runtime / "etc/suricata/reference.config")
    config["threshold-file"] = str(runtime / "etc/suricata/threshold.config")
    config["unix-command"] = {"enabled": False}
    config.setdefault("detect", {})["sgh-mpm-caching"] = False
    config.setdefault("flow-timeouts", {}).setdefault("tcp", {})["closed"] = 60
    # The repository profile targets a VM interface. A default AF_PACKET lo
    # ring dropped packets in the first live probe, so configure the isolated
    # loopback sensor explicitly with a bounded mmap ring.
    config["af-packet"] = [
        {
            "interface": "lo",
            "threads": 1,
            "cluster-id": 99,
            "cluster-type": "cluster_flow",
            "defrag": True,
            "use-mmap": True,
            "tpacket-v3": True,
            "ring-size": 4096,
        }
    ]
    config["outputs"] = [
        {
            "eve-log": {
                "enabled": True,
                "filetype": "unix_stream",
                "filename": str(root / "eve.sock"),
                "types": [
                    {
                        "alert": {
                            "payload": False,
                            "packet": False,
                            "http-body": False,
                            "http-body-printable": False,
                        }
                    },
                    {"http": {"extended": True, "dump-all-headers": "response"}},
                    "flow",
                    {"stats": {"totals": True, "threads": False}},
                ],
            }
        }
    ]
    config["default-log-dir"] = str(root)
    target = root / "live-suricata.yaml"
    target.write_text("%YAML 1.1\n---\n" + yaml.safe_dump(config, sort_keys=False))
    target.chmod(0o600)
    return target


def _snapshot_score(root, rid, key, pipeline, sequence, target):
    snap = root / f"snapshot-{sequence:02d}"
    snap.mkdir(mode=0o700)
    lab = root / "lab"
    for source, name in (
        ("student", "student-audit.log"),
        ("nginx", "access.log"),
        ("suricata", "eve.json"),
    ):
        shutil.copyfile((lab if source != "suricata" else root) / name, snap / name)
        (snap / name).chmod(0o600)
    inputs = [
        Input(source, snap / name)
        for source, name in (
            ("student", "student-audit.log"),
            ("nginx", "access.log"),
            ("suricata", "eve.json"),
        )
    ]
    collect(inputs, snap / "fused", key, input_profile="safe_query_numeric_v2")
    request_key = pseudonym(key, "request", rid)
    rows = [
        row
        for row in iter_rows(snap / "fused/requests.parquet")
        if row["request_key"] == request_key
    ]
    if len(rows) != 1:
        raise PipelineError("Live request did not fuse uniquely")
    row = rows[0]
    expected_numbers = project_query(target, version=2)["numbers"]
    actual_numbers = json.loads(row["numeric_json"])
    if any(actual_numbers.get(name) != float(value) for name, value in expected_numbers.items()):
        raise PipelineError("Live EVE numeric projection differs from sent safe target")
    start = time.perf_counter_ns()
    result = pipeline.observe(row, include_features=True)
    model_ms = (time.perf_counter_ns() - start) / 1e6
    return row, result, model_ms


def _worker(root, runtime, bundle, flow_wait, query_probe):
    import numpy as np

    def stop(_signum, _frame):
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
    config_path = _sensor_config(root, runtime)
    eve_file = (root / "eve.json").open("x")
    (root / "eve.json").chmod(0o600)
    eve_server = _EveServer(str(root / "eve.sock"), _EveHandler)
    (root / "eve.sock").chmod(0o600)
    eve_server.destination = eve_file
    eve_server.query_numeric = True
    eve_server.query_version = 2
    eve_server.request_structure = False
    eve_server.completed = threading.Event()
    eve_server.failed = False
    sensor_thread = threading.Thread(target=eve_server.serve_forever, daemon=True)
    sensor_thread.start()
    # _EveHandler writes one redacted JSON line per EVE event. Line buffering
    # makes receipt observable before sensor shutdown.
    eve_file.reconfigure(line_buffering=True)
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / "usr/lib/x86_64-linux-gnu"))
    sensor_log = (root / "live-suricata.log").open("wb")
    sensor = subprocess.Popen(
        [
            str(runtime / "usr/bin/suricata"),
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
    monitor_stop = threading.Event()
    monitor_thread = None
    key = (root / "pseudonym-key.bin").read_bytes()
    try:
        time.sleep(3)
        if sensor.poll() is not None or nginx.poll() is not None or eve_server.failed:
            raise PipelineError("Live sensor or Nginx failed startup; inspect private logs")
        trackers = [
            _ReceiptLog(
                lab / "student-audit.log", "student", (lab / "student-audit.log").stat().st_size
            ),
            _ReceiptLog(lab / "access.log", "nginx", (lab / "access.log").stat().st_size),
            _ReceiptLog(root / "eve.json", "suricata"),
        ]
        client = LabClient(18881, "127.0.0.250")
        pipeline = InferencePipeline(bundle, 2)
        monitored = [
            psutil.Process(pid)
            for pid in (os.getpid(), nginx.pid, sensor.pid, marker["processes"]["student"]["pid"])
        ]
        resource = {
            "peak_sampled_rss_bytes": 0,
            "cpu_seconds_start": sum(p.cpu_times().user + p.cpu_times().system for p in monitored),
        }

        def monitor():
            while not monitor_stop.is_set():
                try:
                    resource["peak_sampled_rss_bytes"] = max(
                        resource["peak_sampled_rss_bytes"],
                        sum(p.memory_info().rss for p in monitored),
                    )
                except psutil.Error:
                    pass
                monitor_stop.wait(0.05)

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        started = time.monotonic()
        observations = []
        paths = (
            (
                "/api/auth/csrf?size=2",
                "/api/faculties?size=2",
                "/api/auth/csrf?sort=asc",
                "/api/faculties?sort=asc",
            )
            if query_probe
            else ("/api/auth/csrf", "/api/faculties", "/api/auth/csrf", "/api/faculties")
        )
        for index, path in enumerate(paths):
            if index == 2 and flow_wait:
                time.sleep(flow_wait)  # causal flow watermark is flow.end + 65s
            sent = time.time()
            response, _ = client.request("GET", path)
            rid = response["request_id"]
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if all(rid in item.receipts for item in trackers):
                    break
                if sensor.poll() is not None or eve_server.failed:
                    break
                time.sleep(0.01)
            available = {t.source: t.receipts.get(rid, []) for t in trackers}
            record = {
                "source_count": sum(bool(v) for v in available.values()),
                "duplicate_source_observations": {k: len(v) for k, v in available.items()},
                "http_status": response["status_code"],
                "log_delay_ms": {k: (v[0] - sent) * 1000 for k, v in available.items() if v},
                "inference": False,
                "skip_reason": None,
            }
            if record["source_count"] == 3 and all(len(v) == 1 for v in available.values()):
                try:
                    row, result, model_ms = _snapshot_score(root, rid, key, pipeline, index, path)
                    record.update(
                        inference=True,
                        model_ms=model_ms,
                        end_to_end_ms=(time.time() - sent) * 1000,
                        sources=row["sources"],
                        correlation=row["correlation"],
                        prior_flow_available=json.loads(row["flow_json"]).get("duration_seconds")
                        is not None,
                        finite_features=int(np.isfinite(result["feature_vector"]).sum()),
                        finite_score=bool(np.isfinite(result["score"])),
                        numeric_v2_live_parity=True,
                    )
                except PipelineError as exc:
                    record["skip_reason"] = str(exc)
            else:
                record["skip_reason"] = "missing_or_duplicate_source"
            observations.append(record)
        if any(t.error for t in trackers) or eve_server.failed:
            raise PipelineError("Live log tracker or redaction stream failed")
        monitor_stop.set()
        monitor_thread.join(timeout=2)
        elapsed = time.monotonic() - started
        cpu_seconds = sum(p.cpu_times().user + p.cpu_times().system for p in monitored)
        values = [x["end_to_end_ms"] for x in observations if x["inference"]]
        report = {
            "mode": "isolated_live_post_response_shadow",
            "requests_sent": len(observations),
            "three_source": sum(x["source_count"] == 3 for x in observations),
            "inferred": len(values),
            "skipped": len(observations) - len(values),
            "skip_reasons": dict(
                Counter(x["skip_reason"] for x in observations if x["skip_reason"])
            ),
            "eve_event_counts": dict(trackers[2].counts),
            "per_request": observations,
            "end_to_end_ms": {
                k: float(v)
                for k, v in zip(("p50", "p95", "p99"), np.percentile(values, (50, 95, 99)))
            }
            if values
            else None,
            "post_response_only": True,
            "enforcement_actions": 0,
            "sensor_mode": "Suricata -i lo live pcap in private network namespace",
            "feature_parity_scope": "Python collector + Python inference; Rust/production not measured",
            "sensor_config_sha256": file_sha256(config_path),
            "bundle_manifest_sha256": file_sha256(bundle / "model_manifest.json"),
            "resource": {
                "sampled_processes": ["AI worker", "Nginx", "Suricata", "Student JVM"],
                "peak_sampled_rss_bytes": resource["peak_sampled_rss_bytes"],
                "average_cpu_cores_over_probe": (cpu_seconds - resource["cpu_seconds_start"])
                / elapsed,
                "process_affinity": sorted(os.sched_getaffinity(0)),
                "postgres_container_memory_cap_bytes": 512 * 1024 * 1024,
                "postgres_rss_not_in_sample": True,
            },
            "probe_elapsed_seconds": elapsed,
            "inferred_requests_per_second_over_probe": len(values) / elapsed,
            "flow_wait_seconds": flow_wait,
            "query_probe": query_probe,
        }
        atomic_json(root / "live-report.json", report)
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "requests_sent",
                        "three_source",
                        "inferred",
                        "skipped",
                        "end_to_end_ms",
                    )
                }
            )
        )
    finally:
        monitor_stop.set()
        if monitor_thread:
            monitor_thread.join(timeout=2)
        for item in trackers:
            item.close()
        sensor.send_signal(signal.SIGINT)
        sensor.wait(timeout=15)
        nginx.send_signal(signal.SIGQUIT)
        nginx.wait(timeout=15)
        eve_server.shutdown()
        eve_server.server_close()
        (root / "eve.sock").unlink(missing_ok=True)
        eve_file.close()
        sensor_log.close()
        nginx_log.close()


def _run(root, runtime, bundle, nginx_bin, flow_wait, query_probe):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    (root / "pseudonym-key.bin").write_bytes(os.urandom(32))
    (root / "pseudonym-key.bin").chmod(0o600)
    start_lab(root / "lab", nginx_bin, campaigns=15, input_profile="safe_query_numeric_v2")
    lab = root / "lab"
    relay = None
    try:
        marker = load_json(lab / "owned-lab.json")
        process = psutil.Process(marker["processes"]["nginx"]["pid"])
        if process.create_time() != marker["processes"]["nginx"]["create_time"]:
            raise PipelineError("Owned Nginx identity changed")
        process.send_signal(signal.SIGQUIT)
        process.wait(timeout=15)
        marker["processes"].pop("nginx")
        atomic_json(lab / "owned-lab.json", marker)
        relay = _Relay(str(lab / "student.sock"), _RelayHandler)
        (lab / "student.sock").chmod(0o600)
        relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
        relay_thread.start()
        with (root / "worker.log").open("wb") as log:
            worker = subprocess.Popen(
                [
                    "unshare",
                    "-Urn",
                    sys.executable,
                    __file__,
                    "worker",
                    str(root),
                    str(runtime),
                    str(bundle),
                    "--flow-wait",
                    str(flow_wait),
                    *(["--query-probe"] if query_probe else []),
                ],
                stdout=log,
                stderr=log,
            )
            marker["processes"]["sensor_namespace"] = {
                "pid": worker.pid,
                "create_time": psutil.Process(worker.pid).create_time(),
            }
            atomic_json(lab / "owned-lab.json", marker)
            try:
                code = worker.wait(timeout=180)
            except subprocess.TimeoutExpired:
                worker.send_signal(signal.SIGINT)
                try:
                    worker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    worker.terminate()
                    worker.wait(timeout=15)
                raise PipelineError("Live worker timed out") from None
        if code:
            raise PipelineError("Live worker failed; inspect private worker/sensor logs")
    finally:
        if relay:
            relay.shutdown()
            relay.server_close()
            (lab / "student.sock").unlink(missing_ok=True)
        stop_lab(lab)
        verify_lab_cleanup(lab)
    report = load_json(root / "live-report.json")
    sensor_log = (root / "live-suricata.log").read_text(errors="replace")
    counters = re.findall(r"device: lo: packets: (\d+), drops: (\d+)", sensor_log)
    if not counters:
        raise PipelineError("Live sensor packet/drop counters unavailable")
    packets, drops = map(int, counters[-1])
    report["sensor_packets"] = packets
    report["sensor_drops"] = drops
    report["sensor_drop_free"] = drops == 0
    report["eve_counts_after_sensor_stop"] = dict(
        Counter(json.loads(line)["event_type"] for line in (root / "eve.json").open())
    )
    report["runner_cpu_affinity"] = sorted(os.sched_getaffinity(0))
    atomic_json(root / "live-report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "worker"))
    parser.add_argument("root", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--nginx-bin", type=Path)
    parser.add_argument("--flow-wait", type=int, choices=(0, 67), default=67)
    parser.add_argument("--query-probe", action="store_true")
    args = parser.parse_args()
    if args.mode == "worker":
        _worker(
            args.root.resolve(),
            args.runtime.resolve(),
            args.bundle.resolve(),
            args.flow_wait,
            args.query_probe,
        )
    else:
        if not args.nginx_bin:
            parser.error("--nginx-bin is required")
        _run(
            args.root.resolve(),
            args.runtime.resolve(),
            args.bundle.resolve(),
            args.nginx_bin.resolve(),
            args.flow_wait,
            args.query_probe,
        )

#!/usr/bin/env python3
"""Opt-in passive IDS gateway in a private user/network namespace.

Run under integration-guard.py. No host packet socket, PCAP, blocking or rules edit.
"""

import argparse
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
import select
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from idps_ai.data.sensor_decode import redact_eve
from three_source_core import Correlator, identity, response_id

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "shadow", ROOT / "scripts/ai-shadow-worker.py"
)
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)


class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 64


class TCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


def gateway_network(listen, allowed):
    address = ipaddress.IPv4Address(listen)
    network = ipaddress.IPv4Network(allowed, strict=True)
    private = [
        ipaddress.ip_network(v)
        for v in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
    ]
    if (
        address.is_unspecified
        or not any(network.subnet_of(v) for v in private)
        or address not in network
    ):
        raise ValueError(
            "Bind a specific private/loopback IPv4 inside the allowed lab subnet"
        )
    return network


class LabGateway(TCPServer):
    """Only authorized subnet peers; no HTTP header is trusted as a client IP."""

    def verify_request(self, request, address):
        allowed = ipaddress.IPv4Address(address[0]) in self.allowed_network
        if allowed:
            self.peer_journal.append(
                {
                    "observed_at": datetime.now(UTC).isoformat(),
                    "tcp_peer_ip": address[0],
                    "tcp_peer_port": address[1],
                    "identity_scope": "SOCKET_PEER_ONLY_NOT_REQUEST_CORRELATION",
                    "forwarded_client_attribution": "UNAVAILABLE_RELAY; BLOCK_PROHIBITED",
                }
            )
        return allowed


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        target = self.server.target
        upstream = socket.socket(
            socket.AF_UNIX if isinstance(target, str) else socket.AF_INET,
            socket.SOCK_STREAM,
        )
        try:
            upstream.settimeout(15)
            upstream.connect(target)
            peers = (self.request, upstream)
            while True:
                ready, _, _ = select.select(peers, [], [], 30)
                if not ready:
                    return
                for src in ready:
                    data = src.recv(65536)
                    if not data:
                        return
                    peers[1 if src is peers[0] else 0].sendall(data)
        except (OSError, TimeoutError):
            pass  # No raw request/error echo.
        finally:
            upstream.close()


def background(server, target=None):
    server.target = target
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def sensor_config(out, runtime):
    config = yaml.safe_load(
        (ROOT / "security-web/config/suricata/suricata.yaml").read_text()
    )
    config["vars"]["address-groups"]["HOME_NET"] = "[127.0.0.0/8]"
    config["vars"]["port-groups"]["HTTP_PORTS"] = "18881"
    rules = ROOT / "security-web/suricata/pbl4.rules"
    config["default-rule-path"] = str(rules.parent)
    config["rule-files"] = [str(rules)]
    for name in ["classification", "reference"]:
        config[
            name + "-file" if name == "classification" else "reference-config-file"
        ] = str(runtime / "etc/suricata" / (name + ".config"))
    config["unix-command"] = {"enabled": False}
    config["detect"]["sgh-mpm-caching"] = False
    config["af-packet"] = [
        {
            "interface": "lo",
            "threads": 1,
            "use-mmap": True,
            "tpacket-v3": True,
            "ring-size": 4096,
            "cluster-id": 97,
            "cluster-type": "cluster_flow",
        }
    ]
    config["outputs"] = [
        {
            "eve-log": {
                "enabled": True,
                "filetype": "unix_stream",
                "filename": str(out / "eve.sock"),
                "types": [
                    {"http": {"extended": True, "dump-all-headers": "response"}},
                    {
                        "alert": {
                            "payload": False,
                            "packet": False,
                            "http-body": False,
                            "http-body-printable": False,
                        }
                    },
                    "flow",
                    {"stats": {"totals": True, "threads": False}},
                ],
            }
        }
    ]
    config["default-log-dir"] = str(out)
    path = out / "suricata.yaml"
    path.write_text("%YAML 1.1\n---\n" + yaml.safe_dump(config, sort_keys=False))
    return path


def wait_engine(sensor, log_path, offset, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sensor.poll() is not None:
            raise RuntimeError(f"Suricata exited rc={sensor.returncode} before capture readiness; inspect {log_path}")
        with log_path.open("rb") as stream:
            stream.seek(offset)
            if b"Engine started." in stream.read():
                return
        time.sleep(.1)
    raise RuntimeError(f"Suricata engine readiness timed out; inspect {log_path}")


def namespace(args):
    out = args.output
    runtime = args.sensor_runtime
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    upstream = background(
        TCPServer(("127.0.0.1", 18881), Relay), str(out / "to-host.sock")
    )
    edge = background(UnixServer(str(out / "to-net.sock"), Relay), ("127.0.0.1", 18881))
    config = sensor_config(out, runtime)
    environment = os.environ | {
        "LD_LIBRARY_PATH": str(runtime / "usr/lib/x86_64-linux-gnu")
    }
    command = [
        str(runtime / "usr/bin/suricata"),
        "-c",
        str(config),
        "--runmode",
        "single",
        "-k",
        "none",
        "-i",
        "lo",
        "-l",
        str(out),
        "--set",
        "detect.profile=low",
        "tcp port 18881",
    ]
    children = []

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        with (out / "sensor.log").open("ab") as log:
            test = subprocess.run(
                [
                    command[0],
                    "-T",
                    "-c",
                    str(config),
                    "--runmode",
                    "single",
                    "--set",
                    "detect.profile=low",
                ],
                env=environment,
                stdout=log,
                stderr=log,
                timeout=120,
                check=False,
            )
            if test.returncode:
                raise RuntimeError("Suricata config/rule validation failed")
            offset = (out / "sensor.log").stat().st_size
            sensor = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
            children.append(sensor)
            wait_engine(sensor, out / "sensor.log", offset)
            (out / "sensor-ready.json").write_text(json.dumps({"pid":sensor.pid, "ready_at":time.time(), "basis":"CURRENT_ENGINE_STARTED_LOG"}))
            (out / "sensor-pid.json").write_text(
                json.dumps(
                    {
                        "pid": sensor.pid,
                        "namespace": os.readlink("/proc/self/ns/net"),
                        "host_namespace": args.host_namespace,
                    }
                )
            )
            while True:
                if (out / "STOP_SENSOR").exists() and sensor.poll() is None:
                    (out / "sensor-ready.json").unlink(missing_ok=True)
                    sensor.send_signal(signal.SIGINT)
                    sensor.wait(timeout=15)
                    (out / "STOP_SENSOR").unlink()
                if (out / "START_SENSOR").exists():
                    if sensor.poll() is not None:
                        offset = (out / "sensor.log").stat().st_size
                        sensor = subprocess.Popen(
                            command, env=environment, stdout=log, stderr=log
                        )
                        children.append(sensor)
                        wait_engine(sensor, out / "sensor.log", offset)
                        (out / "sensor-ready.json").write_text(json.dumps({"pid":sensor.pid, "ready_at":time.time(), "basis":"CURRENT_ENGINE_STARTED_LOG"}))
                    (out / "START_SENSOR").unlink()
                if sensor.poll() is not None and not (out / "sensor-stopped").exists():
                    (out / "sensor-stopped").touch()
                if sensor.poll() is None:
                    (out / "sensor-stopped").unlink(missing_ok=True)
                time.sleep(0.2)
    finally:
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        upstream.shutdown()
        edge.shutdown()


def host(args):
    allowed_network = gateway_network(args.listen, args.allow_cidr)
    out = args.output
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.umask(0o077)
    args.host_namespace = os.readlink("/proc/self/ns/net")
    sensor_id = uuid.uuid4().hex
    route_key = os.urandom(32)
    (out / "route-key.bin").write_bytes(route_key)
    corr = Correlator(sensor_id, route_key)
    eve_journal = shadow.Journal(args.runtime / "suricata/eve.json")
    events = shadow.Journal(out / "eve.json")
    metadata = shadow.Journal(args.runtime / "correlation/results.jsonl")
    counts = Counter()
    seen_eve = set()
    lock = threading.Lock()

    class Eve(socketserver.StreamRequestHandler):
        def handle(self):
            generation = uuid.uuid4().hex
            while line := self.rfile.readline(65537):
                try:
                    if len(line) > 65536 or not line.endswith(b"\n"):
                        raise ValueError
                    raw = json.loads(line)
                    safe = redact_eve(raw, query_numeric=True, query_version=2)
                    if isinstance(raw.get("tx_id"), int):
                        safe["tx_id"] = raw["tx_id"]
                    safe["sensor_instance"] = generation
                    if raw.get("event_type") == "http" and isinstance(
                        raw.get("http", {}).get("url"), str
                    ):
                        safe["http"]["path_fingerprint"] = hmac.new(
                            route_key,
                            urlsplit(raw["http"]["url"]).path.encode(),
                            hashlib.sha256,
                        ).hexdigest()
                    rid = response_id(safe)
                    if rid:
                        safe["http"]["request_id"] = rid
                    with lock:
                        corr.add("SURICATA", safe, time.time())
                        event_id = identity(safe)
                        if event_id not in seen_eve:
                            if len(seen_eve) >= 16384:
                                raise RuntimeError("Bounded EVE event limit reached")
                            seen_eve.add(event_id)
                            counts[safe["event_type"]] += 1
                            safe["adapter_version"] = "suricata-shadow-1"
                            safe["sensor_event_id"] = event_id
                            safe["received_at"] = time.time()
                            events.append(safe)
                            eve_journal.append(safe)
                        else:
                            counts["duplicate_eve"] += 1
                except (ValueError, TypeError, KeyError):
                    counts["rejected"] += 1

    receiver = background(UnixServer(str(out / "eve.sock"), Eve))
    relay = background(
        UnixServer(str(out / "to-host.sock"), Relay), ("127.0.0.1", args.edge_port)
    )
    child = subprocess.Popen(
        [
            "unshare",
            "-Urn",
            sys.executable,
            str(Path(__file__).resolve()),
            "namespace",
            "--output",
            str(out),
            "--runtime",
            str(args.runtime),
            "--sensor-runtime",
            str(args.sensor_runtime),
            "--host-namespace",
            args.host_namespace,
        ],
        stdout=subprocess.DEVNULL,
        stderr=(out / "namespace.log").open("ab"),
    )
    gateway = None
    sources = {
        "NGINX": args.runtime / "nginx/access.log",
        "STUDENT_AUDIT": args.runtime / "student-audit/student-audit.log",
    }
    offsets = {s: p.stat().st_size for s, p in sources.items()}
    latest = {}
    started = time.time()

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        deadline = time.monotonic() + 150
        while not (out / "sensor-ready.json").exists():
            if child.poll() is not None:
                raise RuntimeError("Namespace startup failed")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Capture readiness deadline; inspect {out / 'sensor.log'}")
            time.sleep(0.2)
        gateway = LabGateway((args.listen, args.gateway_port), Relay)
        gateway.allowed_network = allowed_network
        gateway.peer_journal = shadow.Journal(out / "gateway-peers.jsonl")
        background(gateway, str(out / "to-net.sock"))
        while True:
            if child.poll() is not None:
                raise RuntimeError("Namespace exited")
            with lock:
                for source, path in sources.items():
                    with path.open("rb") as f:
                        f.seek(offsets[source])
                        while line := f.readline(65537):
                            if not line.endswith(b"\n"):
                                break
                            offsets[source] = f.tell()
                            try:
                                value = json.loads(line)
                                if (
                                    source == "STUDENT_AUDIT"
                                    and value.get("event_type") != "http_request"
                                ):
                                    continue
                                corr.add(source, value, time.time())
                            except (ValueError, TypeError):
                                counts["source_rejected"] += 1
                if len(corr.rows) > 2048:
                    raise RuntimeError(
                        "Bounded demo request limit reached; restart after handoff"
                    )
                for rid in list(corr.rows):
                    result = corr.result(rid)
                    if identity(result) != latest.get(rid):
                        latest[rid] = identity(result)
                        result["observed_at"] = datetime.now(UTC).isoformat()
                        metadata.append(result)
                report = {
                    "status": "LIVE_HTTP_OBSERVED"
                    if counts["http"]
                    else "WAITING_FOR_HTTP",
                    "sensor_instance": sensor_id,
                    "event_counts": dict(counts),
                    "request_statuses": dict(
                        Counter(corr.result(r)["status"] for r in corr.rows)
                    ),
                    "host_namespace": args.host_namespace,
                    "gateway_port": args.gateway_port,
                    "gateway_bind": args.listen,
                    "allowed_client_network": str(allowed_network),
                    "client_attribution": "SOCKET_PEER_RECORDED_SEPARATELY; NGINX_SEES_PROTECTED_RELAY",
                    "enforcement_actions": 0,
                    "started_at": started,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "GLU207": "SEPARATE_WORKER_NOT_A_LIVENESS_CHECK",
                    "scope": "Only opt-in gateway; no host capture; tuple changes across Unix relays; response-ID transaction correlation",
                }
                (out / "status.json").write_text(json.dumps(report, indent=2) + "\n")
            time.sleep(0.2)
    finally:
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        for server in [gateway, relay, receiver]:
            if server:
                server.shutdown()
                server.server_close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["host", "namespace"])
    p.add_argument("--runtime", type=Path, default=ROOT / ".local-dev/foundation")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--sensor-runtime",
        type=Path,
        default=Path(
            os.environ.get("SURICATA_RUNTIME_DIR", ROOT / ".local-dev/suricata-runtime")
        ),
    )
    p.add_argument("--edge-port", type=int, default=18780)
    p.add_argument("--gateway-port", type=int, default=18782)
    p.add_argument("--listen", default="127.0.0.1")
    p.add_argument("--allow-cidr", default="127.0.0.0/8")
    p.add_argument("--host-namespace")
    a = p.parse_args()
    a.output = a.output.resolve()
    a.runtime = a.runtime.resolve()
    a.sensor_runtime = a.sensor_runtime.resolve()
    if a.mode == "host":
        host(a)
    else:
        namespace(a)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

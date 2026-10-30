"""Rootless private-network capture. Never opens a packet socket in the host netns."""

import argparse
import http.server
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json


def _capture(directory):
    log = (directory / "tcpdump.log").open("wb")
    process = subprocess.Popen(
        [
            "tcpdump",
            "--immediate-mode",
            "-Z",
            "root",
            "-i",
            "lo",
            "-s",
            "0",
            "-U",
            "-w",
            str(directory / "traffic.pcap"),
            "tcp port 18881",
        ],
        stdout=log,
        stderr=log,
        umask=0o077,
    )
    for _ in range(100):
        if process.poll() is not None:
            log.close()
            raise PipelineError("Private namespace packet capture failed; inspect tcpdump.log")
        if "listening on lo" in (directory / "tcpdump.log").read_text(errors="replace"):
            (directory / "traffic.pcap").chmod(0o600)
            return process, log
        time.sleep(0.02)
    process.terminate()
    raise PipelineError("Private capture startup timed out")


def _finish_capture(process, log):
    process.send_signal(signal.SIGINT)
    code = process.wait(timeout=15)
    log.close()
    if code:
        raise PipelineError("Packet capture exited unsuccessfully")
    return code


def _probe_worker(directory):
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("X-Request-Id", "probe-edge-id")
            self.send_header("Set-Cookie", "SENSOR_SECRET_CANARY")
            self.end_headers()
            self.wfile.write(b"owned lab probe")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 18881), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    capture, log = _capture(directory)
    try:
        from http.client import HTTPConnection

        connection = HTTPConnection("127.0.0.1", 18881)
        connection.request("GET", "/probe")
        response = connection.getresponse()
        status = response.status
        response.read()
        connection.close()
        time.sleep(0.1)
    finally:
        code = _finish_capture(capture, log)
        server.shutdown()
        server.server_close()
    atomic_json(
        directory / "probe.json",
        {
            "http_status": status,
            "pcap_bytes": (directory / "traffic.pcap").stat().st_size,
            "network_namespace": os.readlink("/proc/self/ns/net"),
            "packet_capture_returncode": code,
        },
    )


def probe_capture(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    before = os.readlink("/proc/self/ns/net")
    result = subprocess.run(
        ["unshare", "-Urn", sys.executable, "-m", __name__, "probe-worker", str(directory)],
        capture_output=True,
        timeout=20,
    )
    (directory / "probe-worker.stderr.log").write_bytes(result.stderr)
    (directory / "probe-worker.stderr.log").chmod(0o600)
    if result.returncode:
        raise PipelineError(
            "Private user/network namespace unavailable; no host privileges changed"
        )
    value = load_json(directory / "probe.json")
    value["namespace_isolated"] = value["network_namespace"] != before
    value["host_namespace_unchanged"] = os.readlink("/proc/self/ns/net") == before
    atomic_json(directory / "probe.json", value)
    return value


class _Relay(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    # Nginx uses nonblocking Unix connects. The default backlog of five can
    # return EAGAIN/502 when 18 independent campaigns initialize together.
    request_queue_size = 128


class _RelayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        import select

        with socket.create_connection(("127.0.0.1", 18880), timeout=10) as upstream:
            peers = (self.request, upstream)
            while True:
                ready, _, _ = select.select(peers, [], [], 15)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    peers[1 if source is peers[0] else 0].sendall(data)


def _campaign_worker(directory, duration, requests):
    from idps_ai.data.campaigns import run_extended_campaigns

    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)

    def stop(_signum, _frame):
        (directory / "STOP").touch(mode=0o600)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    marker = load_json(directory / "owned-lab.json")
    config = "user root;\n" + (directory / "nginx.conf").read_text()
    config = config.replace("127.0.0.1:18880", "unix:" + str(directory / "student.sock"))
    # Match edge telemetry: only its masked idps_json view is retained.
    config = "\n".join(
        line for line in config.splitlines() if not ("access_log " in line and "idps_lab" in line)
    )
    config += "\n"
    (directory / "sensor-nginx.conf").write_text(config)
    command = [
        marker["nginx_binary"],
        "-p",
        str(directory) + "/",
        "-c",
        str(directory / "sensor-nginx.conf"),
        "-g",
        "daemon off;",
    ]
    with (directory / "sensor-nginx.log").open("wb") as nginx_log:
        nginx = subprocess.Popen(command, stdout=nginx_log, stderr=nginx_log)
        capture, log = _capture(directory)
        try:
            time.sleep(0.3)
            if nginx.poll() is not None:
                raise PipelineError("Private namespace Nginx failed")
            if marker.get("scenario_version") == "request-challenge-1":
                from idps_ai.data.request_campaigns import run_challenge

                run_challenge(directory, count=requests, duration=duration)
            else:
                run_extended_campaigns(directory, count=requests, duration=duration)
        finally:
            nginx.send_signal(signal.SIGQUIT)
            nginx.wait(timeout=20)
            _finish_capture(capture, log)
    atomic_json(
        directory / "pcap-manifest.json",
        {
            "pcap_sha256": file_sha256(directory / "traffic.pcap"),
            "bytes": (directory / "traffic.pcap").stat().st_size,
            "network_namespace": os.readlink("/proc/self/ns/net"),
            "capture_filter": "tcp port 18881",
            "source": "real Linux TCP, no packet synthesis",
            "tcpdump_log_sha256": file_sha256(directory / "tcpdump.log"),
            "nginx_template_sha256": marker["nginx_template_sha256"],
            "query_profile": marker.get("ai_input_profile", "edge_masked_v1"),
        },
    )


def capture_lab(directory, duration=360, requests=960):
    """Requires a lab from start_lab; shuts down only its host Nginx before capture."""
    import psutil

    directory = Path(directory).resolve()
    marker = load_json(directory / "owned-lab.json")
    if marker.get("purpose") != "ai-pretrain-disposable":
        raise PipelineError("Explicitly owned disposable lab required")
    identity = marker["processes"]["nginx"]
    process = psutil.Process(identity["pid"])
    if process.create_time() != identity["create_time"] or str(directory) not in " ".join(
        process.cmdline()
    ):
        raise PipelineError("Owned Nginx process identity mismatch")
    process.send_signal(signal.SIGQUIT)
    try:
        process.wait(timeout=15)
    except psutil.TimeoutExpired:
        if process.status() != psutil.STATUS_ZOMBIE:
            raise PipelineError("Host lab Nginx did not stop") from None
    marker["processes"].pop("nginx")
    marker["sensor_capture"] = "private user/network namespace TCP PCAP; offline Suricata"
    marker["query_view"] = "edge_masked_v1; raw query view excluded"
    atomic_json(directory / "owned-lab.json", marker)
    socket_path = directory / "student.sock"
    relay = _Relay(str(socket_path), _RelayHandler)
    socket_path.chmod(0o600)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    try:
        with (directory / "namespace.log").open("wb") as log:
            worker = subprocess.Popen(
                [
                    "unshare",
                    "-Urn",
                    sys.executable,
                    "-m",
                    __name__,
                    "campaign-worker",
                    str(directory),
                    "--duration",
                    str(duration),
                    "--requests",
                    str(requests),
                ],
                stdout=log,
                stderr=log,
            )
            marker["processes"]["sensor_namespace"] = {
                "pid": worker.pid,
                "create_time": psutil.Process(worker.pid).create_time(),
            }
            atomic_json(directory / "owned-lab.json", marker)
            try:
                while True:
                    try:
                        code = worker.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        capture_file = directory / "traffic.pcap"
                        if capture_file.exists() and capture_file.stat().st_size > 512 * 1024**2:
                            raise PipelineError(
                                "Private PCAP exceeded 512MiB; stop without certifying data"
                            )
            except BaseException:
                (directory / "STOP").touch(mode=0o600)
                worker.terminate()
                worker.wait(timeout=30)
                raise
        if code:
            raise PipelineError(
                "Private capture failed; inspect namespace.log, no dataset certified"
            )
    finally:
        relay.shutdown()
        relay.server_close()
        socket_path.unlink(missing_ok=True)
    return load_json(directory / "pcap-manifest.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["probe-worker", "campaign-worker"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--duration", type=float, default=360)
    parser.add_argument("--requests", type=int, default=960)
    arguments = parser.parse_args()
    if arguments.action == "probe-worker":
        _probe_worker(arguments.directory)
    else:
        _campaign_worker(arguments.directory, arguments.duration, arguments.requests)

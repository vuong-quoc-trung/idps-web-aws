"""Isolated loopback HTTP proof, not a production reverse proxy or inference worker.

Transient buffers only. HTTP bodies/headers/paths never go to telemetry or logs.
The candidate worker accepts a separate fixed numeric contract, not frozen AI.
"""

import http.client
import json
import os
import socket
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from idps_ai.features import body_syntax_v1 as syntax


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def handle_error(self, request, client_address):
        # Never print request-bearing exception text or traceback locals.
        self.errors = getattr(self, "errors", 0) + 1


def chunks(reader):
    """Forward exact chunk framing. Syntax unsupported; bounded transient blocks."""
    total = 0
    while True:
        line = reader.readline(1025)
        if not line.endswith(b"\r\n") or len(line) > 1024:
            raise ValueError("Chunk framing rejected")
        size = int(line.split(b";", 1)[0], 16)
        if size < 0 or total + size > 1024 * 1024:
            raise ValueError("Chunk transport budget exceeded")
        yield line
        if not size:
            trailer_bytes = 0
            while True:
                line = reader.readline(1025)
                trailer_bytes += len(line)
                if not line.endswith(b"\r\n") or trailer_bytes > 8192:
                    raise ValueError("Trailer transport budget exceeded")
                yield line
                if line == b"\r\n":
                    return
        remaining = size + 2
        while remaining:
            block = reader.read(min(4096, remaining))
            if not block:
                raise ValueError("Incomplete chunk transport")
            remaining -= len(block)
            yield block
        total += size


class SyntaxWorker:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, exist_ok=False)
        # Artifact roots can exceed Linux's Unix-socket path limit. This private
        # temporary directory contains only the socket node, never body bytes.
        self.socket_directory = tempfile.TemporaryDirectory(prefix="idps-body-syntax-")
        self.socket_path = str(Path(self.socket_directory.name) / "syntax.sock")
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.bind(self.socket_path)
        os.chmod(self.socket_path, 0o600)
        self.socket.settimeout(0.1)
        self.stop = threading.Event()
        self.events = {}
        self.rejected = 0
        self.accepted = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _append(self, name, value):
        fd = os.open(
            self.directory / name, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps(value, separators=(",", ":")) + "\n")

    def _run(self):
        while not self.stop.is_set():
            try:
                data = self.socket.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                if len(data) > 4096:
                    raise ValueError("Syntax datagram limit")
                value = json.loads(data)
                syntax.validate_event(value)
            except Exception:
                self.rejected += 1
                if self.rejected <= 64:
                    self._append("worker.log", {"status": "REJECTED_SCHEMA"})
                continue
            if self.accepted >= 512:
                continue
            self._append("candidate.jsonl", value)
            self.accepted += 1
            self.events[value["request_id"]] = value

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.socket.close()
        Path(self.socket_path).unlink(missing_ok=True)
        self.socket_directory.cleanup()


class Ingress:
    """Explicit ephemeral opt-in. Upstream is fixed loopback, no public listener."""

    def __init__(
        self, upstream_port, worker_path, trusted_ids=(), extractor=syntax.extract, enabled=True
    ):
        self.worker_path = str(worker_path)
        self.trusted_ids = set(trusted_ids)
        self.extractor = extractor
        self.enabled = enabled
        self.dropped = self.sent = self.failures = 0
        self.max_prefix = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def handle_one_request(self):
                self.connection.settimeout(5)
                return super().handle_one_request()

            def relay(self):
                upstream = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=5)
                try:
                    upstream.putrequest(
                        self.command, self.path, skip_host=True, skip_accept_encoding=True
                    )
                    for name, value in self.headers.raw_items():
                        upstream.putheader(name, value)
                    upstream.endheaders()
                    transfer = self.headers.get("Transfer-Encoding")
                    content_length = self.headers.get("Content-Length")
                    prefix = bytearray()
                    oversize = False
                    if transfer and transfer.lower().strip() == "chunked":
                        for block in chunks(self.rfile):
                            upstream.send(block)
                        observed = b""
                    elif content_length is not None:
                        length = int(content_length)
                        if not 0 <= length <= 1024 * 1024:
                            raise ValueError("Isolated transport length exceeded")
                        oversize = length > syntax.MAX_BYTES
                        remaining = length
                        while remaining:
                            block = self.rfile.read(min(4096, remaining))
                            if not block:
                                raise ValueError("Incomplete isolated transport")
                            upstream.send(block)
                            remaining -= len(block)
                            if not oversize:
                                prefix.extend(block)
                                owner.max_prefix = max(owner.max_prefix, len(prefix))
                        observed = bytes(prefix)
                    else:
                        observed = None
                    if owner.enabled:
                        try:
                            if oversize:
                                # No over-limit content was buffered or partially interpreted.
                                vector = owner.extractor(
                                    None,
                                    self.headers.get("Content-Type"),
                                    content_encoding=self.headers.get("Content-Encoding"),
                                    transfer_encoding=transfer,
                                    declared_oversize=True,
                                )
                            else:
                                vector = owner.extractor(
                                    observed,
                                    self.headers.get("Content-Type"),
                                    content_encoding=self.headers.get("Content-Encoding"),
                                    transfer_encoding=transfer,
                                )
                            # Lab-owned IDs are predeclared; arbitrary client strings never enter telemetry.
                            incoming = self.headers.get("X-Request-Id")
                            rid = incoming if incoming in owner.trusted_ids else uuid.uuid4().hex
                            payload = json.dumps(
                                syntax.event(rid, vector), separators=(",", ":")
                            ).encode()
                            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sink:
                                sink.setblocking(False)
                                sink.sendto(payload, owner.worker_path)
                            owner.sent += 1
                        except Exception:
                            # Extractor/worker failures never change forwarding decisions.
                            owner.failures += 1
                            owner.dropped += 1
                    del prefix, observed
                    response = upstream.getresponse()
                    self.send_response_only(response.status, response.reason)
                    for name, value in response.getheaders():
                        self.send_header(name, value)
                    self.end_headers()
                    while block := response.read(4096):
                        self.wfile.write(block)
                finally:
                    upstream.close()

            do_GET = relay
            do_POST = relay
            do_PUT = relay
            do_PATCH = relay
            do_DELETE = relay

        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

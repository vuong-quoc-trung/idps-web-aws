"""Opt-in Unix upstream for a dedicated Nginx lab, never the default application path.

Uses the unchanged body-syntax-v1 contract. No request body/header/path is logged.
It is deliberately not installed or enabled by the team bootstrap.
"""

import ctypes
import http.client
import json
import os
import re
import socket
import socketserver
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from idps_ai.common import atomic_json
from idps_ai.features import body_syntax_v1 as syntax
from idps_ai.features.body_syntax_transport import chunks


class Gate:
    def __init__(self, path):
        self.path = Path(path)
        self.enabled = False
        self.latched = False
        self.reason = "DEFAULT_OFF"
        self._save()

    def _save(self):
        atomic_json(
            self.path,
            {
                "BODY_SYNTAX_EXPERIMENT": "ON" if self.enabled else "OFF",
                "latched": self.latched,
                "reason": self.reason,
            },
        )

    def enable(self, *, opt_in=False, privacy_preflight=False):
        if not opt_in or not privacy_preflight or self.latched:
            return False
        self.enabled = True
        self.reason = "EXPLICIT_LAB_OPT_IN_AFTER_PREFLIGHT"
        self._save()
        return True

    def trip(self, reason):
        self.enabled = False
        self.latched = True
        self.reason = reason
        self._save()

    def off(self):
        self.enabled = False
        self.reason = "OPERATOR_OFF" if not self.latched else self.reason
        self._save()


class TempMonitor:
    """Observe create/write/move events, including files deleted before final scan.

    Only counts/category names are kept. No filenames or content are persisted.
    """

    def __init__(self, directories, gate):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise RuntimeError("Filesystem monitor unavailable")
        self.paths = {}
        self.counts = {name: 0 for name in directories}
        self.gate = gate
        self.stop = threading.Event()
        self.healthy = True
        for name, directory in directories.items():
            self._watch(Path(directory), name)
        self.thread = threading.Thread(target=self._guarded, daemon=True)
        self.thread.start()

    def _guarded(self):
        try:
            self._run()
        except Exception:
            self.healthy = False
            self.gate.trip("FILESYSTEM_MONITOR_FAILURE")

    def _watch(self, path, category):
        path.mkdir(parents=True, exist_ok=True)
        wd = self.libc.inotify_add_watch(
            self.fd, os.fsencode(path), 0x100 | 0x2 | 0x8 | 0x80 | 0x4000
        )
        if wd < 0:
            raise RuntimeError("Filesystem watch unavailable")
        self.paths[wd] = (path, category)
        for child in path.iterdir():
            if child.is_dir():
                self._watch(child, category)

    def _run(self):
        while not self.stop.wait(0.01):
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                continue
            except OSError:
                if not self.stop.is_set():
                    self.healthy = False
                    self.gate.trip("FILESYSTEM_MONITOR_LOST")
                return
            offset = 0
            while offset < len(data):
                wd, mask, _, length = struct.unpack_from("iIII", data, offset)
                name = data[offset + 16 : offset + 16 + length].split(b"\0", 1)[0]
                offset += 16 + length
                if mask & 0x4000:
                    self.healthy = False
                    self.gate.trip("FILESYSTEM_MONITOR_OVERFLOW")
                if wd not in self.paths:
                    continue
                path, category = self.paths[wd]
                if mask & 0x40000000:
                    child = path / os.fsdecode(name)
                    if child.exists():
                        self._watch(child, category)
                else:
                    self.counts[category] += 1
                    if category != "SELF_TEST":
                        self.gate.trip("BODY_OR_APPLICATION_TEMP_WRITE")

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        os.close(self.fd)


class UnixHTTP(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        self.errors = getattr(self, "errors", 0) + 1


class LabIngress:
    def __init__(self, path, targets, worker_path, gate, extractor=syntax.extract):
        self.path = Path(path)
        self.gate = gate
        self.extractor = extractor
        self.worker_path = str(worker_path)
        self.observations = {}
        self.sent = self.dropped = self.max_prefix = 0
        self.extraction_ms = []
        self.max_payload_bytes = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def handle_one_request(self):
                self.connection.settimeout(10)
                return super().handle_one_request()

            def relay(self):
                # Socket directory is private0700; no client-facing TCP listener.
                _, uid, _ = struct.unpack(
                    "3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                if uid != os.getuid():
                    raise ValueError("Untrusted ingress peer")
                port = next(
                    (p for prefix, p in targets if self.path.startswith(prefix)), targets[-1][1]
                )
                upstream = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                rid = self.headers.get("X-Request-Id", "")
                try:
                    upstream.putrequest(
                        self.command, self.path, skip_host=True, skip_accept_encoding=True
                    )
                    for key, value in self.headers.raw_items():
                        if key.lower() != "x-body-original-transfer":
                            upstream.putheader(key, value)
                    upstream.endheaders()
                    transfer = self.headers.get("Transfer-Encoding")
                    original_transfer = self.headers.get("X-Body-Original-Transfer") or transfer
                    prefix = bytearray()
                    oversize = False
                    if transfer and transfer.lower() == "chunked":
                        for block in chunks(self.rfile):
                            upstream.send(block)
                        observed = b""
                    elif self.headers.get("Content-Length") is not None:
                        remaining = int(self.headers["Content-Length"])
                        if not 0 <= remaining <= 1024 * 1024:
                            raise ValueError("Lab transport budget exceeded")
                        oversize = remaining > syntax.MAX_BYTES
                        while remaining:
                            block = self.rfile.read(min(4096, remaining))
                            if not block:
                                raise ValueError("Incomplete HTTP transport")
                            remaining -= len(block)
                            upstream.send(block)
                            if not oversize:
                                prefix.extend(block)
                        owner.max_prefix = max(owner.max_prefix, len(prefix))
                        observed = bytes(prefix)
                    else:
                        observed = None
                    if owner.gate.enabled:
                        try:
                            if not re.fullmatch(r"[a-f0-9]{32}", rid):
                                raise ValueError("Missing trusted Nginx identity")
                            started = time.perf_counter()
                            vector = owner.extractor(
                                None if oversize else observed,
                                self.headers.get("Content-Type"),
                                content_encoding=self.headers.get("Content-Encoding"),
                                transfer_encoding=original_transfer,
                                declared_oversize=oversize,
                            )
                            owner.extraction_ms.append((time.perf_counter() - started) * 1000)
                            payload = json.dumps(
                                syntax.event(rid, vector), separators=(",", ":")
                            ).encode()
                            owner.max_payload_bytes = max(owner.max_payload_bytes, len(payload))
                            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as out:
                                out.setblocking(False)
                                out.sendto(payload, owner.worker_path)
                            owner.sent += 1
                        except Exception:
                            owner.dropped += 1
                            owner.gate.trip("EXTRACTOR_OR_TELEMETRY_FAILURE")
                    del prefix, observed
                    response = upstream.getresponse()
                    self.send_response_only(response.status, response.reason)
                    for key, value in response.getheaders():
                        self.send_header(key, value)
                    self.end_headers()
                    # http.client decodes upstream chunk framing; preserve HTTP
                    # response semantics by framing again instead of sending bare bytes.
                    while block := response.read(4096):
                        if response.chunked:
                            self.wfile.write(f"{len(block):x}\r\n".encode() + block + b"\r\n")
                        else:
                            self.wfile.write(block)
                    if response.chunked:
                        self.wfile.write(b"0\r\n\r\n")
                    owner.observations[rid] = {
                        "status": response.status,
                        "candidate_enabled": owner.gate.enabled,
                    }
                finally:
                    upstream.close()

            do_GET = relay
            do_POST = relay
            do_PUT = relay
            do_PATCH = relay
            do_DELETE = relay

        self.server = UnixHTTP(str(self.path), Handler)
        os.chmod(self.path, 0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.gate.off()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)

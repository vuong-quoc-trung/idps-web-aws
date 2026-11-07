"""Privacy, bounded parser semantics and isolated transport regressions."""

import gzip
import http.client
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode

import pytest

from idps_ai.features import body_syntax_v1 as syntax
from idps_ai.features.body_syntax_transport import Ingress, QuietServer, SyntaxWorker, chunks

FORM = "application/x-www-form-urlencoded"
JSON = "application/json"


def value(vector, name):
    return vector[syntax.COLUMNS.index(name)]


@pytest.mark.parametrize(
    "media,body,state",
    [
        (FORM, None, "MISSING"),
        (FORM, b"", "EMPTY"),
        (FORM, b"message=hello", "OK"),
        (JSON, b'{"message":"hello"}', "OK"),
        (JSON, b'{"message":', "MALFORMED"),
        (JSON, b"[]", "UNSUPPORTED_TYPE"),
        (JSON, b'{"a":1,"a":2}', "MALFORMED"),
        (JSON, b'{"a":NaN}', "MALFORMED"),
        (FORM, b"message=%FF", "MALFORMED"),
        (FORM, b"x=" + b"a" * 9000, "OVERSIZE"),
        ("multipart/form-data; boundary=fake", b"private bytes", "UNSUPPORTED_TYPE"),
        ("text/plain", b"private bytes", "UNSUPPORTED_TYPE"),
        (FORM + "; charset=latin-1", b"message=hi", "UNSUPPORTED_TYPE"),
    ],
)
def test_status_and_no_partial_syntax(media, body, state):
    x = syntax.extract(body, media)
    assert syntax.state_of(x) == state
    syntax.validate_event(syntax.event("a" * 32, x))
    if state != "OK":
        assert not any(x[len(syntax.STATES) + len(syntax.MEDIA) :])


def test_semantic_syntax_and_determinism_without_arbitrary_names():
    x = syntax.extract(urlencode({"mtxMessage": "<svg onload=alert(1)>"}).encode(), FORM)
    assert value(x, "html_tag") == value(x, "event_assignment") == 1
    assert x == syntax.extract(urlencode({"mtxMessage": "<svg onload=alert(1)>"}).encode(), FORM)
    a = syntax.extract(b'{"unknown-person-name":"value"}', JSON)
    assert a == syntax.extract(b'{"different-name":"different-value"}', JSON)
    assert syntax.extract(b'{"password":"a"}', JSON) == syntax.extract(
        b'{"password":"<script> very different text"}', JSON
    )


def test_resource_encoding_truncation_and_declared_limits():
    assert (
        syntax.state_of(
            syntax.extract(gzip.compress(b"message=secret"), FORM, content_encoding="gzip")
        )
        == "UNSUPPORTED_ENCODING"
    )
    assert (
        syntax.state_of(syntax.extract(b"message=hi", FORM, transfer_encoding="chunked"))
        == "UNSUPPORTED_TRANSFER"
    )
    assert syntax.state_of(syntax.extract(b"message=hi", FORM, truncated=True)) == "TRUNCATED"
    assert syntax.extract(None, FORM, declared_oversize=True) == syntax.extract(
        b"x" * (syntax.MAX_BYTES + 1), FORM
    )
    assert syntax.state_of(syntax.extract(b"[" * 9 + b"0" + b"]" * 9, JSON)) == "RESOURCE_LIMIT"
    assert syntax.state_of(syntax.extract(b"&".join([b"q=x"] * 33), FORM)) == "RESOURCE_LIMIT"
    assert (
        syntax.state_of(syntax.extract(urlencode({"message": "x" * 1025}).encode(), FORM))
        == "RESOURCE_LIMIT"
    )


def test_canary_serialization_and_secret_value_invariance():
    canaries = [
        "FakePassword-" + secrets.token_hex(20),
        "FakeApiKey-" + secrets.token_hex(20),
        "FakeSession-" + secrets.token_hex(20),
        secrets.token_hex(32),
        "person-" + secrets.token_hex(8) + "@example.invalid",
        "+84912345678",
    ]
    fields = dict(
        zip(
            ["password", "api_key", "session_token", "arbitrary_private_field", "email", "phone"],
            canaries,
        )
    )
    reference = None
    for ct, body in [(FORM, urlencode(fields).encode()), (JSON, json.dumps(fields).encode())]:
        x = syntax.extract(body, ct)
        data = json.dumps(syntax.event("a" * 32, x)).encode()
        assert not any(c.encode() in data for c in canaries)
        changed = {k: "replacement" for k in fields}
        other = urlencode(changed).encode() if ct == FORM else json.dumps(changed).encode()
        assert x == syntax.extract(other, ct)
        reference = x
    allowed = syntax.extract(json.dumps({"message": canaries[3]}).encode(), JSON)
    assert (
        value(allowed, "restricted_values_bucket") == 1
        and value(allowed, "analyzed_values_bucket") == 0
    )
    assert reference is not None


def test_strict_versioning_rejects_raw_and_invalid_features_without_echo():
    event = syntax.event("a" * 32, syntax.extract(b"message=hi", FORM))
    for patch in [
        {"raw_body": "private-canary"},
        {"schema_version": "private-canary"},
        {"features": ["private-canary"]},
        {"request_id": "private-canary"},
    ]:
        with pytest.raises(ValueError) as err:
            syntax.validate_event(event | patch)
        assert "private-canary" not in str(err.value)


class Witness:
    """HTTP application witness, stores only in RAM for byte/header assertions."""

    def __init__(self):
        self.seen = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.headers.get("Transfer-Encoding") == "chunked":
                    # Retain exact chunk framing only in test RAM.
                    body = b"".join(chunks(self.rfile))
                else:
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                owner.seen.append((self.path, dict(self.headers), body))
                self.send_response_only(200)
                self.send_header("Content-Length", "2")
                self.send_header("X-Witness", "unchanged")
                self.end_headers()
                self.wfile.write(b"OK")

            do_GET = do_POST

        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def wait_event(worker, rid):
    deadline = time.monotonic() + 2
    while rid not in worker.events and time.monotonic() < deadline:
        time.sleep(0.005)
    assert rid in worker.events
    return worker.events[rid]


def request(port, body, headers):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", "/witness", body=body, headers=headers)
        response = conn.getresponse()
        assert response.status == 200 and response.getheader("X-Witness") == "unchanged"
        assert response.read() == b"OK"
    finally:
        conn.close()


def test_actual_http_datagram_worker_parity_and_canary_nonpersistence(tmp_path):
    canary = "FakeSecret-" + secrets.token_hex(24)
    rid = "b" * 32
    body = json.dumps(
        {
            "message": "<svg onload=alert(1)>",
            "password": canary,
            "email": canary + "@example.invalid",
        }
    ).encode()
    witness = Witness()
    worker = SyntaxWorker(tmp_path / "candidate")
    ingress = Ingress(witness.port, worker.socket_path, [rid])
    try:
        request(
            ingress.port,
            body,
            {
                "Content-Type": JSON,
                "X-Request-Id": rid,
                "Authorization": "Bearer " + canary,
                "Cookie": "session=" + canary,
            },
        )
        emitted = wait_event(worker, rid)
        assert emitted["features"] == syntax.extract(body, JSON)
        assert (
            witness.seen[0][2] == body and witness.seen[0][1]["Authorization"] == "Bearer " + canary
        )
        # Poisoned event exercises the actual worker rejection/error-log path.
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.sendto(json.dumps({"raw_body": canary}).encode(), worker.socket_path)
        deadline = time.monotonic() + 2
        while not worker.rejected and time.monotonic() < deadline:
            time.sleep(0.005)
        assert worker.rejected == 1
    finally:
        ingress.close()
        worker.close()
        witness.close()
    for file in tmp_path.rglob("*"):
        if file.is_file():
            assert canary.encode() not in file.read_bytes()


def test_parser_failure_disabled_and_absent_worker_do_not_block_application(tmp_path):
    witness = Witness()

    def broken(*args, **kwargs):
        raise RuntimeError("private-canary")

    ingress = Ingress(witness.port, tmp_path / "missing.sock", extractor=broken)
    try:
        request(ingress.port, b"{bad", {"Content-Type": JSON})
        assert ingress.failures == 1
        ingress.extractor = syntax.extract
        request(ingress.port, b"message=hello", {"Content-Type": FORM})
        assert ingress.dropped == 2
        ingress.enabled = False
        request(ingress.port, b"message=hello", {"Content-Type": FORM})
        assert len(witness.seen) == 3
    finally:
        ingress.close()
        witness.close()

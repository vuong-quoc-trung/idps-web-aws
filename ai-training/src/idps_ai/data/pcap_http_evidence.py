"""Recover bounded HTTP body facts from an existing private lab PCAP.

This authenticates observed bytes, not semantic intent or exploit success. Raw
bodies and credentials never enter the JSON ledger or diagnostics.
"""

import hashlib
import hmac
import ipaddress
import json
import secrets
import struct
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.evidence_campaign import verify_blind_queue
from idps_ai.data.snapshot import new_destination

MAX_PCAP_BYTES = 128 * 1024 * 1024
MAX_HTTP_BYTES = 512 * 1024
SAFE_FORM_FIELDS = frozenset(("username", "password", "email", "q", "search", "token", "_csrf"))


def _http_streams(path):
    path = Path(path)
    if path.stat().st_size > MAX_PCAP_BYTES:
        raise PipelineError("Private PCAP exceeds bounded body evidence budget")
    data = path.read_bytes()
    if (
        len(data) < 24
        or data[:4] != b"\xd4\xc3\xb2\xa1"
        or struct.unpack_from("<I", data, 20)[0] != 1
    ):
        raise PipelineError("Only bounded little-endian Ethernet PCAP is supported")
    parts = defaultdict(dict)
    offset = 24
    while offset < len(data):
        if offset + 16 > len(data):
            raise PipelineError("Partial PCAP packet header")
        _, _, size, original = struct.unpack_from("<IIII", data, offset)
        offset += 16
        if size > 65535 or original < size or offset + size > len(data):
            raise PipelineError("Invalid or truncated PCAP packet")
        frame = data[offset : offset + size]
        offset += size
        if len(frame) < 54 or frame[12:14] != b"\x08\x00":
            continue
        ip = frame[14:]
        ihl = (ip[0] & 15) * 4
        if ip[0] >> 4 != 4 or ihl < 20 or len(ip) < ihl + 20 or ip[9] != 6:
            continue
        total_length = struct.unpack_from("!H", ip, 2)[0]
        if total_length < ihl + 20 or total_length > len(ip):
            raise PipelineError("Invalid IPv4 length in private PCAP")
        ip = ip[:total_length]
        # Fragmented IP needs a different reassembly protocol; fail closed.
        if struct.unpack_from("!H", ip, 6)[0] & 0x3FFF:
            raise PipelineError("Fragmented TCP packet cannot prove HTTP body")
        tcp = ip[ihl:]
        thl = (tcp[12] >> 4) * 4
        if thl < 20 or len(tcp) < thl:
            raise PipelineError("Invalid TCP header in private PCAP")
        payload = tcp[thl:]
        if not payload:
            continue
        source_port, dest_port, sequence = struct.unpack_from("!HHI", tcp)
        if 18881 not in (source_port, dest_port):
            continue
        key = (
            str(ipaddress.ip_address(ip[12:16])),
            source_port,
            str(ipaddress.ip_address(ip[16:20])),
            dest_port,
        )
        old = parts[key].get(sequence)
        if old is not None and old != payload:
            raise PipelineError("Conflicting TCP retransmission in private PCAP")
        parts[key][sequence] = payload
    streams = {}
    for key, segments in parts.items():
        previous_end = None
        stream = bytearray()
        for sequence, payload in sorted(segments.items()):
            if previous_end is None:
                stream.extend(payload)
                previous_end = sequence + len(payload)
            elif sequence > previous_end:
                raise PipelineError("TCP gap prevents request body verification")
            elif sequence + len(payload) > previous_end:
                stream.extend(payload[previous_end - sequence :])
                previous_end = sequence + len(payload)
            if len(stream) > MAX_HTTP_BYTES + 16384:
                raise PipelineError("HTTP stream exceeds body evidence budget")
        streams[key] = bytes(stream)
    return streams


def _headers(stream):
    end = stream.find(b"\r\n\r\n")
    if end < 0 or end > 16384:
        raise PipelineError("HTTP header missing or too long in private PCAP")
    lines = stream[:end].split(b"\r\n")
    try:
        first = lines[0].decode("ascii")
        headers = defaultdict(list)
        for line in lines[1:]:
            name, value = line.split(b":", 1)
            headers[name.decode("ascii").lower()].append(value.strip().decode("latin1"))
    except (UnicodeError, ValueError):
        raise PipelineError("Invalid HTTP header in private PCAP") from None
    return first, headers, stream[end + 4 :]


def extract_request_bodies(pcap, expected, key):
    """Return per-request HMAC/shape after binding response ID to the TCP stream."""
    streams = _http_streams(pcap)
    found = {}
    for direction, request_stream in streams.items():
        source_ip, source_port, dest_ip, dest_port = direction
        if dest_port != 18881:
            continue
        reverse = (dest_ip, dest_port, source_ip, source_port)
        if reverse not in streams:
            raise PipelineError("HTTP request has no corresponding PCAP response")
        request_line, headers, rest = _headers(request_stream)
        response_line, response_headers, _ = _headers(streams[reverse])
        fields = request_line.split(" ")
        if len(fields) != 3 or fields[2] not in ("HTTP/1.0", "HTTP/1.1"):
            raise PipelineError("Invalid HTTP request line in private PCAP")
        method, target, _ = fields
        if not response_line.startswith("HTTP/1.") or len(response_line.split(" ")) < 2:
            raise PipelineError("Invalid HTTP response in private PCAP")
        try:
            status = int(response_line.split(" ")[1])
        except ValueError:
            raise PipelineError("Invalid HTTP status in private PCAP") from None
        ids = response_headers.get("x-request-id", [])
        if len(ids) != 1:
            raise PipelineError("PCAP response lacks a unique edge request ID")
        rid = ids[0]
        if rid not in expected:
            continue  # an explicitly owned fixture setup request outside the plan
        if rid in found or source_ip != expected[rid]["source_ip"]:
            raise PipelineError("PCAP request ID or campaign source IP is ambiguous")
        if headers.get("transfer-encoding"):
            raise PipelineError("Chunked request body needs separate bounded decoder")
        lengths = headers.get("content-length", [])
        if len(lengths) > 1:
            raise PipelineError("Ambiguous HTTP request body length")
        try:
            body_length = int(lengths[0]) if lengths else 0
        except ValueError:
            raise PipelineError("Invalid HTTP request body length") from None
        if body_length < 0 or body_length > MAX_HTTP_BYTES or len(rest) < body_length:
            raise PipelineError("Partial or oversized HTTP request body")
        body = rest[:body_length]
        if len(rest) != body_length:
            raise PipelineError("Multiple HTTP requests on one TCP connection are unsupported")
        if (
            method != expected[rid]["http_method"]
            or status != expected[rid]["status_code"]
            or hashlib.sha256(target.encode()).hexdigest() != expected[rid]["target_sha256"]
        ):
            raise PipelineError("PCAP request/response disagrees with pinned capture")
        content_type = headers.get("content-type", [])
        field_names = []
        if (
            body
            and len(content_type) == 1
            and content_type[0].split(";", 1)[0].lower() == "application/x-www-form-urlencoded"
        ):
            try:
                field_names = sorted(
                    {
                        name if name in SAFE_FORM_FIELDS else "[redacted]"
                        for name, _ in parse_qsl(body.decode("utf-8"), keep_blank_values=True)
                    }
                )
            except UnicodeError:
                raise PipelineError("Form body is not UTF-8") from None
            if len(field_names) > 20 or any(len(name) > 64 for name in field_names):
                raise PipelineError("Form field names exceed private review budget")
        found[rid] = {
            "request_id": rid,
            "campaign_id": expected[rid]["campaign_id"],
            "http_method": method,
            "status_code": status,
            "body_observed_in_pcap": True,
            "body_length": body_length,
            "body_field_names": field_names,
            "body_hmac_sha256": hmac.new(key, body, hashlib.sha256).hexdigest(),
            "target_sha256": expected[rid]["target_sha256"],
        }
    if set(found) != set(expected):
        raise PipelineError("PCAP does not cover every pinned request and response")
    return found


def collect_body_evidence(
    plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir, output
):
    """Write private HMAC evidence; no review decision or admission side effect."""
    verified = verify_blind_queue(
        plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir
    )
    plan = load_json(Path(plan_dir) / "plan.json")
    source_ips = {c["campaign_id"]: c["source_ip"] for c in plan["campaigns"]}
    with (Path(capture_dir) / "pending-evidence.jsonl").open() as stream:
        expected = {r["request_id"]: r for r in (json.loads(line) for line in stream)}
    if len(expected) != verified["requests"]:
        raise PipelineError("Capture request count changed before PCAP body extraction")
    for row in expected.values():
        row["source_ip"] = source_ips[row["campaign_id"]]
    output = new_destination(output)
    key = secrets.token_bytes(32)
    pcap = Path(lab_dir) / "traffic.pcap"
    rows = extract_request_bodies(pcap, expected, key)
    output.mkdir(mode=0o700)
    key_path = output / "body-hmac-key.bin"
    with key_path.open("xb") as stream:
        stream.write(key)
    key_path.chmod(0o600)
    ledger = output / "post-body-evidence.jsonl"
    with ledger.open("x") as stream:
        for rid in sorted(rows):
            stream.write(json.dumps(rows[rid], sort_keys=True) + "\n")
    ledger.chmod(0o600)
    result = {
        "format_version": 1,
        "status": "PCAP_BODY_BYTES_OBSERVED_NO_SEMANTIC_LABEL",
        "requests": len(rows),
        "post_bodies_observed": sum(
            r["http_method"] == "POST" and r["body_length"] > 0 for r in rows.values()
        ),
        "pcap_sha256": file_sha256(pcap),
        "capture_report_sha256": file_sha256(Path(capture_dir) / "report.json"),
        "review_queue_sha256": file_sha256(Path(review_dir) / "blind-review.jsonl"),
        "body_evidence_sha256": file_sha256(ledger),
        "hmac_key_sha256": file_sha256(key_path),
        "training_admission": 0,
        "limits": "Body HMAC and form field names prove captured bytes only. Password/token values are never exported. The private HMAC key and PCAP must not be published; exploit outcome still requires an application oracle.",
    }
    atomic_json(output / "report.json", result)
    return result


def verify_body_evidence(
    plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir, output
):
    """Recompute body facts from the pinned PCAP without disclosing body bytes."""
    verified = verify_blind_queue(
        plan_dir, lab_dir, capture_dir, review_dir, collector_source, three_source_dir
    )
    output = Path(output)
    report = load_json(output / "report.json")
    pcap = Path(lab_dir) / "traffic.pcap"
    ledger = output / "post-body-evidence.jsonl"
    key_path = output / "body-hmac-key.bin"
    if (
        report.get("status") != "PCAP_BODY_BYTES_OBSERVED_NO_SEMANTIC_LABEL"
        or report.get("requests") != verified["requests"]
        or report.get("training_admission") != 0
        or report.get("pcap_sha256") != file_sha256(pcap)
        or report.get("capture_report_sha256") != file_sha256(Path(capture_dir) / "report.json")
        or report.get("review_queue_sha256") != file_sha256(Path(review_dir) / "blind-review.jsonl")
        or report.get("body_evidence_sha256") != file_sha256(ledger)
        or report.get("hmac_key_sha256") != file_sha256(key_path)
        or key_path.stat().st_mode & 0o077
        or ledger.stat().st_mode & 0o077
    ):
        raise PipelineError("PCAP body evidence provenance or privacy mode changed")
    key = key_path.read_bytes()
    if len(key) != 32:
        raise PipelineError("Private body HMAC key length changed")
    plan = load_json(Path(plan_dir) / "plan.json")
    source_ips = {c["campaign_id"]: c["source_ip"] for c in plan["campaigns"]}
    with (Path(capture_dir) / "pending-evidence.jsonl").open() as stream:
        expected = {r["request_id"]: r for r in (json.loads(line) for line in stream)}
    for row in expected.values():
        row["source_ip"] = source_ips[row["campaign_id"]]
    recomputed = extract_request_bodies(pcap, expected, key)
    observed = {}
    with ledger.open("rb") as stream:
        while line := stream.readline(65537):
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise PipelineError("Invalid bounded PCAP body evidence line")
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                raise PipelineError("Invalid PCAP body evidence JSONL") from None
            rid = row.get("request_id")
            if rid in observed or row != recomputed.get(rid):
                raise PipelineError("PCAP body fact differs from the captured bytes")
            observed[rid] = row
    if set(observed) != set(recomputed):
        raise PipelineError("PCAP body evidence does not cover every request")
    return {
        "status": "PCAP_BODY_EVIDENCE_REVERIFIED_NO_LABEL",
        "requests": len(observed),
        "post_bodies_observed": sum(
            r["http_method"] == "POST" and r["body_length"] > 0 for r in observed.values()
        ),
        "training_admission": 0,
    }

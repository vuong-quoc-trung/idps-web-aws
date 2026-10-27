"""Read-only finite-file adapters for the exact foundation producer contracts."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from idps_ai.common import REPO_ROOT, PipelineError
from idps_ai.data.privacy import METHODS, ROLES, pseudonym, request_numbers, safe_agent, safe_route


@dataclass(frozen=True)
class Input:
    source: str
    path: Path


def event_time(value):
    if not isinstance(value, str):
        raise PipelineError("Missing event timestamp")
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if time.tzinfo is None:
            raise ValueError
        return time.astimezone(timezone.utc).timestamp()
    except ValueError:
        raise PipelineError("Invalid or timezone-naive event timestamp") from None


def finite(value):
    return (
        float(value)
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        else None
    )


@lru_cache(maxsize=1)
def canonical_validator():
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads((REPO_ROOT / "contracts/canonical-event-v1.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


def normalize_record(source, value, key, identity):
    canonical = source in ("student", "canonical", "postgres-export")
    if canonical:
        value = value.get("canonical", value)
        if isinstance(value, str):
            value = json.loads(value)
        if not canonical_validator().is_valid(value):
            raise PipelineError("Canonical event violates frozen Schema v1")
        if source == "student" and value["source"] != "STUDENT_AUDIT":
            raise PipelineError("Student source mismatch")
        mapped = dict(value)
        identity = ":".join((mapped["source"], mapped["source_instance"], mapped["event_id"]))
    elif source == "nginx":
        if value.get("schema_version", "1.0") != "1.0":
            raise PipelineError("Unsupported Nginx schema version")
        mapped = dict(value, source="NGINX", event_type="http_request")
        mapped["status_code"] = value.get("status_code", value.get("status"))
        mapped["latency_ms"] = value.get("latency_ms")
        if mapped["latency_ms"] is None and finite(value.get("latency_seconds")) is not None:
            mapped["latency_ms"] = value["latency_seconds"] * 1000
    elif source == "suricata":
        http = value.get("http") or {}
        mapped = dict(
            value,
            source="SURICATA",
            client_ip=value.get("src_ip"),
            http_method=http.get("http_method"),
            uri_path=http.get("url"),
            query_string=None,
            request_id=http.get("request_id"),
            status_code=http.get("status"),
            response_bytes=http.get("length"),
            user_agent=http.get("http_user_agent"),
        )
        mapped["event_type"] = (
            "http_request"
            if value.get("event_type") == "http"
            else value.get("event_type", "other")
        )
        if "?" in str(mapped.get("uri_path") or ""):
            mapped["uri_path"], mapped["query_string"] = mapped["uri_path"].split("?", 1)
    else:
        raise PipelineError("Unsupported log adapter")
    timestamp = event_time(mapped.get("timestamp"))
    address = mapped.get("client_ip")
    if address is not None:
        try:
            if not isinstance(address, str):
                raise ValueError
            address = str(ipaddress.ip_address(address))
        except ValueError:
            raise PipelineError("Invalid client IP") from None
    status = mapped.get("status_code")
    if status is not None:
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            raise PipelineError("Invalid HTTP status")
    path, query = mapped.get("uri_path"), mapped.get("query_string")
    flow = mapped.get("flow") or {}
    flow_values = {
        name: finite(flow.get(name, flow.get(alias)))
        for name, alias in (
            ("duration_seconds", "age"),
            ("bytes_to_server", "bytes_toserver"),
            ("bytes_to_client", "bytes_toclient"),
            ("packets_to_server", "pkts_toserver"),
            ("packets_to_client", "pkts_toclient"),
        )
    }
    method = mapped.get("http_method")
    role = mapped.get("role")
    return {
        "event_key": pseudonym(key, "event", identity),
        "source": mapped["source"],
        "timestamp": timestamp,
        "request_key": pseudonym(key, "request", mapped.get("request_id")),
        "client_key": pseudonym(key, "ip", address),
        "flow_key": pseudonym(key, "flow", mapped.get("flow_id")),
        "user_key": pseudonym(key, "user", mapped.get("user_id")),
        "session_key": pseudonym(key, "session", mapped.get("session_hmac")),
        "http_method": method if method in METHODS else "OTHER",
        "uri_path": safe_route(path) if path is not None else None,
        "status_code": status,
        "latency_ms": finite(mapped.get("latency_ms")),
        "role": role if role in ROLES else "UNKNOWN",
        "user_agent": safe_agent(mapped.get("user_agent")),
        "event_type": mapped.get("event_type")
        if mapped.get("event_type") in ("http_request", "flow", "alert", "dns", "tls", "other")
        else "other",
        "request_bytes": finite(mapped.get("request_bytes")),
        "response_bytes": finite(mapped.get("response_bytes")),
        "flow": flow_values,
        "numeric": request_numbers(path, query, mapped.get("query_features")),
        "redacted": True,
        "truncated": bool(mapped.get("truncated", False)),
        "provenance": "canonical" if canonical else "native_log",
    }


COMBINED = re.compile(
    r'^(\S+) \S+ \S+ \[([^\]]+)\] "([A-Z]+) ([^"]+) HTTP/[\d.]+" (\d{3}) (\d+|-) "(?:[^"\\]|\\.)*" "((?:[^"\\]|\\.)*)"$'
)


def read_events(inputs, key, stats=None, max_line_bytes=65536, max_records=2_000_000):
    stats = stats if stats is not None else {}
    count = 0
    for item in inputs:
        path = Path(item.path)
        before = path.stat()
        with path.open("rb") as stream:
            while True:
                line = stream.readline(max_line_bytes + 1)
                if not line:
                    break
                count += 1
                if count > max_records:
                    raise PipelineError(
                        "Input record limit exceeded; create smaller immutable snapshots"
                    )
                if len(line) > max_line_bytes:
                    while line and not line.endswith(b"\n"):
                        line = stream.readline(max_line_bytes + 1)
                    stats["oversized"] = stats.get("oversized", 0) + 1
                    continue
                if not line.endswith(b"\n"):
                    stats["partial"] = stats.get("partial", 0) + 1
                    continue
                try:
                    if item.source == "nginx" and not line.lstrip().startswith(b"{"):
                        match = COMBINED.fullmatch(line.decode().strip())
                        if not match:
                            raise PipelineError("Invalid combined log")
                        ip, date, method, target, status, size, ua = match.groups()
                        uri, _, query = target.partition("?")
                        value = {
                            "timestamp": datetime.strptime(
                                date, "%d/%b/%Y:%H:%M:%S %z"
                            ).isoformat(),
                            "client_ip": ip,
                            "http_method": method,
                            "uri_path": uri,
                            "query_string": query or None,
                            "status": int(status),
                            "response_bytes": None if size == "-" else int(size),
                            "user_agent": ua,
                        }
                    else:
                        value = json.loads(line)
                    event = normalize_record(
                        item.source, value, key, hashlib.sha256(line).hexdigest()
                    )
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                    stats["invalid"] = stats.get("invalid", 0) + 1
                    continue
                stats["accepted"] = stats.get("accepted", 0) + 1
                yield event
        after = path.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise PipelineError("Input changed while reading; use an immutable export/snapshot")

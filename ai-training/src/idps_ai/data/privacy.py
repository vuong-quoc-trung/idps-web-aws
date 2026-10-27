"""Only whitelisted literals, pseudonyms and numeric structure leave the reader."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from collections import Counter
from urllib.parse import unquote, urlsplit

from idps_ai.common import PipelineError

ROUTES = frozenset(
    "api auth login logout csrf me profile completion academic classmates students users faculties majors classes training-programs addresses family-members emergency-contacts post-graduation-contacts profile-options access-logs activate activation verify send forgot-password reset-password change-password reissue-token dashboard catalog assets public images health robots.txt index.html favicon.ico".split()
)
METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "CONNECT", "TRACE", "OTHER")
ROLES = ("ADMIN", "STAFF", "STUDENT", "ANONYMOUS", "UNKNOWN")
PRODUCTS = (
    "sqlmap",
    "nikto",
    "nmap",
    "gobuster",
    "nuclei",
    "ffuf",
    "dirbuster",
    "masscan",
    "acunetix",
    "zgrab",
    "Mozilla",
    "Chrome",
    "Chromium",
    "Firefox",
    "Safari",
    "Edge",
    "curl",
    "wget",
    "python-requests",
    "PostmanRuntime",
    "Go-http-client",
)
SENSITIVE = re.compile(
    r"password|passwd|secret|token|cookie|authorization|session|csrf|otp|proof|code|email|username|phone|name|address|cccd",
    re.I,
)
PII = re.compile(
    r"[\w.+-]+@[\w.-]+|\b(?:\d[ -]?){9,}\b|eyJ[\w-]+\.[\w-]+\.[\w-]+|(?i:bearer|basic)\s+\S+|[A-Za-z0-9_-]{40,}"
)


def pseudonym(key, purpose, value):
    if len(key) < 32:
        raise PipelineError("Training redaction key must contain at least 32 bytes")
    if value is None or value == "":
        return None
    return hmac.new(key, (purpose + ":" + str(value)).encode(), hashlib.sha256).hexdigest()


def safe_route(value):
    path = str(value or "/")[:8192]
    for _ in range(2):
        path = unquote(path, errors="replace")
    if "://" in path:
        path = urlsplit(path).path
    path = path.split("?", 1)[0].split("#", 1)[0]
    parts = []
    sensitive_tail = False
    for segment in path.split("/"):
        if not segment:
            continue
        segment = segment.split(";", 1)[0]
        if sensitive_tail:
            safe = "[redacted]"
        elif SENSITIVE.fullmatch(segment):
            safe = "[redacted]"
            sensitive_tail = True
        elif segment in ROUTES or segment in ("[id]", "[redacted]"):
            safe = segment
        elif segment.isascii() and segment.isdigit():
            safe = "[id]"
        else:
            safe = "[redacted]"
        parts.append(safe)
    return ("/" + "/".join(parts))[:512]


def safe_agent(value):
    if value is None:
        return None
    lower = str(value)[:4096].lower()
    names = [
        name
        for name in PRODUCTS
        if re.search(r"(?<![a-z0-9])" + re.escape(name.lower()) + r"(?![a-z0-9])", lower)
        or (name == "Edge" and re.search(r"(?<![a-z0-9])edg/", lower))
    ]
    return " ".join(names) if names else "[REDACTED]"


def entropy(text):
    if not text:
        return 0.0
    return -sum((n / len(text)) * math.log2(n / len(text)) for n in Counter(text).values())


def request_numbers(path, query, original=None):
    """Ephemeral lexical analysis; raw strings are NEVER returned or persisted.

    Credential values/PII are removed before numeric analysis. Upstream-masked
    values are unavailable, not reconstructed. Original five query counters are
    used only when an actual producer supplied them.
    """
    path_missing = path is None
    path = PII.sub("[redacted]", str(path or "/")[:8192])
    fields = []
    safe_keys = {
        "q",
        "search",
        "query",
        "filter",
        "page",
        "size",
        "sort",
        "limit",
        "offset",
        "id",
        "status",
        "role",
        "from",
        "to",
    }
    for field in str(query or "")[:8192].split("&")[:64]:
        if not field:
            continue
        key, _, value = field.partition("=")
        safe_key = key if key.lower() in safe_keys else "[key]"
        fields.append(
            "[redacted]"
            if SENSITIVE.search(unquote(key))
            else safe_key + "=" + PII.sub("[redacted]", value)
        )
    path_masked = "[redacted]" in path.lower() or "[id]" in path.lower()
    visible_query = "&".join(field for field in fields if "[redacted]" not in field.lower())
    query_masked = bool(fields) and not visible_query
    view = ("" if path_masked else path) + "?" + visible_query
    decoded = unquote(unquote(view)).lower()
    n = max(len(view), 1)
    result = {
        "uri_length": float(len(safe_route(path))) if not path_missing else 0.0,
        "query_length": float(len(visible_query)),
        "path_depth": float(len([s for s in safe_route(path).split("/") if s])),
        "parameter_count": float(len(fields)),
        "uri_entropy": entropy(path) if not path_masked else 0.0,
        "query_entropy": entropy(visible_query),
        "digit_ratio": sum(c.isdigit() for c in view) / n,
        "special_ratio": sum(not c.isalnum() for c in view) / n,
        "uri_lexical_available": float(not path_masked and not path_missing),
        "query_lexical_available": float(query is not None and not query_masked),
        "object_identity_available": 0.0,
        "sqli_keywords": float(
            len(
                re.findall(
                    r"\b(?:union|select|sleep|benchmark|or|and|drop|extractvalue)\b", decoded
                )
            )
        ),
        "xss_tokens": float(len(re.findall(r"<script|onerror|onload|javascript:", decoded))),
        "traversal_tokens": float(decoded.count("../")),
    }
    for name, token in (
        ("quote_single", "'"),
        ("quote_double", '"'),
        ("semicolon", ";"),
        ("percent", "%"),
        ("lt", "<"),
        ("gt", ">"),
        ("dollar", "$"),
        ("pipe", "|"),
    ):
        result[name] = float(view.count(token))
    for name in ("length", "parameter_count", "percent_count", "quote_count", "operator_count"):
        value = original.get(name) if isinstance(original, dict) else None
        result["query_original_" + name] = (
            float(min(max(value, 0), 1e6))
            if isinstance(value, (float, int)) and math.isfinite(value)
            else 0.0
        )
    result["query_original_available"] = float(isinstance(original, dict))
    return result

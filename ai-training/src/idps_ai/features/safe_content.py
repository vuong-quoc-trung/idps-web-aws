"""Bounded symbolic HTTP content for weak-label research; no raw values leave memory."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from idps_ai.common import PipelineError

PRIVATE = re.compile(
    r"password|passwd|secret|token|cookie|authorization|session|csrf|otp|api.?key|jwt|bearer|email|username|phone|address|cccd",
    re.I,
)
WORDS = frozenset(
    "union select from where and or sleep benchmark waitfor pg_sleep information_schema "
    "script javascript onerror onload alert eval document window iframe svg img src "
    "etc passwd env git config php cmd exec system bash sh curl wget cat "
    "http https file data base64 wp admin login api xml json".split()
)
HEADER_NAMES = frozenset(
    "accept accept-encoding content-type content-length host user-agent referer origin "
    "x-forwarded-for x-real-ip authorization cookie transfer-encoding connection".split()
)
PUNCT = frozenset("/?&=;:'\"<>.$|\\(){}[]#@%+-_*!`")
PARTS = re.compile(r"[A-Za-z_]+|[0-9]+|[^A-Za-z0-9\s]", re.ASCII)
HEADERS = re.compile(r"(?<!\S)([A-Za-z-]{2,40}):", re.ASCII)
SAFE_METHODS = frozenset("GET HEAD OPTIONS POST PUT PATCH DELETE CONNECT TRACE".split())


def _decode(value):
    for _ in range(2):
        changed = unquote(value)
        if changed == value:
            break
        value = changed
    return value


def _symbols(value, limit=4096):
    result = []
    for item in PARTS.findall(_decode(value[:limit]))[:1024]:
        if item[0].isalpha() or item[0] == "_":
            result.append(item.lower() if item.lower() in WORDS else "w")
        elif item[0].isdigit():
            result.append("n")
        else:
            result.append(item if item in PUNCT else "x")
    return " ".join(result)


def symbolic_request(method, url, headers, body):
    """Return only allowlisted words, character classes and punctuation.

    Secret query values are dropped. Any body mentioning a secret-key family is
    withheld in full; header values are never inspected or emitted.
    """
    if not isinstance(method, str) or not isinstance(url, str) or not url or len(url) > 8192:
        raise PipelineError("Invalid request-content input")
    if headers is not None and not isinstance(headers, str):
        raise PipelineError("Invalid header-content input")
    if body is not None and not isinstance(body, str):
        raise PipelineError("Invalid body-content input")
    parsed = urlsplit(url)
    path = _symbols(parsed.path)
    fields = []
    redacted_query = 0
    for field in parsed.query.split("&")[:64] if parsed.query else ():
        key, _, value = field.partition("=")
        if PRIVATE.search(_decode(key)):
            redacted_query += 1
            continue
        fields.append(_symbols(key, 256) + " = " + _symbols(value, 2048))
    names = sorted(
        name.lower()
        for name in HEADERS.findall((headers or "")[:8192])
        if name.lower() in HEADER_NAMES
    )[:32]
    body_redacted = bool(body and PRIVATE.search(body[:4096]))
    body_symbols = "redacted" if body_redacted else _symbols(body or "")
    safe = " method " + (method if method in SAFE_METHODS else "OTHER")
    safe += " path " + path + " query " + " & ".join(fields)
    safe += " headers " + " ".join(names) + " body " + body_symbols
    # Lengths are capped and bucketed; raw values and exact length never leave.
    safe += " size " + str(min(len(body or "") // 128, 32))
    return safe, {
        "redacted_query_fields": redacted_query,
        "body_redacted": body_redacted,
        "body_nonempty": bool(body),
        "header_names_retained": len(names),
    }

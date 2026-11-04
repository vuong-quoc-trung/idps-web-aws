"""Coarse HTTP syntax profile for request-only weak-label research."""

from __future__ import annotations

import math
from collections import Counter
from urllib.parse import unquote, urlsplit

from idps_ai.common import PipelineError
from idps_ai.data.privacy import PII
from idps_ai.features.safe_content import HEADER_NAMES, HEADERS, PARTS, PRIVATE, PUNCT, WORDS

VALUE_HEADERS = frozenset(
    {"user-agent", "content-type", "accept", "accept-encoding", "transfer-encoding"}
)
SAFE_METHODS = frozenset("GET HEAD OPTIONS POST PUT PATCH DELETE CONNECT TRACE".split())
SECURITY_WORDS = WORDS | frozenset(
    "sqlmap nikto nmap gobuster nuclei ffuf dirbuster xp_cmdshell or true false ".split()
)


def _bucket(length):
    return str(min(max(int(length).bit_length(), 0), 12))


def _decode(value):
    for _ in range(2):
        changed = unquote(value)
        if changed == value:
            break
        value = changed
    return value


def _syntax(value, limit=4096):
    output = []
    for token in PARTS.findall(_decode(value[:limit]))[:1024]:
        if token[0].isalpha() or token[0] == "_":
            output.append(
                token.lower() if token.lower() in SECURITY_WORDS else "w" + _bucket(len(token))
            )
        elif token[0].isdigit():
            output.append("n" + _bucket(len(token)))
        else:
            output.append(token if token in PUNCT else "x")
    return " ".join(output)


def _entropy_bucket(value):
    if not value:
        return "0"
    text = value[:4096]
    counts = Counter(text)
    entropy = -sum((n / len(text)) * math.log2(n / len(text)) for n in counts.values())
    return str(min(int(entropy), 7))


def rich_request(method, url, headers, body):
    """Return allowlisted words, syntax classes and coarse length/entropy bins.

    No raw word outside the fixed security vocabulary is retained. Header values
    are inspected only for a small nonsecret allowlist; cookie/authorization/host
    values never enter the view. Secret/PII query fields and whole sensitive body
    are withheld. Buckets can still reveal structure and need private storage.
    """
    if not isinstance(method, str) or not isinstance(url, str) or not url or len(url) > 8192:
        raise PipelineError("Invalid rich request input")
    if headers is not None and not isinstance(headers, str):
        raise PipelineError("Invalid rich headers")
    if body is not None and not isinstance(body, str):
        raise PipelineError("Invalid rich body")
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise PipelineError("Invalid rich request URL") from None
    parts = ["method", method if method in SAFE_METHODS else "OTHER"]
    path = parsed.path
    parts.extend(("path", _syntax(path), "pathlen", _bucket(len(path))))
    redacted_fields = 0
    visible_fields = 0
    for field in parsed.query.split("&")[:64] if parsed.query else ():
        key, _, value = field.partition("=")
        if (
            PRIVATE.search(_decode(key))
            or PRIVATE.search(_decode(value))
            or PII.search(_decode(value))
        ):
            redacted_fields += 1
            continue
        parts.extend(
            (
                "key",
                _syntax(key, 256),
                "value",
                _syntax(value, 2048),
                "vlen",
                _bucket(len(value)),
                "ventropy",
                _entropy_bucket(value),
            )
        )
        visible_fields += 1
    parts.extend(("qfields", _bucket(visible_fields), "qredacted", _bucket(redacted_fields)))
    header_text = (headers or "")[:8192]
    matches = list(HEADERS.finditer(header_text))[:64]
    for i, found in enumerate(matches):
        name = found.group(1).lower()
        if name not in HEADER_NAMES:
            continue
        parts.extend(("header", name))
        if name in VALUE_HEADERS:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(header_text)
            value = header_text[found.end() : end]
            if not PRIVATE.search(value) and not PII.search(value):
                parts.extend(("hsyntax", _syntax(value, 512), "hlen", _bucket(len(value))))
            else:
                parts.append("hredacted")
    body_text = body or ""
    if PRIVATE.search(body_text[:4096]) or PII.search(body_text[:4096]):
        parts.extend(("body", "redacted"))
        body_redacted = True
    else:
        parts.extend(
            (
                "body",
                _syntax(body_text),
                "blen",
                _bucket(len(body_text)),
                "bentropy",
                _entropy_bucket(body_text),
            )
        )
        body_redacted = False
    return " ".join(parts), {
        "redacted_query_fields": redacted_fields,
        "body_redacted": body_redacted,
        "body_nonempty": bool(body_text),
        "visible_query_fields": visible_fields,
    }

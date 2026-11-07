"""Bounded, lossy body syntax for an isolated research boundary, never raw telemetry.

No labels, routes, sources, sessions, IDs, hashes of input, or learned vocabulary
participate in extraction. Protected/unknown field values are never profiled or emitted.
This module is separate from every frozen encoder and model.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl

from idps_ai.common import digest
from idps_ai.data.privacy import PII
from idps_ai.features.safe_content import PRIVATE

VERSION = "http-body-syntax-v1"
MAX_BYTES = 8192
MAX_FIELDS = 32
MAX_DEPTH = 8
MAX_VALUE = 1024
# Research purpose allowlist: ordinary text/search fields, plus pinned DVWA
# mtxMessage/ip forms. No claim of approval for an arbitrary application's fields.
ALLOW = frozenset(
    {
        "message",
        "comment",
        "text",
        "description",
        "content",
        "q",
        "query",
        "search",
        "ip",
        "mtxmessage",
    }
)
STATES = (
    "MISSING",
    "EMPTY",
    "OK",
    "MALFORMED",
    "OVERSIZE",
    "UNSUPPORTED_TYPE",
    "UNSUPPORTED_ENCODING",
    "UNSUPPORTED_TRANSFER",
    "RESOURCE_LIMIT",
    "TRUNCATED",
    "EXTRACTION_ERROR",
)
MEDIA = ("FORM", "JSON", "OTHER", "MISSING")
PUNCT = (
    ("lt", "<"),
    ("gt", ">"),
    ("single_quote", "'"),
    ("double_quote", '"'),
    ("lparen", "("),
    ("rparen", ")"),
    ("lbrace", "{"),
    ("rbrace", "}"),
    ("lbracket", "["),
    ("rbracket", "]"),
    ("semicolon", ";"),
    ("amp", "&"),
    ("pipe", "|"),
    ("dollar", "$"),
    ("backtick", "`"),
    ("equals", "="),
    ("backslash", "\\"),
)
PATTERNS = {
    "html_tag": re.compile(r"</?[a-z][^<>]{0,64}>", re.I),
    "event_assignment": re.compile(r"\bon[a-z]{2,20}\s*=", re.I),
    "script_scheme": re.compile(r"\bjavascript\s*:", re.I),
    "sql_boolean": re.compile(r"\b(?:or|and)\s+(?:[0-9]+\s*=|true\b|false\b)", re.I),
    "sql_union": re.compile(r"\bunion\s+(?:all\s+)?select\b", re.I),
    "shell_substitution": re.compile(r"\$\(|`"),
    "percent_escape": re.compile(r"%[0-9a-f]{2}", re.I),
    "html_entity": re.compile(r"&(?:#[0-9]{1,6}|#x[0-9a-f]{1,6}|[a-z]{2,8});", re.I),
}
COUNTS = (
    "fields_bucket",
    "allowed_fields_bucket",
    "ignored_fields_bucket",
    "analyzed_values_bucket",
    "restricted_values_bucket",
    "nonstring_values_bucket",
)
COLUMNS = (
    tuple("state_" + s for s in STATES)
    + tuple("media_" + s for s in MEDIA)
    + COUNTS
    + tuple("punct_" + n for n, _ in PUNCT)
    + tuple(PATTERNS)
)
MAXIMA = (
    (1,) * (len(STATES) + len(MEDIA))
    + (6,) * len(COUNTS)
    + (3,) * len(PUNCT)
    + (1,) * len(PATTERNS)
)


def contract():
    return {
        "version": VERSION,
        "columns": list(COLUMNS),
        "maxima": list(MAXIMA),
        "limits": {
            "body_bytes": MAX_BYTES,
            "fields": MAX_FIELDS,
            "depth": MAX_DEPTH,
            "value_characters": MAX_VALUE,
        },
        "allowlist": sorted(ALLOW),
        "semantics": "Only root allowlisted string values, nonrecursive; protected/unknown values ignored; matching PII/secret allowed values withheld; aggregate clipped syntax, no value/name/ngram/hash output",
        "frozen_compatible": False,
    }


CONTRACT_SHA256 = digest(contract())


class Limit(Exception):
    pass


def _bucket(n):
    return min(int(n).bit_length(), 6)


def _blank(state, media):
    x = [0] * len(COLUMNS)
    x[STATES.index(state)] = 1
    x[len(STATES) + MEDIA.index(media)] = 1
    return x


def state_of(vector):
    return STATES[vector[: len(STATES)].index(1)]


def _depth_guard(text):
    depth = 0
    quoted = escaped = False
    for c in text:
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise Limit()
        elif c in "]}":
            depth -= 1


def _object(items):
    if len(items) > MAX_FIELDS:
        raise Limit()
    result = {}
    for k, v in items:
        if k in result:
            raise ValueError("Duplicate JSON key")
        result[k] = v
    return result


def _constant(_):
    raise ValueError("Nonfinite JSON")


def extract(
    body,
    content_type=None,
    *,
    content_encoding=None,
    transfer_encoding=None,
    truncated=False,
    declared_oversize=False,
):
    """Return fixed integer syntax vector; exceptions never contain input values.

    Inputs exist transiently in the caller's trusted RAM. Unsupported/failed inputs
    emit only state/media indicators, never guessed or partially parsed syntax.
    """
    ct = (content_type or "").lower()[:256]
    mime = ct.split(";", 1)[0].strip()
    media = (
        "FORM"
        if mime == "application/x-www-form-urlencoded"
        else "JSON"
        if mime == "application/json"
        else "OTHER"
        if mime
        else "MISSING"
    )
    if body is None and not declared_oversize:
        return _blank("MISSING", media)
    if transfer_encoding and transfer_encoding.lower().strip() not in {"", "identity"}:
        return _blank("UNSUPPORTED_TRANSFER", media)
    if content_encoding and content_encoding.lower().strip() not in {"", "identity"}:
        return _blank("UNSUPPORTED_ENCODING", media)
    if truncated:
        return _blank("TRUNCATED", media)
    if declared_oversize or len(body) > MAX_BYTES:
        return _blank("OVERSIZE", media)
    if not body:
        return _blank("EMPTY", media)
    if media not in {"FORM", "JSON"} or (
        "charset=" in ct and not re.search(r"charset\s*=\s*[\"']?utf-?8\b", ct)
    ):
        return _blank("UNSUPPORTED_TYPE", media)
    try:
        text = body.decode("utf-8", errors="strict")
        if media == "JSON":
            _depth_guard(text)
            parsed = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
            if not isinstance(parsed, dict):
                return _blank("UNSUPPORTED_TYPE", media)
            items = list(parsed.items())
        else:
            if text.count("&") + 1 > MAX_FIELDS:
                raise Limit()
            items = parse_qsl(
                text, keep_blank_values=True, errors="strict", max_num_fields=MAX_FIELDS
            )
        if len(items) > MAX_FIELDS:
            raise Limit()
        numbers = {k: 0 for k in COUNTS}
        numbers["fields_bucket"] = len(items)
        punctuation = [0] * len(PUNCT)
        flags = [0] * len(PATTERNS)
        for key, value in items:
            if key.lower() not in ALLOW:
                numbers["ignored_fields_bucket"] += 1
                continue
            numbers["allowed_fields_bucket"] += 1
            if not isinstance(value, str):
                numbers["nonstring_values_bucket"] += 1
                continue
            if len(value) > MAX_VALUE:
                raise Limit()
            if PRIVATE.search(value) or PII.search(value):
                numbers["restricted_values_bucket"] += 1
                continue
            numbers["analyzed_values_bucket"] += 1
            for i, (_, c) in enumerate(PUNCT):
                punctuation[i] = min(3, punctuation[i] + value.count(c))
            for i, pattern in enumerate(PATTERNS.values()):
                flags[i] = int(bool(flags[i] or pattern.search(value)))
        result = _blank("OK", media)
        start = len(STATES) + len(MEDIA)
        result[start:] = [_bucket(numbers[k]) for k in COUNTS] + punctuation + flags
        return result
    except Limit:
        return _blank("RESOURCE_LIMIT", media)
    except (ValueError, UnicodeError, RecursionError, TypeError, OverflowError):
        return _blank("MALFORMED", media)
    except Exception:
        return _blank("EXTRACTION_ERROR", media)


def event(request_id, vector):
    result = {
        "schema_version": VERSION,
        "contract_sha256": CONTRACT_SHA256,
        "request_id": request_id,
        "features": vector,
    }
    validate_event(result)
    return result


def validate_event(value):
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "contract_sha256",
        "request_id",
        "features",
    }:
        raise ValueError("Body syntax event schema rejected")
    if (
        value["schema_version"] != VERSION
        or value["contract_sha256"] != CONTRACT_SHA256
        or not isinstance(value["request_id"], str)
        or not re.fullmatch(r"[a-f0-9]{32}", value["request_id"])
    ):
        raise ValueError("Body syntax event identity rejected")
    x = value["features"]
    if (
        not isinstance(x, list)
        or len(x) != len(COLUMNS)
        or any(type(v) is not int or not 0 <= v <= cap for v, cap in zip(x, MAXIMA))
    ):
        raise ValueError("Body syntax vector rejected")
    if sum(x[: len(STATES)]) != 1 or sum(x[len(STATES) : len(STATES) + len(MEDIA)]) != 1:
        raise ValueError("Body syntax state rejected")
    if state_of(x) != "OK" and any(x[len(STATES) + len(MEDIA) :]):
        raise ValueError("Body syntax unavailable signal rejected")

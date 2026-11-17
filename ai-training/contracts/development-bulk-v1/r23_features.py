"""Request-target shape extensions for URI76, with no literal n-grams."""

import re
from urllib.parse import unquote

import numpy as np

from idps_ai.data.privacy import PII, SENSITIVE
from idps_ai.features.request_view import PRIVATE_KEY

VERSION = "idps-request-time-uri76-shape-r23-v1"
BINS = 128
SYMBOLS = b"/=?&-_.:+*{}[]();!%,~"
ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
OPAQUE = re.compile(
    r"[0-9a-f]{16,}|[0-9]{9,}|(?=[a-zA-Z0-9_-]*[a-zA-Z])(?=[a-zA-Z0-9_-]*[0-9])[a-zA-Z0-9_-]{17,}"
)
LANES = {"structure": 24, "symbol_ngram": BINS}


def inspected(value):
    for _ in range(3):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    return value


def private(value, *, inspect_key=False):
    return bool(
        len(value) > 192
        or PII.search(value)
        or PRIVATE_KEY.search(value)
        or OPAQUE.fullmatch(value)
        or ESCAPE.search(value)
        or inspect_key
        and SENSITIVE.search(value)
    )


def collapse(value):
    """Map bytes to classes, retaining punctuation from a fixed alphabet."""
    out = bytearray()
    previous, run = 0, 0
    for c in value.encode("utf-8")[:192]:
        symbol = (
            65
            if 65 <= c <= 90
            else 97
            if 97 <= c <= 122
            else 48
            if 48 <= c <= 57
            else c
            if c in SYMBOLS
            else 63
        )
        run = run + 1 if previous == symbol else 1
        if run <= 4:
            out.append(symbol)
        previous = symbol
    return bytes(out)


def sketch(target):
    """Only screened bounded class tokens leave this boundary."""
    path, _, query = target.partition("?")
    segments = path.split("/")[1:]
    safe_path = []
    for segment in segments[:24]:
        text = inspected(segment)
        if private(text, inspect_key=True) or "@" in text:
            break
        safe_path.append(collapse(text))
    safe_query = []
    for field in query.split("&")[:32] if query else ():
        key, eq, value = field.partition("=")
        key, value = inspected(key), inspected(value)
        if private(key, inspect_key=True) or private(value) or "@" in key or "@" in value:
            continue
        safe_query.append(collapse(key) + (b"=" + collapse(value) if eq else b""))
    return b"/".join(safe_path)[:512], b"&".join(safe_query)[:512]


def describe_lane(value, split):
    items = value.split(split) if value else []
    lengths = [len(x) for x in items]
    return [
        bool(value),
        len(items),
        len(value),
        max(lengths, default=0),
        lengths[0] if lengths else 0,
        lengths[-1] if lengths else 0,
        value.count(b"0"),
        value.count(b"A"),
        value.count(b"a"),
        sum(c in SYMBOLS for c in value),
        value.count(b"?"),
        sum(a != b for a, b in zip(value, value[1:])),
    ]


def numeric(path, query):
    structure = np.minimum(31, describe_lane(path, b"/") + describe_lane(query, b"&")).astype(
        np.uint8
    )
    hist = bytearray(BINS)
    for lane, value in enumerate((path, query)):
        if not value:
            continue
        framed = b"^" + value + b"$"
        for width in (2, 3):
            for i in range(len(framed) - width + 1):
                code = 0x811C9DC5 ^ (17 * lane + width)
                for char in framed[i : i + width]:
                    code = ((code ^ char) * 0x01000193) & 0xFFFFFFFF
                bucket = code & (BINS - 1)
                if hist[bucket] < 15:
                    hist[bucket] += 1
    return structure, np.frombuffer(bytes(hist), dtype=np.uint8)


def project(target):
    return numeric(*sketch(target))

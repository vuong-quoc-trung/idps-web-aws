"""Two request-only feature hypotheses over a fixed, privacy-safe alphabet.

A = URI100 + contextual symbol n-grams. B = A + optional body/header observations.
No source/actor/status/label, literal hashes or learned vocabulary enter a vector.
"""

# isort: skip_file

import json
import re
from urllib.parse import unquote

import numpy as np
import r26_common  # noqa: F401 - initialize frozen-contract import path first.
from r23_features import describe_lane, sketch

from idps_ai.common import PipelineError
from idps_ai.data.privacy import PII, SENSITIVE
from idps_ai.features.request_time import from_request
from idps_ai.features.safe_content import PRIVATE, PUNCT, WORDS, _symbols

VERSION = "idps-causal-http-symbols-r26-v1"
URI_WIDTH, FULL_WIDTH, BINS = 164, 244, 64
VOCAB = tuple(sorted(WORDS | PUNCT | {"w", "n", "x", "P", "Q", "V", "B", "END"}))
TOKEN_ID = {token: index + 1 for index, token in enumerate(VOCAB)}
HEADER_NAMES = (
    "content-type",
    "content-length",
    "transfer-encoding",
    "accept",
    "user-agent",
    "accept-encoding",
    "connection",
    "referer",
    "origin",
    "host",
)
HEADER_PATTERN = re.compile(r"(?:^|[\r\n])\s*([A-Za-z-]{2,40})\s*:")


def header_names(headers):
    if headers.lstrip().startswith("{"):
        try:
            parsed = json.loads(headers)
        except (ValueError, RecursionError):
            return None
        if not isinstance(parsed, dict) or not all(
            isinstance(k, str) and re.fullmatch(r"[A-Za-z-]{2,40}", k) for k in parsed
        ):
            return None
        return {name.lower() for name in parsed}
    return {name.lower() for name in HEADER_PATTERN.findall(headers[:8192])}


def decode(value):
    for _ in range(2):
        changed = unquote(value)
        if changed == value:
            break
        value = changed
    return value


def uri_tokens(target):
    path, _, query = target.partition("?")
    tokens = ["P", *_symbols(path).split(), "Q"]
    for field in query.split("&")[:64] if query else ():
        key, _, value = field.partition("=")
        key, value = decode(key), decode(value)
        if PRIVATE.search(key) or SENSITIVE.search(key) or PII.search(key) or PII.search(value):
            continue
        tokens.extend(("V", *_symbols(value, 2048).split(), "END"))
    return tokens[:1024]


def histogram(tokens, lane):
    ids = [TOKEN_ID[t] for t in tokens]
    counts = np.zeros(BINS, np.uint8)
    for width in (1, 2, 3):
        for i in range(len(ids) - width + 1):
            value = 0x811C9DC5 ^ (lane * 17 + width)
            for token in ids[i : i + width]:
                value = ((value ^ token) * 0x01000193) & 0xFFFFFFFF
            bucket = value & (BINS - 1)
            if counts[bucket] < 31:
                counts[bucket] += 1
    return counts.astype(np.float32) / 31


def uri_extension(target):
    return histogram(uri_tokens(target), 0)


def content_extension(headers=None, body=None):
    if headers is not None and not isinstance(headers, str):
        raise PipelineError("Unsupported header observation type")
    if body is not None and not isinstance(body, str):
        raise PipelineError("Unsupported body observation type")
    values = np.zeros(16, np.float32)
    names = header_names(headers) if headers is not None else None
    if names is not None:
        values[0] = 1
        values[3:13] = [name in names for name in HEADER_NAMES]
        values[13] = min(16, sum(name in names for name in HEADER_NAMES)) / 16
    body_state = "missing"
    tokens = []
    if body is not None:
        # Preserve the existing full-body secret-key withholding policy. Privacy
        # diagnostics stay in metadata and never become a label or raw feature.
        if PRIVATE.search(decode(body[:65536])):
            body_state = "privacy_withheld"
        else:
            body_state = "truncated" if len(body) > 4096 else "observed"
            values[1] = 1
            values[2] = min(32, len(body) // 128) / 32
            values[14] = len(body) <= 4096
            values[15] = len(body) == 0
            tokens = ["B", *_symbols(body).split()]
    return np.r_[histogram(tokens, 1), values].astype(np.float32), {
        "headers_state": "missing"
        if headers is None
        else "malformed"
        if names is None
        else "observed",
        "body_state": body_state,
    }


def project(target, method, headers=None, body=None, *, base=None):
    prefix = from_request(target, method) if base is None else base
    lane = sketch(target)
    shape = np.minimum(31, describe_lane(lane[0], b"/") + describe_lane(lane[1], b"&"))
    extra, availability = content_extension(headers, body)
    result = np.r_[prefix, shape.astype(np.float32) / 31, uri_extension(target), extra].astype(
        np.float32
    )
    if result.shape != (FULL_WIDTH,) or not np.isfinite(result).all():
        raise PipelineError("Invalid R26 projection")
    return result, availability


def schema():
    return {
        "version": VERSION,
        "dtype": "float32",
        "width_uri": URI_WIDTH,
        "width_full": FULL_WIDTH,
        "ordering": "URI76, R23 shape24, URI64, BODY64, HEADER_AND_AVAILABILITY16",
        "histogram": {
            "hash": "FNV1a32",
            "bins": BINS,
            "token_widths": [1, 2, 3],
            "cap_and_scale": 31,
        },
        "vocabulary": VOCAB,
        "header_names": HEADER_NAMES,
        "missing_content": "All body/header cells zero with observed masks zero; observed empty has body observed=1, empty=1",
        "body_privacy": "Whole body withheld on existing secret-key families; only finite alphabet and bucketed length retained",
        "raw_target_or_payload_persisted": False,
        "runtime_profile": "Request-only. HTTP_FULL requires independently observed content before cutoff; URI-only views are auxiliary views of the same original.",
    }

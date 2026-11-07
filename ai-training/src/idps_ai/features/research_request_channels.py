"""Isolated research encoder; frozen Request v2 contracts remain untouched.

76 fixed numeric dimensions + independently normalized 256 URI / 192 body /
64 header features. No fit, response, source, session, clock or label input.
"""

import json
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from idps_ai.data.privacy import PII
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import project_request
from idps_ai.features.rich_content_v2 import rich_request_v2
from idps_ai.features.safe_content import PRIVATE

HEADER_ALLOW = frozenset(
    ["accept", "accept-encoding", "content-type", "user-agent", "transfer-encoding"]
)
IDENTITY = frozenset(["email", "username"])


def clean_fields(items):
    out = {}
    for key, value in list(items)[:32]:
        key = str(key)
        if PRIVATE.search(key) and key.lower() not in IDENTITY:
            continue
        if key.lower() in IDENTITY and (not isinstance(value, str) or PII.search(value)):
            value = "identity withheld"
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
    return out


def sanitize(request):
    url = urlsplit(request["url"])
    fields = clean_fields(parse_qsl(url.query, keep_blank_values=True))
    target = urlunsplit(("", "", url.path, urlencode(fields), ""))
    raw_body = request.get("body")
    if raw_body is None:
        body = None
    elif not raw_body:
        body = ""
    else:
        try:
            value = json.loads(raw_body) if len(raw_body) <= 8192 else None
        except ValueError:
            value = None
        if isinstance(value, dict):
            # Drop secret values before any length/entropy or syntax measurement.
            body = json.dumps(clean_fields(value.items()), sort_keys=True)
        elif "=" in raw_body:
            body = urlencode(clean_fields(parse_qsl(raw_body, keep_blank_values=True)))
        else:
            body = (
                "withheld" if PRIVATE.search(raw_body) or PII.search(raw_body) else raw_body[:4096]
            )
    raw_headers = request.get("headers")
    headers = (
        None
        if raw_headers is None
        else "\r\n".join(
            line
            for line in raw_headers.splitlines()
            if line.partition(":")[0].strip().lower() in HEADER_ALLOW
        )
    )
    return target, body, headers


@lru_cache
def hasher(width):
    return HashingVectorizer(
        n_features=width,
        analyzer="char",
        ngram_range=(3, 5),
        alternate_sign=False,
        norm="l2",
        lowercase=False,
    )


def encode(request):
    target, body, headers = sanitize(request)
    method = request["method"]
    numeric = encode_request(bounded_spec(), project_request(target, method)["numbers"])
    uri, _ = rich_request_v2(method, target, None, None)
    body_symbols, _ = rich_request_v2("OTHER", "/", None, body)
    header_symbols, _ = rich_request_v2("OTHER", "/", headers, None)
    channels = [
        "URI present " + uri,
        ("BODY missing " if body is None else "BODY present ") + body_symbols,
        ("HEADERS missing " if headers is None else "HEADERS present ") + header_symbols,
    ]
    result = np.concatenate(
        [
            numeric,
            *[
                hasher(width).transform([text]).toarray().astype(np.float32)[0]
                for width, text in zip([256, 192, 64], channels, strict=True)
            ],
        ]
    )
    if result.shape != (588,) or not np.isfinite(result).all():
        raise ValueError("Research channel feature contract failure")
    return result

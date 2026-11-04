"""Additional privacy-bounded JSON-body syntax for lab request research v2."""

from __future__ import annotations

import json

from idps_ai.data.privacy import PII
from idps_ai.features.rich_content import _bucket, _entropy_bucket, _syntax, rich_request
from idps_ai.features.safe_content import PRIVATE


def rich_request_v2(method, url, headers, body):
    """Return v1 view plus coarse, field-aware JSON syntax; never raw secrets.

    The v1 contract is left intact for frozen WAF checkpoints. This extension
    only measures whether body structure could resolve observed lab collisions.
    """
    base, availability = rich_request(method, url, headers, body)
    if not body:
        return base + " jsonbody absent", availability | {"json_body_profile": False}
    try:
        parsed = json.loads(body[:8193]) if len(body) <= 8192 else None
    except (ValueError, UnicodeDecodeError):
        parsed = None
    if not isinstance(parsed, dict):
        return base + " jsonbody unavailable", availability | {"json_body_profile": False}
    parts = [base, "jsonbody", "fields", _bucket(len(parsed))]
    for key, value in sorted(parsed.items())[:32]:
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool, type(None))):
            parts.append("field unsupported")
            continue
        lower = key.lower()
        if (
            lower
            in {
                "password",
                "passwd",
                "token",
                "authorization",
                "cookie",
                "secret",
                "api_key",
                "csrf",
                "otp",
            }
            or PRIVATE.search(lower)
            and lower not in {"email", "username"}
        ):
            parts.append("field secret redacted")
            continue
        text = str(value)
        if lower in {"email", "username"}:
            if PII.search(text) or PRIVATE.search(text):
                parts.append("field identity redacted")
            else:
                parts.extend(
                    (
                        "field identity syntax",
                        _syntax(text, 512),
                        "length",
                        _bucket(len(text)),
                        "entropy",
                        _entropy_bucket(text),
                    )
                )
            continue
        if PII.search(text) or PRIVATE.search(text):
            parts.append("field redacted")
        else:
            parts.extend(
                (
                    "field other",
                    _syntax(key, 128),
                    "syntax",
                    _syntax(text, 512),
                    "length",
                    _bucket(len(text)),
                )
            )
    return " ".join(parts), availability | {"json_body_profile": True}

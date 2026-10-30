"""Separate, application-neutral numeric request profile. Legacy v5 is untouched.

Only URI/query structure and method enter the model. Parameter names are replaced
by equality-preserving aliases, credentials/PII are removed before statistics,
and masking diagnostics stay out of model input. No actor/status/flow or clock.
"""

import math
import re
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

from idps_ai.common import PipelineError, digest, file_sha256
from idps_ai.data.privacy import METHODS, PII, SENSITIVE, request_numbers
from idps_ai.data.structure import safe_components, structure_numbers

PROFILE = "request-structure-v1"
PRIVATE_KEY = re.compile(
    r"(?:pwd|passphrase|credential|api.?key|access.?key|jwt|bearer|ticket|signature|private.?key|^pin$|^pass$|^auth$)",
    re.I,
)
EXCLUDED = {
    "uri_length",
    "path_depth",
    "uri_api_ratio",
    "object_identity_available",
    "query_original_available",
}


def _decode(text):
    text = text.replace("+", " ")
    for _ in range(3):
        changed = unquote(text)
        if changed == text:
            return text
        text = changed
    return text


def project_request(target, method="GET", _agent=None):
    if not isinstance(target, str) or len(target) > 8192:
        raise PipelineError("Missing/oversized request URI")
    try:
        parsed = urlsplit(target)
    except ValueError:
        raise PipelineError("Invalid request URI; raw value omitted") from None
    path, _ = safe_components(parsed.path, "")
    # Broader credential aliases and encoded PII in path must also be removed.
    for i, segment in enumerate(path.split("/")):
        inspected = _decode(segment)
        if PII.search(inspected) or PRIVATE_KEY.search(inspected):
            path = "/".join(path.split("/")[:i])
            break
    aliases, fields, dropped = {}, [], 0
    original = parsed.query.split("&") if parsed.query else []
    for field in original[:64]:
        key, _, value = field.partition("=")
        inspected_key, inspected_value = _decode(key).lower(), _decode(value)
        if (
            SENSITIVE.search(inspected_key)
            or PRIVATE_KEY.search(inspected_key)
            or PII.search(inspected_key)
            or PII.search(inspected_value)
            or "[redacted]" in inspected_value.lower()
            or re.search(r"%[0-9a-f]{2}", inspected_key, re.I)
        ):
            dropped += 1
            continue
        alias = aliases.setdefault(inspected_key, "field" + str(len(aliases)))
        fields.append(alias + "=" + value)
    query = "&".join(fields)
    values = {
        **request_numbers(
            path, None if parsed.query and not fields else query, decoded_operators=True
        ),
        **structure_numbers(path, query),
    }
    values = {
        k: float(v)
        for k, v in values.items()
        if k not in EXCLUDED and not k.startswith("query_original_")
    }
    method = method if method in METHODS else "OTHER"
    values.update({"method_" + m: float(method == m) for m in METHODS})
    return {
        "profile": PROFILE,
        "implementation_sha256": fingerprint(),
        "numbers": values,
        "availability": {
            "dropped_fields": dropped,
            "field_limit_exceeded": len(original) > 64,
            "visible_fields": len(fields),
            "body_observed": False,
            "path_filtered": path != parsed.path,
        },
    }


@cache
def columns():
    return tuple(sorted(project_request("/")["numbers"]))


@cache
def fingerprint():
    root = Path(__file__).resolve().parents[1]
    return digest(
        {
            str(p.relative_to(root)): file_sha256(p)
            for p in (Path(__file__), root / "data/privacy.py", root / "data/structure.py")
        }
    )


def validate_numbers(numbers):
    if set(numbers) != set(columns()):
        raise PipelineError("Request profile/feature contract mismatch")
    if any(
        isinstance(x, bool)
        or not isinstance(x, (int, float))
        or not math.isfinite(x)
        or not 0 <= x <= 1e6
        for x in numbers.values()
    ):
        raise PipelineError("Invalid numeric request projection")
    return numbers


def validate_view(value):
    if value.get("profile") != PROFILE or value.get("implementation_sha256") != fingerprint():
        raise PipelineError("Request projection profile/implementation mismatch")
    return validate_numbers(value.get("numbers", {}))

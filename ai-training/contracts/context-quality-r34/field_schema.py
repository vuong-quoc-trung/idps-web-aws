"""Public field-role and value-type relationships; no free-text tokens, keys or IDs in output."""

import json
import math
import re
from collections import Counter
from urllib.parse import unquote, unquote_plus

ROLES = {
    "number": {
        "id",
        "page",
        "offset",
        "limit",
        "count",
        "size",
        "start",
        "length",
        "quantity",
        "year",
        "per_page",
        "pagesize",
        "max",
        "min",
    },
    "boolean": {
        "enabled",
        "active",
        "visible",
        "published",
        "descending",
        "ascending",
        "reverse",
        "include",
        "debug",
    },
    "choice": {
        "sort",
        "order",
        "direction",
        "format",
        "type",
        "mode",
        "lang",
        "language",
        "view",
        "category",
        "action",
    },
    "text": {
        "q",
        "query",
        "search",
        "filter",
        "keyword",
        "term",
        "title",
        "name",
        "description",
        "message",
        "comment",
        "text",
        "content",
    },
    "collection": {"tags", "fields", "columns", "items", "values", "categories", "ids", "list"},
    "date": {"date", "from", "to", "since", "until", "before", "after", "end_date", "start_date"},
}
LOOKUP = {k: r for r, keys in ROLES.items() for k in keys}
KINDS = (
    "empty",
    "integer",
    "decimal",
    "boolean",
    "date",
    "word",
    "text",
    "structured",
    "array",
    "object",
    "null",
)
EXPECTED = {
    "number": {"integer", "decimal"},
    "boolean": {"boolean", "integer"},
    "choice": {"word", "integer"},
    "text": {"word", "text", "empty", "integer", "date"},
    "collection": {"array", "word", "text", "integer"},
    "date": {"date", "integer"},
}
FEATURES = tuple(
    f"{lane}.{key}"
    for lane in ("query", "body")
    for key in [
        *(f"{role}.{kind}" for role in ROLES for kind in KINDS),
        "duplicate",
        "mixed_type_same_field",
        "mismatched",
        "nested",
        "repeated_role",
    ]
)
WIDTH = len(FEATURES) // 2
SENSITIVE = re.compile(
    r"password|passwd|secret|token|cookie|authorization|session|csrf|otp|api.?key|bearer|email|username|phone|address|cccd|(?:^|\W)(?:pin|auth|pass)(?:$|\W)|@|[a-f0-9]{16,}|\d{9,}|[A-Za-z0-9_-]{24,}|%[a-fA-F0-9]{2}",
    re.I,
)
ALLOWED = re.compile(r"[a-z][a-z0-9_]{0,24}\Z")
PRIVATE_STATE = "WITHHELD_OR_UNSUPPORTED"


class ObjectPairs(list):
    pass


def decode(s):
    for _ in range(3):
        new = unquote_plus(s) if _ == 0 else unquote(s)
        if new == s:
            break
        s = new
    return s


def value_type(v):
    if isinstance(v, ObjectPairs):
        return "object"
    if isinstance(v, list):
        return "array"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return None if abs(v) >= 10**8 else "integer"
    if isinstance(v, float):
        return "decimal" if math.isfinite(v) and abs(v) < 10**8 else None
    if not isinstance(v, str) or len(v) > 256 or SENSITIVE.search(v):
        return None
    s = v.strip()
    if not s:
        return "empty"
    if s.lower() in ("true", "false"):
        return "boolean"
    if re.fullmatch(r"[+-]?\d{1,8}", s):
        return "integer"
    if re.fullmatch(r"[+-]?\d{1,8}\.\d{1,6}", s):
        return "decimal"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?", s):
        return "date"
    if re.fullmatch(r"[\w.-]{1,48}", s):
        return "word"
    if re.fullmatch(r"[\w .,-]+", s):
        return "text"
    return "structured"


def pairs(s, body):
    if not s or len(s) > 4096:
        return ()
    if body and s.lstrip().startswith(("{", "[")):
        try:
            obj = json.loads(s, object_pairs_hook=ObjectPairs)
        except (ValueError, RecursionError):
            return ()
        return obj if isinstance(obj, ObjectPairs) and len(obj) <= 32 else ()
    fields = s.split("&")
    if len(fields) > 32:
        return ()
    result = []
    for field in fields:
        key, sep, val = field.partition("=")
        if sep:
            result.append((decode(key), decode(val)))
    return result


def lane(s, body):
    values = [0] * WIDTH
    seen = {}
    count = Counter()
    for key, value in pairs(s, body):
        key = key.lower()
        if not ALLOWED.fullmatch(key) or key not in LOOKUP:
            continue
        kind = value_type(value)
        if kind is None:
            continue
        # Nested values are opaque. Only the public outer field's container type is observed.
        role = LOOKUP[key]
        offset = list(ROLES).index(role) * len(KINDS) + KINDS.index(kind)
        values[offset] += 1
        values[-5] += int(key in seen)
        values[-4] += int(key in seen and seen[key] != kind)
        values[-3] += int(kind not in EXPECTED[role])
        values[-2] += int(kind in ("array", "object"))
        values[-1] += int(count[role] > 0)
        seen[key] = kind
        count[role] += 1
    return [min(v, 4) for v in values]


def project(target, body):
    query = lane(target.partition("?")[2], False)
    return query + (lane(body, True) if isinstance(body, str) else [0] * WIDTH)

"""Bounded numeric URI/query structure; strings never leave the projection."""

import math
import re
from urllib.parse import unquote

from idps_ai.data.privacy import PII, SENSITIVE

SAFE_KEYS = frozenset(
    "q search query filter page size sort limit offset id status role from to".split()
)


def decoded(value):
    return unquote(unquote(value.replace("+", " ")))


def safe_components(path, query):
    path = path[:8192]
    parts = path.split("/")
    for i, part in enumerate(parts):
        inspected = decoded(part)
        if (
            PII.search(inspected)
            or "[redacted]" in inspected.lower()
            or (
                SENSITIVE.search(inspected)
                and (
                    i < len(parts) - 1
                    or any(SENSITIVE.search(s) for s in re.split(r"[/\\]", inspected)[:-1])
                )
            )
        ):
            path = "/".join(parts[:i])
            break
    fields = []
    for field in query[:8192].split("&")[:64]:
        key, _, value = field.partition("=")
        key = decoded(key).lower()
        if key not in SAFE_KEYS or SENSITIVE.search(key):
            continue
        if PII.search(decoded(value)) or "[redacted]" in decoded(value).lower():
            continue
        fields.append(key + "=" + value)
    return path, "&".join(fields)


def structure_numbers(path, query):
    raw = path + "?" + query
    once = unquote(raw.replace("+", " "))
    twice = unquote(once)
    lower = twice.lower()
    values = [decoded(f.partition("=")[2]) for f in query.split("&") if f]
    keys = [f.partition("=")[0] for f in query.split("&") if f]
    lengths = [len(v) for v in values]
    n = max(len(twice), 1)
    parens = max_depth = 0
    for char in twice:
        parens = max(0, parens + (1 if char == "(" else -1 if char == ")" else 0))
        max_depth = max(max_depth, parens)
    result = {
        "structure_available": 1.0,
        "decoded_uri_length": float(len(twice)),
        "decoded_query_length": float(len(decoded(query))),
        "encoding_rounds": float((once != raw) + (twice != once)),
        "percent_escape_count": float(len(re.findall(r"%[0-9a-fA-F]{2}", raw))),
        "invalid_escape_count": float(len(re.findall(r"%(?![0-9a-fA-F]{2})", raw))),
        "encoding_contraction_ratio": max(0.0, (len(raw) - len(twice)) / max(len(raw), 1)),
        "non_ascii_ratio": sum(ord(c) > 127 for c in twice) / n,
        "uppercase_ratio": sum(c.isupper() for c in twice) / n,
        "whitespace_ratio": sum(c.isspace() for c in twice) / n,
        "max_parameter_length": float(max(lengths, default=0)),
        "mean_parameter_length": sum(lengths) / max(len(lengths), 1),
        "parameter_length_std": math.sqrt(
            sum((v - sum(lengths) / len(lengths)) ** 2 for v in lengths) / len(lengths)
        )
        if lengths
        else 0.0,
        "duplicate_parameter_count": float(len(keys) - len(set(keys))),
        "empty_parameter_count": float(sum(not v for v in values)),
        "numeric_parameter_ratio": sum(v.isnumeric() for v in values) / max(len(values), 1),
        "sql_comment_open_count": float(lower.count("/*")),
        "sql_comment_close_count": float(lower.count("*/")),
        "sql_line_comment_count": float(lower.count("--")),
        "comparison_operator_count": float(
            len(re.findall(r"(?:!=|<>|<=|>=|=|<|>)", " ".join(values)))
        ),
        "boolean_operator_count": float(len(re.findall(r"\b(?:or|and|not)\b", lower))),
        "comma_count": float(twice.count(",")),
        "parenthesis_open_count": float(twice.count("(")),
        "parenthesis_close_count": float(twice.count(")")),
        "parenthesis_max_depth": float(max_depth),
        "html_tag_open_count": float(len(re.findall(r"<\s*[a-z]", lower))),
        "html_tag_close_count": float(lower.count("</")),
        "html_entity_count": float(len(re.findall(r"&(?:#x?[0-9a-f]+|[a-z]+);", lower))),
        "event_assignment_count": float(len(re.findall(r"\bon[a-z]+\s*=", lower))),
        "uri_scheme_count": float(len(re.findall(r"\b[a-z]+:", lower))),
        "path_parent_segment_count": float(lower.count("../") + lower.count("..\\")),
        "path_dot_segment_count": float(lower.count("./")),
        "backslash_count": float(twice.count("\\")),
        "slash_count": float(twice.count("/")),
        "dot_count": float(twice.count(".")),
        "shell_and_count": float(lower.count("&&")),
        "shell_or_count": float(lower.count("||")),
        "shell_substitution_count": float(lower.count("$(")),
        "backtick_count": float(twice.count("`")),
        "newline_count": float(twice.count("\n")),
        "null_byte_count": float(twice.count("\x00")),
    }
    return result


STRUCTURE_KEYS = frozenset(structure_numbers("/", ""))

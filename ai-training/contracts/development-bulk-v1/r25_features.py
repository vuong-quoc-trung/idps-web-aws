"""Finite allowlisted lexical indicators after the existing privacy boundary.

No learned vocabulary, literal hashes, body, headers, identity or response fields.
This is a research candidate. Missing raw method/target is unsupported.
"""

import re
import numpy as np
from r23_features import inspected, private

VERSION = "idps-uri100-lexical32-r25-v1"
SPECS = (
    ("sql_select", r"\bselect\b"),
    ("sql_union", r"\bunion\b"),
    ("sql_from", r"\bfrom\b"),
    ("sql_where", r"\bwhere\b"),
    ("sql_or", r"\bor\b"),
    ("sql_and", r"\band\b"),
    ("sql_insert_update", r"\b(?:insert|update|delete|drop)\b"),
    ("sql_exec", r"\b(?:exec|execute|xp_cmdshell)\b"),
    ("sql_delay", r"\b(?:sleep|benchmark|waitfor)\b"),
    ("sql_comment", r"--|/\*|\*/"),
    ("sql_function", r"\b(?:concat|char|ascii|substring|extractvalue)\s*\("),
    ("sql_metadata", r"\b(?:information_schema|sysobjects|version|database)\b"),
    ("tag_script", r"<\s*/?\s*script\b"),
    ("tag_html", r"<\s*(?:img|svg|iframe|object|body)\b"),
    ("script_scheme", r"(?:javascript|vbscript)\s*:"),
    ("html_event", r"\bon(?:error|load|click|focus|mouseover)\s*="),
    ("script_call", r"\b(?:alert|prompt|confirm|eval)\s*\("),
    ("html_entity", r"&#(?:x[0-9a-f]+|[0-9]+);?"),
    ("parent_segment", r"(?:^|[/\\])\.\.(?:[/\\]|$)"),
    ("posix_system", r"/(?:etc|proc|bin|dev)/(?:passwd|shadow|self|sh|bash|null)\b"),
    ("windows_system", r"\b(?:win\.ini|boot\.ini|windows[/\\]|system32)"),
    ("shell_word", r"\b(?:wget|curl|whoami|chmod|bash|powershell|cmd\.exe)\b"),
    ("shell_substitution", r"\$\(|`"),
    ("xml_entity", r"<!\s*(?:doctype|entity)\b"),
    ("template_expression", r"\{\{|\$\{|#\{"),
    ("php_expression", r"<\?php|\b(?:phpinfo|base64_decode|system)\s*\("),
    ("archive_extension", r"\.(?:zip|tar|gz|bak|old)(?:$|[?&/])"),
    ("script_extension", r"\.(?:php|asp|aspx|jsp|cgi)(?:$|[?&/])"),
    ("admin_route", r"(?:^|/)(?:admin|administrator|wp-admin)(?:/|$)"),
    ("protocol_url", r"\b(?:https?|ftp|file|gopher)://"),
    ("boolean_comparison", r"\b[0-9]{1,5}\s*[=<>]\s*[0-9]{1,5}\b"),
    ("null_escape", r"%00|\x00"),
)
PATTERNS = tuple(re.compile(p, re.I | re.ASCII) for _, p in SPECS)


def screened(target):
    path, _, query = target.partition("?")
    safe = []
    for part in path.split("/")[1:25]:
        part = inspected(part)
        if private(part, inspect_key=True) or "@" in part:
            break
        safe.append(part)
    fields = []
    for field in query.split("&")[:32] if query else ():
        key, eq, value = field.partition("=")
        key, value = inspected(key), inspected(value)
        if private(key, inspect_key=True) or private(value) or "@" in key or "@" in value:
            continue
        # Field names are excluded to prevent account or token-key shortcuts.
        if eq:
            fields.append(value)
    return "/" + "/".join(safe), "&".join(fields)


def lexical(target):
    lanes = screened(target)
    return np.array([any(p.search(s) is not None for s in lanes) for p in PATTERNS], np.uint8)

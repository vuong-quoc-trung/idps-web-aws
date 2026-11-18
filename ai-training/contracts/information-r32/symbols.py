"""Binary symbolic features with an exact address per HTTP field and adjacent token pair."""

import re
from urllib.parse import unquote

from idps_ai.data.privacy import PII, SENSITIVE
from idps_ai.features.request_view import PRIVATE_KEY
from idps_ai.features.safe_content import PARTS, PRIVATE, PUNCT, WORDS

ALPHABET = tuple(sorted(WORDS | PUNCT | {"<word>", "<number>", "<other>", "<start>", "<end>"}))
TOKEN = {word: index for index, word in enumerate(ALPHABET)}
N = len(TOKEN)
STRIDE = N + N * N
BODY_START = 2 * STRIDE
WIDTH = 3 * STRIDE


def decoded(value):
    for _ in range(3):
        new = unquote(value)
        if new == value:
            break
        value = new
    return value


RESIDUAL_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
OPAQUE = re.compile(
    r"(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{17,}|[a-fA-F0-9]{16,}"
)


def sensitive(value):
    return any(
        pattern.search(value)
        for pattern in (PII, SENSITIVE, PRIVATE, PRIVATE_KEY, RESIDUAL_ESCAPE, OPAQUE)
    )


def add_part(columns, value, lane):
    if not value:
        return
    offset = lane * STRIDE
    previous = TOKEN["<start>"]
    for index, match in enumerate(PARTS.finditer(value)):
        if index == 256:
            break
        value_token = match.group(0).lower()
        if value_token in WORDS or value_token in PUNCT:
            word = value_token
        elif value_token[0].isalpha() or value_token.startswith("_"):
            word = "<word>"
        elif value_token[0].isdigit():
            word = "<number>"
        else:
            word = "<other>"
        current = TOKEN[word]
        columns.add(offset + current)
        columns.add(offset + N + previous * N + current)
        previous = current
    if previous != TOKEN["<start>"]:
        columns.add(offset + N + previous * N + TOKEN["<end>"])


def project(target, body):
    # Only finite-alphabet column IDs leave this function. No bins for absence,
    # source, length of withheld content, headers, host, keys, identity or outcome.
    columns = set()
    path, _, query = target.partition("?")
    for part in path.split("/")[1:25]:
        value = decoded(part)
        if len(value) > 192 or sensitive(value) or "@" in value:
            break
        add_part(columns, value, 0)
    for field in query.split("&")[:32]:
        key, _, raw = field.partition("=")
        key, value = decoded(key), decoded(raw)
        if len(value) <= 256 and not sensitive(key) and not sensitive(value) and "@" not in value:
            add_part(columns, value, 1)
    if isinstance(body, str) and 0 < len(body) <= 4096:
        value = decoded(body)
        if (
            not sensitive(value)
            and not re.search(r"(?i)(?<![a-z0-9])(?:pin|pass|auth)(?![a-z0-9])", value)
            and "@" not in value
        ):
            add_part(columns, value, 2)
    return sorted(columns)

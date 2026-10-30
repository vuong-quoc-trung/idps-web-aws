"""Opt-in numeric-only HTTP query telemetry, shared by offline and live EVE bridges.

This is an AI adapter extension, not a change to canonical event schema v1.
Raw URLs/headers exist only during projection. No rule result or identity is input.
"""

import json
import math
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from idps_ai.common import PipelineError
from idps_ai.data.privacy import request_numbers
from idps_ai.data.structure import STRUCTURE_KEYS, safe_components, structure_numbers

PROFILE = "safe_query_numeric_v1"
PROFILE_V2 = "safe_query_numeric_v2"
CAUSAL_PROFILES = ("edge_masked_v1", PROFILE, PROFILE_V2)
NUMERIC_KEYS = frozenset(request_numbers(None, None))


def project_query(url, version=1):
    if not isinstance(url, str) or len(url) > 8192:
        raise PipelineError("Missing or oversized HTTP URI for numeric projection")
    parsed = urlsplit(url)
    if version == 2:
        path, query = safe_components(parsed.path, parsed.query)
        return {
            "version": 2,
            "numbers": {
                **request_numbers(
                    path, None if parsed.query and not query else query, decoded_operators=True
                ),
                **structure_numbers(path, query),
            },
        }
    if version != 1:
        raise PipelineError("Unsupported query projection version")
    return {
        "version": 1,
        "numbers": request_numbers(parsed.path, parsed.query, decoded_operators=True),
    }


def validate_projection(value, version=1):
    if not isinstance(value, dict) or set(value) != {"version", "numbers"}:
        raise PipelineError("Invalid numeric query envelope")
    numbers = value["numbers"]
    expected = NUMERIC_KEYS | STRUCTURE_KEYS if version == 2 else NUMERIC_KEYS
    if (
        version not in (1, 2)
        or value["version"] != version
        or not isinstance(numbers, dict)
        or set(numbers) != expected
    ):
        raise PipelineError("Unsupported numeric query contract")
    for name, number in numbers.items():
        if (
            not isinstance(number, (float, int))
            or isinstance(number, bool)
            or not math.isfinite(number)
            or not 0 <= number <= 1e6
            or (name.endswith("_available") and number not in (0, 1))
        ):
            raise PipelineError("Invalid numeric query value")
    return {name: float(number) for name, number in numbers.items()}


def project_stream(source, destination, version=1):
    from idps_ai.data.sensor_decode import redact_eve

    count = 0
    while line := source.readline(65537):
        if len(line) > 65536 or not line.endswith(b"\n"):
            raise PipelineError("Oversized or partial EVE record")
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError
            safe = redact_eve(value, query_numeric=True, query_version=version)
            destination.write(json.dumps(safe, allow_nan=False, separators=(",", ":")) + "\n")
            destination.flush()
        except (ValueError, TypeError, KeyError, OverflowError):
            raise PipelineError("Invalid EVE projection input; raw record omitted") from None
        count += 1
    return count


def project_file(source, output, version=1):
    from contextlib import nullcontext

    from idps_ai.data.snapshot import new_destination

    with nullcontext(sys.stdin.buffer) if source == "-" else Path(source).open("rb") as stream:
        if output == "-":
            return {
                "records": project_stream(stream, sys.stdout, version),
                "profile": PROFILE_V2 if version == 2 else PROFILE,
            }
        target = new_destination(output)
        with tempfile.TemporaryDirectory(prefix=".project-eve-", dir=target.parent) as temporary:
            candidate = Path(temporary) / "eve.json"
            with candidate.open("w") as dest:
                candidate.chmod(0o600)
                count = project_stream(stream, dest, version)
                os.fsync(dest.fileno())
            os.replace(candidate, target)
        return {
            "records": count,
            "profile": PROFILE_V2 if version == 2 else PROFILE,
            "output": str(target),
        }

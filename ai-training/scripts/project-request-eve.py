#!/usr/bin/env python3
"""Opt-in bounded pre-redaction EVE bridge. No service/Web configuration writes."""

import json
import sys

from idps_ai.data.sensor_decode import redact_eve


def main():
    while line := sys.stdin.buffer.readline(65537):
        if len(line) > 65536 or not line.endswith(b"\n"):
            raise ValueError("oversized/partial EVE")
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError("invalid EVE object")
        value = redact_eve(raw, query_numeric=True, query_version=2, request_structure=True)
        sys.stdout.write(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, TypeError, KeyError, OverflowError):
        sys.stderr.write("EVE request projection failed; raw record omitted\n")
        raise SystemExit(2)

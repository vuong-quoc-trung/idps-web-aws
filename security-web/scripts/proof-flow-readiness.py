"""Read back the old decrypted NGINX leg during a planned, drained sensor rotation."""

import argparse
import ipaddress
import json
from pathlib import Path
import sys
import time


def endpoint(field):
    raw, port = field.split(":")
    return str(ipaddress.IPv4Address(int(raw, 16).to_bytes(4, sys.byteorder))), int(
        port, 16
    )


def established(lines):
    flows = set()
    for line in lines[1:]:
        fields = line.split()
        if fields[3] != "01":
            continue
        source, dest = endpoint(fields[1]), endpoint(fields[2])
        if source[0] == "127.77.0.1" and dest == ("127.77.0.2", 18080):
            flows.add((source, dest, fields[9]))
    return flows


def current():
    return established(Path("/proc/self/net/tcp").read_text().splitlines())


def wait_for_rotation(old, timeout):
    if not 0 < timeout <= 30:
        raise ValueError("Rotation deadline must be within 30 seconds")
    start = time.monotonic()
    while old & current():
        if time.monotonic() - start >= timeout:
            raise TimeoutError("Previous proof-leg connection is still established")
        time.sleep(0.025)
    return dict(
        old_connections=len(old),
        remaining_old_connections=0,
        old_flow_drain_ms=round((time.monotonic() - start) * 1000, 3),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--timeout", type=float, default=5)
    args = p.parse_args()
    print(json.dumps(wait_for_rotation(current(), args.timeout)))

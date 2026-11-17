"""Generate opt-in mirror includes for an existing worker-owned Local site."""

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "request-time-v1"


def render(output, mirror_socket):
    if not re.fullmatch(r"/[a-zA-Z0-9/_.-]+", str(mirror_socket)):
        raise ValueError("Unsupported socket path for NGINX include")
    output.mkdir(mode=0o700, exist_ok=True)
    server = (
        (HERE / "server-location.conf")
        .read_text()
        .replace("__PRIVATE_SOCKET__", str(mirror_socket))
    )
    server = server.replace(
        "proxy_set_header X-IDPS-Dispatch-Ms $msec;",
        "proxy_set_header X-IDPS-Dispatch-Ms $idps_local_dispatch_ms;",
    )
    proxy = "set $idps_local_dispatch_ms $msec;\n" + (HERE / "proxy-location.conf").read_text()
    for name, text in (("r22-server.conf", server), ("r22-proxy.conf", proxy)):
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runtime_config", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    render(args.output, Path(json.loads(args.runtime_config.read_text())["mirror_socket"]))

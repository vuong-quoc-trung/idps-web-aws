"""Manual actuator for a single EC2-owned peer on an isolated ingress interface."""

import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import struct
import subprocess
import sys

EDGE, PEER_IF, NS = "ws-c2-edge", "ws-c2-peer", "ws-c2-peer"
SERVER, PEER = "10.254.63.1", "10.254.63.2"
TABLE = "ws_aws_prevention"
SET = ("inet", TABLE, "blocked_ips")
RUNTIME = Path("/run/websentinel-aws-prevention")
SCOPE = RUNTIME / "scope.json"
SOCKET = RUNTIME / "actuator.sock"
RULES = f'''create table inet {TABLE}
table inet {TABLE} {{
  set blocked_ips {{ type ipv4_addr; flags timeout; }}
  chain input {{
    type filter hook input priority filter; policy accept;
    iifname "{EDGE}" ip saddr {PEER} ip daddr {SERVER} tcp dport 443 ip saddr @blocked_ips counter drop
    iifname "{EDGE}" ip saddr {PEER} ip daddr {SERVER} tcp dport 443 accept
    iifname "{EDGE}" drop
  }}
  chain forward {{
    type filter hook forward priority filter; policy accept;
    iifname "{EDGE}" drop
    oifname "{EDGE}" drop
  }}
}}
'''


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, timeout=4, **kwargs)


def ip(*args):
    return json.loads(run("ip", "-j", "-4", *args))


def nft(*args, **kwargs):
    return run("nft", *args, **kwargs)


def fingerprint():
    return hashlib.sha256(nft("-st", "list", "table", "inet", TABLE).encode()).hexdigest()


def identity(*, verify_peer=False):
    routes = ip("route", "get", PEER)
    links = json.loads(run("ip", "-j", "-d", "link", "show", "dev", EDGE))
    if (len(routes) != 1 or routes[0].get("dev") != EDGE or routes[0].get("prefsrc") != SERVER
            or routes[0].get("gateway") or len(links) != 1
            or links[0].get("linkinfo", {}).get("info_kind") != "veth"):
        raise ValueError("Ingress route or interface differs")
    namespace = os.stat(f"/run/netns/{NS}").st_ino
    host = os.stat("/proc/self/ns/net").st_ino
    fingerprint = [links[0]["ifindex"], links[0]["link_index"], host, namespace]
    if not verify_peer:
        return fingerprint
    if host != os.stat("/proc/1/ns/net").st_ino:
        raise ValueError("Setup must run in the host network namespace")
    peer = json.loads(run("ip", "-n", NS, "-j", "-d", "address", "show"))
    devices = [dev for dev in peer if dev["ifname"] != "lo"]
    if len(devices) != 1 or devices[0]["ifname"] != PEER_IF:
        raise ValueError("Unexpected interfaces in peer namespace")
    peer_link = devices[0]
    if (peer_link["ifindex"] != links[0].get("link_index")
            or peer_link.get("link_index") != links[0]["ifindex"]
            or peer_link.get("linkinfo", {}).get("info_kind") != "veth"
            or {(a["family"], a["local"], a["prefixlen"]) for a in peer_link["addr_info"]
                if a["family"] == "inet"} != {("inet", PEER, 30)}
            or run("ip", "-n", NS, "-4", "route", "show", "default").strip()
            or run("ip", "-n", NS, "-6", "route", "show", "default").strip()):
        raise ValueError("Dedicated peer identity differs")
    return fingerprint


def setup():
    if SCOPE.exists() or Path(f"/sys/class/net/{EDGE}").exists() or Path(f"/run/netns/{NS}").exists():
        raise RuntimeError("Ingress scope already exists")
    tables = json.loads(nft("-j", "list", "tables"))["nftables"]
    if any(row.get("table", {}).get("name") == TABLE for row in tables):
        raise RuntimeError("Ingress table already exists")
    routes = ip("route", "get", PEER)
    if len(routes) != 1 or not routes[0].get("gateway"):
        raise RuntimeError("Dedicated peer subnet overlaps an existing route")
    namespace = edge = table = False
    try:
        run("ip", "netns", "add", NS)
        namespace = True
        # Put filters in place before creating or raising the interface.
        nft("-f", "-", input=RULES)
        table = True
        run("ip", "link", "add", EDGE, "type", "veth", "peer", "name", PEER_IF, "netns", NS)
        edge = True
        run("ip", "addr", "add", SERVER + "/30", "dev", EDGE)
        run("ip", "link", "set", EDGE, "up")
        run("ip", "-n", NS, "addr", "add", PEER + "/30", "dev", PEER_IF)
        run("ip", "-n", NS, "link", "set", PEER_IF, "up")
        if run("ip", "-n", NS, "route", "show", "default").strip():
            raise RuntimeError("Peer must have no default route")
        SCOPE.write_text(json.dumps({"identity": identity(verify_peer=True), "table": fingerprint()}))
        SCOPE.chmod(0o600)
    except BaseException:
        if edge:
            run("ip", "link", "del", EDGE)
        if table:
            nft("delete", "table", "inet", TABLE)
        if namespace:
            run("ip", "netns", "del", NS)
        raise


def validate(scope):
    if identity() != scope["identity"] or fingerprint() != scope["table"]:
        raise ValueError("Ingress or firewall scope changed")


def cleanup():
    if not SCOPE.exists():
        return
    scope = json.loads(SCOPE.read_text())
    validate(scope)
    run("ip", "link", "del", EDGE)
    nft("delete", "table", "inet", TABLE)
    run("ip", "netns", "del", NS)
    SCOPE.unlink()


def respond(connection, scope, api_uid):
    connection.settimeout(.75)
    pid, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != api_uid or Path(f"/proc/{pid}/cgroup").read_text().strip() != (
            "0::/websentinelr47.slice/websentinel-r47-security.service"):
        return
    line = connection.makefile("rb").readline(64)
    verb = re.fullmatch(rb"(STATUS|UNBLOCK 10\.254\.63\.2|BLOCK 10\.254\.63\.2 ([1-9]|[1-5][0-9]|60))\n", line)
    if not verb or connection.recv(1):
        return
    validate(scope)
    snapshot = nft("-j", "list", "set", *SET)
    items = [item["set"] for item in json.loads(snapshot)["nftables"] if "set" in item]
    entries = items[0].get("elem", [])
    if len(items) != 1 or any((obj if isinstance(obj, str) else obj.get("elem", {}).get("val")) != PEER for obj in entries):
        raise ValueError("Unexpected kernel set")
    changed = False
    if verb[2] and not entries:
        nft("add", "element", *SET, "{", PEER, "timeout", f"{int(verb[2])}s", "}")
        changed = True
    elif verb[1].startswith(b"UNBLOCK") and entries:
        nft("delete", "element", *SET, "{", PEER, "}")
    try:
        connection.sendall(nft("-j", "list", "set", *SET).encode())
    except (OSError, subprocess.SubprocessError):
        if changed:
            nft("delete", "element", *SET, "{", PEER, "}")
        raise


def serve():
    api = pwd.getpwnam("ws-r47-security")
    scope = json.loads(SCOPE.read_text())
    validate(scope)
    if os.getgid() != grp.getgrnam("ws-r47-evidence").gr_gid:
        raise RuntimeError("Unexpected actuator group")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(SOCKET))
        SOCKET.chmod(0o660)
        listener.listen(8)
        try:
            while True:
                connection, _ = listener.accept()
                with connection:
                    try:
                        respond(connection, scope, api.pw_uid)
                    except (OSError, ValueError, subprocess.SubprocessError):
                        print("Actuator refused operation or lost kernel readback", flush=True)
        finally:
            SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    if os.geteuid() != 0 or not RUNTIME.is_dir() or RUNTIME.is_symlink() or RUNTIME.stat().st_uid != 0:
        raise SystemExit("Root-owned systemd runtime directory required")
    {"setup": setup, "serve": serve, "cleanup": cleanup}[sys.argv[1]]()

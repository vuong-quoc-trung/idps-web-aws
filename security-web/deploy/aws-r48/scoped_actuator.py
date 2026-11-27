"""Manual actuator for the dedicated peer and optional pinned EC2 web ingress."""

import grp
import hashlib
import ipaddress
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
MAX_TTL = 300
TABLE = "ws_aws_prevention"
SET = ("inet", TABLE, "blocked_ips")
RUNTIME = Path("/run/websentinel-aws-prevention")
SCOPE = RUNTIME / "scope.json"
SOCKET = RUNTIME / "actuator.sock"
RULES = f'''create table inet {TABLE}
table inet {TABLE} {{
  set blocked_ips {{ type ipv4_addr; flags timeout; size 128; }}
  chain input {{
    type filter hook input priority filter; policy accept;
    __WEB_SCOPE__
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
    rules = nft("-st", "list", "table", "inet", TABLE)
    # nft 1.1.6 appends live occupancy to set size even with --terse.
    rules = re.sub(r"(?m)^(\s*size \d+)[ \t]+# count \d+[ \t]*$", r"\1", rules)
    return hashlib.sha256(rules.encode()).hexdigest()


def public_profile():
    if os.environ.get("WS_AWS_MANUAL_PUBLIC_IPV4") != "1":
        return None
    device = os.environ["AWS_MANUAL_WEB_INTERFACE"]
    local = str(ipaddress.IPv4Address(os.environ["AWS_MANUAL_WEB_LOCAL_IP"]))
    eip = ipaddress.IPv4Address(os.environ["AWS_MANUAL_WEB_EIP"])
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", device) or device in {EDGE, "lo"} or not eip.is_global:
        raise ValueError("Invalid public web scope")
    routes = ip("route", "show", "default")
    links = ip("address", "show", "dev", device)
    if (len(routes) != 1 or routes[0].get("dev") != device or routes[0].get("prefsrc") != local
            or not routes[0].get("gateway") or len(links) != 1
            or local not in {addr.get("local") for addr in links[0]["addr_info"]}):
        raise ValueError("EC2 ingress scope changed")
    return {"interface": device, "local": local, "eip": str(eip),
            "ifindex": links[0]["ifindex"], "gateway": routes[0]["gateway"]}


def rules_for(public):
    if public is None:
        return RULES.replace("__WEB_SCOPE__", "")
    rule = (f'iifname "{public["interface"]}" ip daddr {public["local"]} '
            f'ip saddr != {PEER} tcp dport {{ 80, 443 }} ip saddr @blocked_ips counter drop')
    return RULES.replace("__WEB_SCOPE__", rule)


def allowed(target, public):
    if target == PEER:
        return True
    address = ipaddress.IPv4Address(target)
    if (public is None or not address.is_global or address.is_multicast or address.is_reserved
            or target in (public["eip"], public["local"], public["gateway"])):
        return False
    return all(address not in ipaddress.IPv4Network(network) for network in ("192.0.0.0/24", "192.88.99.0/24"))


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
    public = public_profile()
    namespace = edge = table = False
    try:
        run("ip", "netns", "add", NS)
        namespace = True
        # Put filters in place before creating or raising the interface.
        nft("-f", "-", input=rules_for(public))
        table = True
        run("ip", "link", "add", EDGE, "type", "veth", "peer", "name", PEER_IF, "netns", NS)
        edge = True
        run("ip", "addr", "add", SERVER + "/30", "dev", EDGE)
        run("ip", "link", "set", EDGE, "up")
        run("ip", "-n", NS, "addr", "add", PEER + "/30", "dev", PEER_IF)
        run("ip", "-n", NS, "link", "set", PEER_IF, "up")
        if run("ip", "-n", NS, "route", "show", "default").strip():
            raise RuntimeError("Peer must have no default route")
        SCOPE.write_text(json.dumps({"identity": identity(verify_peer=True), "table": fingerprint(), "public": public}))
        SCOPE.chmod(0o600)
    except BaseException:
        if edge:
            run("ip", "link", "del", EDGE)
        if table:
            nft("delete", "table", "inet", TABLE)
        if namespace:
            run("ip", "netns", "del", NS)
        raise


def validate(scope, *, verify_public=True):
    if identity() != scope["identity"] or fingerprint() != scope["table"]:
        raise ValueError("Ingress or firewall scope changed")
    if verify_public and public_profile() != scope.get("public"):
        raise ValueError("Public ingress changed")


def cleanup():
    if not SCOPE.exists():
        return
    scope = json.loads(SCOPE.read_text())
    validate(scope, verify_public=False)
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
    verb = re.fullmatch(rb"(?:(STATUS)|(UNBLOCK|BLOCK) ([0-9.]{7,15})(?: ([1-9][0-9]{0,2}))?)\n", line)
    if not verb or connection.recv(1):
        return
    ttl = int(verb[4]) if verb[4] else None
    target = verb[3].decode() if verb[3] else None
    public = scope.get("public")
    if (verb[2] == b"BLOCK") != (ttl is not None) or (ttl and ttl > MAX_TTL):
        return
    if target is not None and not allowed(target, public):
        return
    validate(scope)
    snapshot = nft("-j", "list", "set", *SET)
    item, = (item["set"] for item in json.loads(snapshot)["nftables"] if "set" in item)
    entries = {obj if isinstance(obj, str) else obj.get("elem", {}).get("val") for obj in item.get("elem", [])}
    if any(not isinstance(entry, str) or not allowed(entry, public) for entry in entries):
        raise ValueError("Unexpected kernel set")
    changed = False
    if ttl is not None and target not in entries:
        nft("add", "element", *SET, "{", target, "timeout", f"{ttl}s", "}")
        changed = True
    elif verb[2] == b"UNBLOCK" and target in entries:
        nft("delete", "element", *SET, "{", target, "}")
    try:
        connection.sendall(nft("-j", "list", "set", *SET).encode())
    except (OSError, subprocess.SubprocessError):
        if changed:
            nft("delete", "element", *SET, "{", target, "}")
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

"""Read only the approved Edge socket-peer ledger, never HTTP supplied addresses."""
import pwd
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

CONFIG = Path("/etc/ws-native/direct-peer.json")
LEDGER = Path("/var/lib/ws-native/edge/direct-peer.jsonl")


def scope(live=True, *, require_neighbor=True):
    if CONFIG.resolve() != CONFIG or CONFIG.stat().st_uid or CONFIG.stat().st_mode & 0o022:
        raise ValueError("Untrusted direct scope")
    cfg = json.loads(CONFIG.read_bytes())
    return validate(cfg, live=live, require_neighbor=require_neighbor)


def listening(address, pid=None):
    args = ["/usr/bin/ss", "-H", "-4", "-ltn"]
    if pid is not None:
        args.append("-p")
    rows = subprocess.check_output(args + ["sport = :24443"], text=True, timeout=2)
    for line in rows.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[3] == f"{address}:24443":
            if pid is None or f'"nginx",pid={pid},' in line:
                return True
    return False


def check_listener_name(cfg):
    name = cfg["listener_name"]
    try:
        answers = socket.getaddrinfo(name, 24443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Host NSS cannot resolve {name} to {cfg['listener_ip']}") from exc
    addresses = {answer[4][0] for answer in answers}
    if addresses != {cfg["listener_ip"]}:
        raise ValueError(f"{name} resolves to {sorted(addresses)}, expected only {cfg['listener_ip']}")


def dns_servers():
    # The actuator has no need for the system bus. Include per-link uplinks:
    # the stub in /etc/resolv.conf alone cannot identify protected DNS peers.
    def nameservers(path):
        servers = set()
        for line in path.read_text().splitlines():
            fields = line.split()
            if fields and fields[0] == "nameserver":
                servers.add(ipaddress.ip_address(fields[1].split("%", 1)[0]))
        return servers

    servers = nameservers(Path("/etc/resolv.conf"))
    for path in (Path("/run/systemd/resolve/resolv.conf"),
                 Path("/run/NetworkManager/no-stub-resolv.conf")):
        try:
            servers.update(nameservers(path))
        except FileNotFoundError:
            continue
    if not any(not ip.is_loopback and not ip.is_unspecified for ip in servers):
        raise ValueError("Cannot identify upstream DNS servers for the protected-IP check")
    return servers


def validate(cfg, live=True, require_listener=True, *, require_neighbor=True):
    addr = ipaddress.IPv4Address(cfg["exclusive_lab_peer"])
    local = ipaddress.IPv4Address(cfg["listener_ip"])
    if (not all(a.is_private and not (a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified) for a in (addr,local))
            or addr == local or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}",cfg["interface"])
            or cfg["interface"] == "lo" or not cfg["protected_networks"]
            or any(addr in ipaddress.ip_network(n) for n in cfg["protected_networks"])
            or not re.fullmatch(r"[a-fA-F0-9]{2}(:[a-fA-F0-9]{2}){5}",cfg["peer_mac"])):
        raise ValueError("Unusable lab peer")
    if cfg.get("exclusive_no_relay_confirmed") is not True:
        raise ValueError("Direct client exclusivity not confirmed")
    lab = ipaddress.IPv4Network(cfg["lab_cidr"])
    if not any(lab.subnet_of(r) and lab != r for r in map(ipaddress.IPv4Network,
            ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"))):
        raise ValueError("Require explicit subnet within RFC1918")
    if any(a not in lab or a in (lab.broadcast_address,lab.network_address) for a in (addr,local)):
        raise ValueError("Target/listener outside approved lab host range")
    if any(addr in ipaddress.ip_network(n) for n in ("192.168.20.0/24","192.168.10.0/24")):
        raise ValueError("Protected PBL4 infrastructure")
    if not live:
        return cfg
    if require_listener and not listening(str(local)):
        raise ValueError("No direct IPv4 listener at the approved lab address")
    def ip(*args):
        return json.loads(subprocess.check_output(["/usr/sbin/ip","-j","-4",*args], timeout=2))
    iface = cfg["interface"]
    if not (Path("/sys/class/net")/iface/"device").exists():
        raise ValueError("Physical lab network interface required")
    for dev in ip("addr","show"):
        if re.match(r"^(docker|br-|vmnet|virbr|veth)",dev["ifname"]) or (Path("/sys/class/net")/dev["ifname"]/"bridge").exists():
            for entry in dev["addr_info"]:
                if addr in ipaddress.ip_network(f"{entry['local']}/{entry['prefixlen']}",strict=False):
                    raise ValueError("Peer overlaps bridge or VM subnet")
    if addr in dns_servers():
        raise ValueError("Protected DNS address")
    if any(str(addr)==i.get("local") for dev in ip("addr","show") for i in dev.get("addr_info",[])):
        raise ValueError("Host address")
    if any(str(addr)==hop.get("gateway") for r in ip("route","show","table","all") for hop in (r,*r.get("nexthops",[]))):
        raise ValueError("Gateway address")
    route, = ip("route","get",str(addr))
    if route.get("dev")!=cfg["interface"] or route.get("prefsrc")!=str(local) or route.get("gateway"):
        raise ValueError("Peer not directly attached")
    if not require_listener or not require_neighbor:
        return cfg
    neighbor, = ip("neigh","show","to",str(addr),"dev",cfg["interface"])
    if neighbor.get("lladdr","").lower()!=cfg["peer_mac"].lower() or not set(neighbor.get("state",[])) & {"REACHABLE","STALE","DELAY","PROBE","PERMANENT"}:
        raise ValueError("Exclusive peer binding unconfirmed")
    return cfg


def check_table(cfg, data):
    import hashlib
    match = (f'iifname "{cfg["interface"]}" ip daddr {cfg["listener_ip"]} tcp dport 24443 '
             f'ip saddr {cfg["exclusive_lab_peer"]} ip saddr @edge_peers drop')
    prefix=f'ip daddr {cfg["listener_ip"]} tcp dport 24443'
    guards=(f'{prefix} ct status dnat drop {prefix} iifname != "{cfg["interface"]}" drop '
            f'{prefix} ip saddr != {cfg["exclusive_lab_peer"]} drop ')
    expected = ('table inet ws_native_lab_peer { set edge_peers { type ipv4_addr timeout 15s } '
                'chain input { type filter hook input priority filter; policy accept; ' + guards + match + ' } }')
    if " ".join(data.decode().split()) != expected or hashlib.sha256(data).hexdigest()!=cfg["table_sha256"]:
        raise ValueError("Dedicated table scope or fingerprint differs")


def verify(plan, cfg):
    rids = set(plan["evidence"])
    if len(rids)<10 or plan["request_id"] not in rids or len(rids)!=len(plan["evidence"]):
        raise ValueError("Insufficient independent transactions")
    check_observations(rids, plan["oldest"]-1, plan["issued"]+2,cfg)


def check_observations(rids, earliest, latest, cfg):
    hits = {}
    with LEDGER.open("rb") as f:
        if LEDGER.resolve()!=LEDGER or os.fstat(f.fileno()).st_uid not in (0,pwd.getpwnam("ws-native-edge").pw_uid) or os.fstat(f.fileno()).st_mode & 0o022:
            raise ValueError("Unsafe Edge ledger")
        # Bounded suffix. A rotated, truncated or incomplete observation cannot authorize a ban.
        offset=max(0,os.fstat(f.fileno()).st_size-1048576)
        f.seek(offset)
        if offset: f.readline()
        for line in f.read(1048576).splitlines(keepends=True):
            if not line.endswith(b"\n"): continue
            entry=json.loads(line)
            rid=entry.get("rid")
            if rid not in rids: continue
            if (rid in hits or entry["peer"]!=cfg["exclusive_lab_peer"] or entry["listener"]!=cfg["listener_ip"]
                    or str(entry["port"])!="24443" or not earliest<=float(entry["at"])<=min(time.time(),latest)):
                raise ValueError("Conflicting socket evidence")
            hits[rid]=True
    if set(hits)!=rids:
        raise ValueError("Missing socket evidence")


def ip_actuate(operation, plan):
    import socket
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(16)
        sock.connect("/run/ws-native-peer.sock")
        sock.sendall(json.dumps(dict(op=operation,plan=plan)).encode()+b"\n")
        sock.shutdown(socket.SHUT_WR)
        if sock.makefile("rb").read(24) != b"ACK\n":
            raise RuntimeError("Dedicated IP actuator did not acknowledge")
        return "APPLIED" if operation=="apply" else "REVOKED"

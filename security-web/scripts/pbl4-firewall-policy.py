#!/usr/bin/env python3
"""Narrow privileged actuator: literal IPv4 hosts, private scope, host/gateway exclusions.

Install root-owned at /usr/local/libexec/pbl4-firewall-policy.py. Optional policy:
/etc/pbl4/firewall-policy.json (root-owned, not group/world writable).
"""
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

DEFAULTS = {"allowed_subnets": ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"],
            "protected_ips": ["192.168.20.1", "192.168.20.10"]}
NFT = "/usr/sbin/nft"


def policy(path=Path("/etc/pbl4/firewall-policy.json")):
    if not path.exists():
        return DEFAULTS
    mode = path.stat()
    if path.is_symlink() or mode.st_uid != 0 or mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError("firewall policy must be root-owned and not shared-writable")
    value = json.loads(path.read_text())
    return {"allowed_subnets": value.get("allowed_subnets", DEFAULTS["allowed_subnets"]),
            "protected_ips": value.get("protected_ips", DEFAULTS["protected_ips"])}


def discover():
    def query(*args):
        return json.loads(subprocess.check_output(["/usr/sbin/ip", *args], timeout=2))
    addresses = {ipaddress.ip_address(item["local"]) for interface in query("-j", "address", "show")
                 for item in interface.get("addr_info", []) if "local" in item}
    if not addresses:
        raise ValueError("empty host discovery; refusing BLOCK")
    for args in [("-j", "route", "show", "default"), ("-6", "-j", "route", "show", "default")]:
        for route in query(*args):
            if route.get("gateway"):
                addresses.add(ipaddress.ip_address(route["gateway"]))
            addresses.update(ipaddress.ip_address(hop["gateway"]) for hop in route.get("nexthops", []) if hop.get("gateway"))
    return addresses


def validate(raw, settings, discovered):
    address = ipaddress.ip_address(raw)
    if address.version != 4 or address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local or str(address) == "255.255.255.255":
        raise ValueError("protected/non-unicast target")
    protected = {ipaddress.ip_address(value) for value in settings["protected_ips"]} | discovered
    if address in protected or not any(address in ipaddress.ip_network(value, strict=False) for value in settings["allowed_subnets"]):
        raise ValueError("protected target or outside allowed subnet")
    return address


def nft(*args, **kwargs):
    return subprocess.run([NFT, *args], check=True, timeout=5, **kwargs)


def main(args):
    if len(args) == 1 and args[0] in ("list", "list-json"):
        nft(*(["-j"] if args[0] == "list-json" else []), "list", "set", "inet", "pbl4_demo", "blocked_ips")
        return
    if len(args) not in (2,3) or args[0] not in ("block", "unblock"):
        raise ValueError("usage: pbl4-firewall block|unblock IP, or list|list-json")
    action, raw = args[:2]
    ttl = int(args[2]) if len(args)==3 else 300
    if not 1 <= ttl <= 300:
        raise ValueError("invalid bounded BLOCK TTL")
    address = ipaddress.ip_address(raw)
    if address.version != 4:
        raise ValueError("IPv4 enforcement only")
    if action == "block":
        settings = policy()
        discovered = discover()  # failure prevents any kernel change
        address = validate(raw, settings, discovered)
        protected = sorted({str(ip) for ip in discovered if ip.version == 4} |
                           {str(ipaddress.IPv4Address(value)) for value in settings["protected_ips"] if ":" not in value})
        # Atomic replacement of the independent kernel safety set.
        script = "flush set inet pbl4_demo protected_ips\n"
        if protected:
            script += "add element inet pbl4_demo protected_ips { " + ", ".join(protected) + " }\n"
        nft("-f", "-", input=script, text=True, stdout=subprocess.DEVNULL)
    present = subprocess.run([NFT, "get", "element", "inet", "pbl4_demo", "blocked_ips", "{", str(address), "}"],
                             capture_output=True, timeout=5).returncode == 0
    if present and action == "unblock":
        nft("delete", "element", "inet", "pbl4_demo", "blocked_ips", "{", str(address), "}")
    elif not present and action == "block":
        nft("add", "element", "inet", "pbl4_demo", "blocked_ips", "{", str(address), "timeout", f"{ttl}s", "}")
    else:
        nft("list", "set", "inet", "pbl4_demo", "blocked_ips", stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, OSError, subprocess.SubprocessError):
        print("Firewall operation refused/failed; verify protected assets, policy and nftables", file=sys.stderr)
        sys.exit(2)

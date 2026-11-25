"""Authorization lifetime; action leases always retain their individual deadlines."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import time

APPROVAL = Path("/etc/ws-native/approval.json")
SCOPE = Path("/etc/ws-native/direct-peer.json")
READY = Path("/run/ws-native-continuous.ready")
PROFILES = {
    "BLOCK_REQUEST": (["APP-1012", "APP-1013"], 3, 15),
    "BLOCK_SESSION": (["APP-1016"], 5, 30),
    "BLOCK_ACCOUNT": (["APP-1014"], 8, 60),
    "BLOCK_IP": (["APP-1013", "APP-1014"], 10, 15),
}


def trusted_bytes(path):
    if path.resolve() != path:
        raise ValueError(f"Unexpected symlink: {path}")
    with path.open("rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid or st.st_mode & 0o022:
            raise ValueError(f"Untrusted file: {path}")
        return f.read()


def validate_actions(actions):
    if set(actions) != set(PROFILES):
        raise ValueError("Require the four previously approved scopes")
    source = actions["BLOCK_REQUEST"]["source_instance"]
    actor = actions["BLOCK_SESSION"]["lab_actor"]
    if not source or not re.fullmatch("[a-f0-9]{64}", actor):
        raise ValueError("Missing approved VM binding")
    for action, (rules, events, ttl) in PROFILES.items():
        expected = dict(rules=rules, events=events, ttl=ttl, source_instance=source,
                        window_seconds=60, cooldown=60, immediate=[])
        if action in ("BLOCK_SESSION", "BLOCK_ACCOUNT"):
            expected["lab_actor"] = actor
        if actions[action] != expected:
            raise ValueError(f"Unexpected {action} scope")


def limits(policy):
    start = policy["start"]
    if type(start) is not int or start <= 0:
        raise ValueError("Invalid authorization start")
    if policy.get("mode", "LAB") == "LAB":
        end = policy["end"]
        if type(end) is not int or not 0 < end-start <= 600:
            raise ValueError("Invalid LAB deadline")
        return start, end
    if policy["mode"] != "CONTINUOUS" or "end" in policy:
        raise ValueError("Invalid authorization mode")
    validate_actions(policy["actions"])
    if not re.fullmatch("[a-f0-9]{64}", policy["scope_sha256"]):
        raise ValueError("Invalid direct scope digest")
    return start, None


def current():
    policy = json.loads(trusted_bytes(APPROVAL))
    start, end = limits(policy)
    if time.time() < start or (end is not None and time.time() >= end):
        raise ValueError("Authorization is outside its lifetime")
    return policy


def network_binding(cfg):
    from direct_peer import dns_servers
    iface = cfg["interface"]
    link = subprocess.check_output(["/usr/sbin/iw", "dev", iface, "link"], timeout=3)
    ap = re.search(rb"^Connected to ([0-9a-fA-F:]{17}) ", link, re.M)
    ssid = re.search(rb"^[ \t]*SSID: (.+)$", link, re.M)
    if not ap or not ssid:
        raise ValueError("Cannot verify approved Wi-Fi attachment")
    routes = json.loads(subprocess.check_output(["/usr/sbin/ip","-4","-j","route","show","default","dev",iface],timeout=2))
    gateways = sorted(r.get("gateway","") for r in routes)
    return hashlib.sha256(b"\0".join([ap[1].lower(), ssid[1],
        json.dumps(gateways).encode(), ",".join(sorted(map(str,dns_servers()))).encode()])).hexdigest()


def check_scope(policy):
    if policy.get("mode") == "CONTINUOUS" and hashlib.sha256(trusted_bytes(SCOPE)).hexdigest() != policy["scope_sha256"]:
        raise ValueError("Direct scope has changed since approval")
    if policy.get("mode") == "CONTINUOUS" and network_binding(json.loads(trusted_bytes(SCOPE))) != policy.get("network_sha256"):
        raise ValueError("Approved Wi-Fi, DNS or gateway changed")


def ready_generation(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def require_ready(policy):
    if policy.get("mode") == "CONTINUOUS" and json.loads(trusted_bytes(READY)) != ready_generation(policy):
        raise ValueError("Continuous startup readiness has not passed for this authorization")

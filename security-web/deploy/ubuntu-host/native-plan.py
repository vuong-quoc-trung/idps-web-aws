"""Fixed read-only planner; only the actuator UID can call this local socket."""
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess

with socket.socket(fileno=os.dup(0)) as peer:
    _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,12))
    caller = pwd.getpwuid(uid).pw_name
    if caller not in ("ws-native-actuator", "ws-native-ipguard"):
        raise SystemExit(1)
    policy=Path("/etc/ws-native/approval.json")
    if policy.resolve()!=policy or policy.stat().st_uid or policy.stat().st_mode & 0o022:
        raise ValueError("Untrusted policy")
    action = peer.recv(32).decode("ascii")
    if caller == "ws-native-ipguard" and action != "BLOCK_IP":
        raise PermissionError("IP actuator can check IP decisions only")
    cfg=json.loads(policy.read_bytes())["actions"][action]
    threshold={k:cfg[k] for k in ("events","window_seconds","ttl","source_instance")}
    threshold["action"]=action
    scopes = {"BLOCK_REQUEST": (3,15), "BLOCK_SESSION": (5,30), "BLOCK_ACCOUNT": (8,60), "BLOCK_IP": (10,15)}
    if scopes.get(action) != (cfg["events"],cfg["ttl"]):
        raise ValueError("Invalid action scope")
    if cfg["rules"]!={"BLOCK_REQUEST":["APP-1012","APP-1013"], "BLOCK_SESSION":["APP-1016"], "BLOCK_ACCOUNT":["APP-1014"], "BLOCK_IP":["APP-1013","APP-1014"]}[action] or cfg["immediate"]:
        raise ValueError("Unexpected native scope")
    result=subprocess.check_output(["/opt/ws-native/runtime-fix/security","--native-adaptive-plan",
        ",".join(cfg["rules"]),"",json.dumps(threshold)],timeout=5)
    peer.sendall(result)

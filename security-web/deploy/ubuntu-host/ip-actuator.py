"""One authenticated native worker RPC; modify only the lab Edge-specific set."""
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import socket
import struct
import subprocess
import sys
import time

from native_policy import check_scope, current as current_policy, limits, require_ready
from direct_peer import scope, verify, check_table

def nft(*args):
    return subprocess.check_output(["/usr/sbin/nft",*args],timeout=2)

with socket.socket(fileno=os.dup(0)) as sock:
    sock.settimeout(3)
    _,uid,_=struct.unpack("3i",sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    if uid!=pwd.getpwnam("ws-native-actuator").pw_uid: raise ValueError("Wrong caller")
    lock=open(__file__,"rb")
    fcntl.flock(lock,fcntl.LOCK_EX)
    msg=json.loads(sock.makefile("rb").read(8193))
    if msg == {"op":"readiness"}:
        stage = "direct-peer"
        try:
            check_scope(current_policy())
            cfg=scope(require_neighbor=False)
            stage = "nftables"
            check_table(cfg,nft("-st","list","table","inet","ws_native_lab_peer"))
            stage = "planner"
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as planner:
                planner.settimeout(6)
                planner.connect("/run/ws-native-peer-plan.sock")
                planner.sendall(b"BLOCK_IP")
                planner.shutdown(socket.SHUT_WR)
                raw = planner.makefile("rb").read(65537)
                if not raw:
                    raise ValueError("Planner closed without a response")
                if len(raw) > 65536:
                    raise ValueError("Oversized planner response")
                proposal = json.loads(raw)
                if proposal is not None and (not isinstance(proposal, dict) or proposal.get("action") != "BLOCK_IP"):
                    raise ValueError("Unexpected planner scope")
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            # Only a bounded diagnostic belongs on the RPC socket.
            detail = " ".join(str(exc).splitlines())[:220]
            reason = f"{stage}: {type(exc).__name__}: {detail}"
            print(f"BLOCK_IP readiness: {reason}", file=sys.stderr, flush=True)
            sock.sendall(("ERROR " + reason + "\n").encode("ascii", "backslashreplace"))
            raise SystemExit(1)
        sock.sendall(b"READY\n")
        raise SystemExit(0)
    plan=msg["plan"]
    cfg=scope(live=msg["op"]!="revoke")
    addr=cfg["exclusive_lab_peer"]
    if plan["action"]!="BLOCK_IP" or plan["selector"]!="ip-"+addr: raise ValueError("Scope mismatch")
    # Pin the reviewed input chain + set. Terse/stateless excludes changing elements.
    table=nft("-st","list","table","inet","ws_native_lab_peer")
    check_table(cfg,table)
    rid=plan["request_id"]
    if not re.fullmatch("[0-9a-f]{32}",rid): raise ValueError("Invalid decision")
    key=("element","inet","ws_native_lab_peer","edge_peers","{",addr,"}")
    if msg["op"]=="apply":
        p=Path("/etc/ws-native/approval.json")
        if p.resolve()!=p or p.stat().st_uid or p.stat().st_mode & 0o022: raise ValueError("Untrusted window")
        policy=current_policy()
        require_ready(policy)
        check_scope(policy)
        start, end = limits(policy)
        ttl=int(plan["expires"]-time.time())
        if not (1<=ttl<=15 and start<=plan["oldest"]<=plan["issued"]<=time.time()<plan["expires"] and (end is None or plan["expires"] <= end) and "BLOCK_IP" in policy["actions"]):
            raise ValueError("Outside authorization")
        # Independently re-read Rust's decision across the service credential boundary.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as planner:
            planner.settimeout(6)
            planner.connect("/run/ws-native-peer-plan.sock")
            planner.sendall(b"BLOCK_IP")
            planner.shutdown(socket.SHUT_WR)
            current = json.loads(planner.makefile("rb").read(65537))
        if current is None or current != (plan | {"selector": ""}):
            raise ValueError("Rust no longer authorizes this transaction set")
        verify(plan,cfg)
        # create (exclusive) never refreshes another lease or extends a retry.
        probe=subprocess.run(["/usr/sbin/nft","get",*key],capture_output=True,timeout=2)
        tag=f'comment "{rid}"'.encode()
        ttl=int(plan["expires"]-time.time())
        if ttl < 1: raise ValueError("Expired during verification")
        if probe.returncode and b"No such file or directory" not in probe.stderr: raise ValueError("Cannot read current set")
        if current_policy() != policy:
            raise ValueError("Operator authorization changed before apply")
        require_ready(policy)
        if probe.returncode: nft("create",*key[:-1],"timeout",f"{ttl}s","comment",f'"{rid}"',"}")
        elif tag not in probe.stdout: raise ValueError("Existing unrelated lease")
    elif msg["op"]=="revoke":
        probe=subprocess.run(["/usr/sbin/nft","get",*key],capture_output=True,timeout=2)
        if probe.returncode==0 and f'comment "{rid}"'.encode() in probe.stdout: nft("delete",*key)
        elif probe.returncode and b"No such file or directory" not in probe.stderr: raise ValueError("Cannot verify revocation")
    else: raise ValueError("Unsupported action")
    sock.sendall(b"ACK\n")

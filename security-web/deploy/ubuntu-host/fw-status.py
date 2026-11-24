"""Read-only status operation; systemd supplies a connected AF_UNIX socket."""
import hashlib
import json
from pathlib import Path
import os
import pwd
import socket
import sqlite3
import re
import time
from contextlib import closing
import struct
import subprocess

def active_leases(scope):
    """A missing/unreadable journal is distinct from an observed empty journal."""
    now = time.time()
    uri = "file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=0.15)) as db:
            db.execute("BEGIN")
            if db.execute("SELECT stopped FROM control").fetchall() not in ([(0,)], [(1,)]):
                return None
            # An actuator ACK without its durable decision cannot be scoped.
            orphan = db.execute("""SELECT 1 FROM audit a WHERE a.action='BLOCK_IP'
                AND a.outcome='APPLIED' AND NOT EXISTS (SELECT 1 FROM decisions d
                WHERE d.action=a.action AND d.rid=a.rid AND d.plan IS NOT NULL) LIMIT 1""").fetchone()
            if orphan:
                return None
            rows = db.execute("""
                SELECT d.rid,d.plan,d.revoked,
                  (SELECT outcome FROM audit a WHERE a.action=d.action AND a.rid=d.rid
                   AND outcome IN ('APPLIED','REVOKE_ACK','REVOKE_ACK_MISSING')
                   ORDER BY seq DESC LIMIT 1)
                FROM decisions d WHERE action='BLOCK_IP' AND plan IS NOT NULL
                AND (json_extract(plan,'$.expires') IS NULL OR json_extract(plan,'$.expires')>?)
            """, (now,)).fetchall()
        leases = []
        for rid, encoded, revoked, ack in rows:
            plan = json.loads(encoded)
            if (plan["action"] != "BLOCK_IP" or plan["request_id"] != rid
                    or not re.fullmatch("[a-f0-9]{32}", rid)
                    or not 0 < plan["expires"]-plan["issued"] <= 15
                    or plan["issued"] > now or plan["expires"] <= now + 1
                    or plan["selector"] != "ip-"+scope["exclusive_lab_peer"]):
                return None
            if revoked == 1 and ack == "REVOKE_ACK":
                continue
            if revoked != 0 or ack != "APPLIED":
                return None
            leases.append(dict(ip=scope["exclusive_lab_peer"], rid=rid,
                               issued=plan["issued"], expires=plan["expires"]))
        return sorted(leases, key=lambda lease: lease["rid"])
    except (sqlite3.Error, KeyError, ValueError, TypeError, OSError):
        return None


with socket.socket(fileno=os.dup(0)) as peer:
    peer.settimeout(2)
    _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != pwd.getpwnam("ws-native-security").pw_uid:
        raise SystemExit(1)
    with peer.makefile("rb") as reader:
        if reader.readline(16) != b"STATUS\n":
            raise SystemExit(1)
    table = ["list", "table", "inet", "ws_native_lab_peer"]
    result = subprocess.run(["/usr/sbin/nft", "-st", *table], capture_output=True,
                            timeout=2, env={"LC_ALL": "C"})
    if result.returncode:
        reply = b"UNINITIALIZED" if b"No such file or directory" in result.stderr else b"ACTUATOR_ERROR"
    else:
        try:
            scope = json.loads(Path("/etc/ws-native/direct-peer.json").read_bytes())
            # Same stateless table digest as lan-cutover, covering set, hook and rule scope.
            if hashlib.sha256(result.stdout).hexdigest() != scope["table_sha256"]:
                reply = b"SCOPE_MISMATCH"
            else:
                before = active_leases(scope)
                raw = subprocess.check_output(["/usr/sbin/nft", "-j", *table],
                                                stderr=subprocess.PIPE, timeout=2)
                snapshot = json.loads(raw)
                after = active_leases(scope)
                snapshot["worker_leases"] = after if before == after else None
                reply = json.dumps(snapshot).encode()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            reply = b"SCOPE_UNVERIFIED"
    peer.sendall(reply)

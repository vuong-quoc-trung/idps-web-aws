"""Native operator/worker entry point. Timed, explicitly approved scopes, off by default."""
import argparse
import grp
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import sqlite3
import subprocess
from vm_transport import deliver
from direct_peer import check_listener_name, scope, verify, ip_actuate

# Installation stores both files in the same root-owned release directory.
from approve_session import initialize, publish, emergency_stop

BASE = Path("/var/lib/ws-native/approval")
RUN = Path("/run/ws-native-leases")
ACTIONS = ("BLOCK_REQUEST", "BLOCK_SESSION", "BLOCK_ACCOUNT", "BLOCK_IP")
DIRS = {action: RUN for action in ACTIONS}
CONFIG = Path("/etc/ws-native/approval.json")
RULES = {"APP-1012", "APP-1013", "APP-1014", "APP-1016"}


def revoke_remote(plan):
    action = plan["action"]
    try:
        (ip_actuate if action == "BLOCK_IP" else deliver)("revoke", plan)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        outcome = "REVOKE_ACK_MISSING"
    else:
        outcome = "REVOKE_ACK"
    with sqlite3.connect(BASE / "approvals.sqlite3") as audit:
        audit.execute("INSERT INTO audit(at,operator,action,rid,outcome) VALUES(?,?,?,?,?)",
                      (int(time.time()), "native-worker", action, plan["request_id"], outcome))
    return outcome == "REVOKE_ACK"


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("init", "tick", "stop", "revoke"))
    cli.add_argument("action", nargs="?", choices=ACTIONS)
    cli.add_argument("request_id", nargs="?")
    args = cli.parse_args()
    if os.geteuid() == 0 or Path("/run/systemd/container").exists():
        sys.exit("Requires the dedicated unprivileged native actuator")
    for directory in (BASE, RUN):
        st = directory.stat()
        if directory.resolve() != directory or st.st_uid != os.getuid() or st.st_mode & 0o022:
            sys.exit("Unsafe actuator storage")
    gid = grp.getgrnam("ws-native-evidence").gr_gid
    if args.command == "init":
        initialize(BASE)
        return
    if args.command == "stop":
        emergency_stop(BASE, DIRS)
        missing = []
        with sqlite3.connect(BASE / "approvals.sqlite3") as db:
            for encoded, in db.execute("SELECT plan FROM decisions WHERE action IN ('BLOCK_SESSION','BLOCK_ACCOUNT','BLOCK_IP') AND plan IS NOT NULL AND json_extract(plan,'$.expires') > ?", (int(time.time()),)).fetchall():
                plan = json.loads(encoded)
                if not revoke_remote(plan): missing.append(plan["request_id"])
        if missing: sys.exit("Revocation ACK pending: " + ", ".join(missing))
        return
    if args.command == "revoke":
        if not args.action or not re.fullmatch("[a-f0-9]{32}", args.request_id or ""):
            cli.error("revoke requires action and trigger request ID")
        with sqlite3.connect(BASE / "approvals.sqlite3") as db:
            old = db.execute("SELECT plan FROM decisions WHERE action=? AND rid=?", (args.action,args.request_id)).fetchone()
        print(publish(None, args.request_id,args.action,RUN,gid,True,state=BASE))
        if args.action != "BLOCK_REQUEST" and old and old[0]:
            if not revoke_remote(json.loads(old[0])): sys.exit("Revocation ACK missing")
        return
    if not CONFIG.exists():
        return
    if CONFIG.resolve() != CONFIG or CONFIG.stat().st_uid != 0 or CONFIG.stat().st_mode & 0o022:
        sys.exit("Unsafe operator policy")
    policy = json.loads(CONFIG.read_text())
    start, end = policy["start"], policy["end"]
    if not start <= time.time() < end or not 0 < end-start <= 600:
        return
    if not set(policy["actions"]) <= set(ACTIONS):
        sys.exit("Unsupported action in native policy")
    for action in ACTIONS:
        cfg = policy["actions"].get(action)
        if cfg is None:
            continue
        rules, immediate = cfg["rules"], cfg["immediate"]
        if not set(immediate) <= set(rules) <= RULES or not rules or not 1 <= cfg["cooldown"] <= 3600:
            sys.exit("Invalid authorization")
        threshold = {k:cfg[k] for k in ("events","window_seconds","ttl","source_instance")}
        threshold["action"] = action
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(7)
            peer.connect("/run/ws-native-plan.sock")
            peer.sendall(action.encode("ascii"))
            peer.shutdown(socket.SHUT_WR)
            with peer.makefile("rb") as stream:
                payload = stream.read(65537)
        if len(payload)>65536:
            raise ValueError("Oversized native plan")
        plan=json.loads(payload)
        if plan is None:
            continue
        try:
            if action in ("BLOCK_ACCOUNT","BLOCK_SESSION"):
                actor = cfg.get("lab_actor","")
                if not re.fullmatch("[0-9a-f]{64}",actor) or not (
                        plan["selector"] == "account-"+actor if action == "BLOCK_ACCOUNT"
                        else plan["selector"].startswith(actor+".")):
                    raise ValueError("Outside operator-verified VM lab identity")
            if action == "BLOCK_IP":
                direct = scope()
                check_listener_name(direct)
                verify(plan, direct)
                plan["selector"] = "ip-" + direct["exclusive_lab_peer"]
            outcome = publish(plan,plan["request_id"],action,RUN,gid,
                  state=BASE,auto_window=(start,end),native=threshold|{"cooldown":cfg["cooldown"]})
            if action == "BLOCK_IP" and outcome == "ALREADY_ACTIVE":
                with sqlite3.connect(BASE / "approvals.sqlite3") as db:
                    ack = db.execute("SELECT 1 FROM audit WHERE action=? AND rid=? AND operator='kernel-actuator' AND outcome='APPLIED' LIMIT 1",
                                     (action,plan["request_id"])).fetchone()
                if ack:
                    continue  # Kernel expiry or manual withdrawal cannot re-arm this evidence.
            if action != "BLOCK_REQUEST":
                outcome = (ip_actuate if action == "BLOCK_IP" else deliver)("apply", plan)
                with sqlite3.connect(BASE / "approvals.sqlite3") as db:
                    db.execute("""INSERT INTO audit(at,operator,action,rid,outcome)
                        SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM audit WHERE action=? AND rid=? AND outcome=?)""",
                        (int(time.time()), ("kernel-actuator" if action == "BLOCK_IP" else "student-vm"), action, plan["request_id"], outcome, action, plan["request_id"], outcome))
            print(action,plan["request_id"],outcome)
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            if action != "BLOCK_IP" and not isinstance(exc, ValueError):
                raise
            if action == "BLOCK_IP":
                with sqlite3.connect(BASE / "approvals.sqlite3") as db:
                    db.execute("""INSERT INTO audit(at,operator,action,rid,outcome)
                        SELECT ?,'native-worker',?,?,'REVIEW' WHERE NOT EXISTS
                        (SELECT 1 FROM audit WHERE action=? AND rid=? AND outcome='REVIEW')""",
                        (int(time.time()),action,plan["request_id"],action,plan["request_id"]))
            print("REVIEW" if action=="BLOCK_IP" else "SKIPPED",action,plan["request_id"],str(exc))
            continue
        # publish() atomically rejects cross-action reuse of consumed evidence.


if __name__ == "__main__":
    main()

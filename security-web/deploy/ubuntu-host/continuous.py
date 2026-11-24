"""Root-only lifecycle for an explicitly promoted, previously accepted native scope."""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from direct_peer import check_listener_name, check_table, validate
from native_policy import APPROVAL, READY, SCOPE, ready_generation, check_scope, current, limits, network_binding, trusted_bytes, validate_actions

SAVED = APPROVAL.with_name("continuous-lab-baseline.json")


def write(path, obj):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(json.dumps(obj).encode())
        f.flush()
        os.fchmod(f.fileno(), 0o644)
        os.fsync(f.fileno())
    os.replace(f.name, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def promote():
    lab = json.loads(trusted_bytes(APPROVAL if APPROVAL.exists() else SAVED))
    if lab.get("mode") == "CONTINUOUS":
        check_scope(current())
        return
    limits(lab)
    validate_actions(lab["actions"])
    raw = trusted_bytes(SCOPE)
    cfg = json.loads(raw)
    check_listener_name(cfg)
    validate(cfg, require_neighbor=False)
    check_table(cfg, subprocess.check_output(["nft","-st","list","table","inet","ws_native_lab_peer"]))
    binding = network_binding(cfg)
    write(SAVED, lab)
    write(APPROVAL, dict(mode="CONTINUOUS", start=int(time.time()), actions=lab["actions"],
                         scope_sha256=hashlib.sha256(raw).hexdigest(), network_sha256=binding))


def guard():
    cfg = json.loads(trusted_bytes(SCOPE))
    if APPROVAL.exists():
        policy = json.loads(trusted_bytes(APPROVAL))
        check_scope(policy)
    validate(cfg, require_listener=False)
    tables = subprocess.check_output(["nft","-j","list","tables"])
    if not any(x.get("table",{}).get("family") == "inet" and x["table"]["name"] == "ws_native_lab_peer"
               for x in json.loads(tables)["nftables"]):
        rules = trusted_bytes(Path(__file__).with_name("direct-peer.nft.example")).decode()
        rules = rules.replace("LAB_INTERFACE",cfg["interface"]).replace("LISTENER_IPV4",cfg["listener_ip"]).replace("EXCLUSIVE_TEST_IPV4",cfg["exclusive_lab_peer"])
        subprocess.run(["nft","-f","-"], input="create table inet ws_native_lab_peer\n"+rules, text=True, check=True)
    check_table(cfg, subprocess.check_output(["nft","-st","list","table","inet","ws_native_lab_peer"]))


def request_outcomes():
    """Report a real 403 only when Gate, lease journal and ingested NGINX agree."""
    start = current()["start"]
    logs = subprocess.check_output(["journalctl","-u","ws-native-gate","--since",f"@{start}",
                                    "-n","100","--no-pager","-o","cat"],text=True,timeout=5)
    matches = re.findall(r"^BLOCK_REQUEST trigger=([0-9a-f]{32}) request=([0-9a-f]{32}) expires=(\d{1,12})$",logs,re.M)
    db = "file:/var/lib/ws-native/approval/approvals.sqlite3?mode=ro"
    with sqlite3.connect(db, uri=True) as journal:
        pairs = [(trigger,rid) for trigger,rid,end in matches if journal.execute(
            "SELECT 1 FROM decisions WHERE action='BLOCK_REQUEST' AND rid=? AND json_extract(plan,'$.expires')=?",
            (trigger,int(end))).fetchone()]
    if pairs:
        # Both identifiers have been restricted to exactly 32 hexadecimal characters.
        rows = ",".join(f"('{trigger}','{rid}')" for trigger,rid in pairs)
        sql = f"""SELECT DISTINCT r.trigger,r.rid,403 FROM (VALUES {rows}) AS r(trigger,rid)
            JOIN normalized_events n ON n.request_id=r.rid WHERE n.source='NGINX'
            AND n.uri_path='/api/users' AND n.status_code=403 AND n.occurred_at>=to_timestamp({int(start)})"""
        result = subprocess.check_output(["docker","exec","-e","PGOPTIONS=-cdefault_transaction_read_only=on",
                "pbl4-postgres","psql","-XAt","-v","ON_ERROR_STOP=1","-U","pbl4","-d","ws_native_security","-c",sql],
                text=True,timeout=5).strip()
        if result:
            print("Confirmed Gate trigger | HTTP request ID | HTTP status")
            print(result)
            return
    print("BLOCK_REQUEST: no confirmed HTTP 403 in the last 100 Gate journal lines")


if __name__ == "__main__":
    if os.geteuid() or Path("/run/systemd/container").exists():
        sys.exit("Native Host operator required")
    command, = sys.argv[1:]
    if command == "outcomes":
        try:
            request_outcomes()
        except (sqlite3.Error, OSError, subprocess.SubprocessError) as exc:
            print(f"BLOCK_REQUEST HTTP evidence unavailable: {type(exc).__name__}")
    elif command == "guard":
        guard()
    elif command == "promote":
        promote()
    elif command in ("check", "mark-ready"):
        policy = current()
        if policy.get("mode") != "CONTINUOUS":
            sys.exit("Continuous mode not authorized")
        check_scope(policy)
        if command == "mark-ready":
            write(READY, ready_generation(policy))
    else:
        sys.exit("Unknown operation")

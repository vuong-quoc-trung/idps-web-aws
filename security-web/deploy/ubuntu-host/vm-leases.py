"""Forced SSH command on Student VM. Run as a dedicated unprivileged lease writer."""
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time
from approve_session import install_record, sync_directory

ROOT = Path("/var/lib/ws-student-leases")
LEASES = ROOT / "leases"
STATE = ROOT / "consumed"


def receive(msg, leases, state):
    op = msg["op"]
    if op == "ready":
        for directory in (leases, state):
            if not directory.is_dir() or directory.resolve() != directory or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022:
                raise ValueError("Unsafe VM lease storage")
        return "READY"
    rid, selector = msg["rid"], msg["selector"]
    if not re.fullmatch("[0-9a-f]{32}", rid) or not re.fullmatch(
        r"(account-[0-9a-f]{64}|[0-9a-f]{64}\.[0-9a-f]{64})", selector
    ):
        raise ValueError("Invalid lease binding")
    start, end = msg["issued"], msg["expires"]
    if type(start) != int or type(end) != int or not 0 < end-start <= 60:
        raise ValueError("Invalid lease lifetime")
    record = f"{rid} {start} {end}\n"
    path = leases / selector
    marker = state / rid
    gid = leases.stat().st_gid
    with (state / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if op == "revoke":
            install_record(marker, "REVOKED", os.getgid())
            sync_directory(state)
            if path.exists() and path.read_text() == record:
                path.unlink()
                sync_directory(leases)
            return "REVOKED"
        if op != "apply" or not start <= time.time() < end:
            raise ValueError("Expired or unknown operation")
        if marker.exists():
            if marker.read_text() == selector + record and path.exists() and path.read_text() == record:
                return "APPLIED"
            raise ValueError("Consumed decision")
        if path.exists() and int(path.read_text().split()[2]) > time.time():
            raise ValueError("Selector already leased")
        install_record(marker, selector + record, os.getgid())
        sync_directory(state)
        install_record(path, record, gid)
        sync_directory(leases)
        return "APPLIED"


if __name__ == "__main__":
    if os.geteuid() == 0 or os.environ.get("SSH_ORIGINAL_COMMAND"):
        sys.exit("Requires restricted SSH identity")
    print(receive(json.loads(sys.stdin.buffer.read(2049)), LEASES, STATE))

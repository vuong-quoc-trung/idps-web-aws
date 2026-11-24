"""Controlled development lease publisher; root in ws-i5-dev only."""
import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing
import socket
import subprocess
import syslog
import tempfile
import time

DIRECTORIES = {
    "BLOCK_ACCOUNT": Path("/run/ws-dev-session-leases"),
    "BLOCK_SESSION": Path("/run/ws-dev-session-leases"),
    "BLOCK_REQUEST": Path("/run/ws-dev-request-leases"),
}


def install_record(target, content, gid):
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as stage:
        path = Path(stage.name)
        try:
            os.fchown(stage.fileno(), -1, gid)
            os.fchmod(stage.fileno(), 0o640)
            stage.write(content)
            stage.flush()
            os.fsync(stage.fileno())
            path.replace(target)
        finally:
            path.unlink(missing_ok=True)


STATE = Path("/var/lib/ws-adaptive-dev")
JOURNAL = "approvals.sqlite3"


def initialize(state):
    # Explicit provisioning only. Existing files, including damaged journals, fail closed.
    path = state / JOURNAL
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE decisions(action TEXT, rid TEXT, plan TEXT, revoked INTEGER NOT NULL,
                                   PRIMARY KEY(action,rid));
            CREATE TABLE control(stopped INTEGER NOT NULL CHECK(stopped IN (0,1)));
            INSERT INTO control VALUES(0);
            CREATE TABLE audit(seq INTEGER PRIMARY KEY, at INTEGER NOT NULL, operator TEXT NOT NULL,
                               action TEXT NOT NULL, rid TEXT NOT NULL, outcome TEXT NOT NULL);
        """)
    sync_directory(state)


def sync_directory(directory):
    fd = os.open(directory, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def emergency_stop(state, directories):
    """Latch first, then withdraw outstanding leases. Repeat safely after interruption."""
    path = state / JOURNAL
    with path.open("rb") as lock, closing(sqlite3.connect(path.as_uri()+"?mode=rw", uri=True)) as db:
        fcntl.flock(lock, fcntl.LOCK_EX)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("UPDATE control SET stopped=1")
        db.execute("INSERT INTO audit(at,operator,action,rid,outcome) VALUES(?,?,?,?,?)",
                   (int(time.time()), os.environ.get("SUDO_UID", str(os.getuid())), "ALL", "-", "STOP"))
        db.commit()
        for action, rid, encoded in db.execute("SELECT action,rid,plan FROM decisions WHERE revoked=0").fetchall():
            plan = json.loads(encoded)
            directory = directories[action]
            target = directory / plan["selector"]
            if target.exists() and target.read_text() == lease_record(plan):
                target.unlink()
                sync_directory(directory)
            db.execute("UPDATE decisions SET revoked=1 WHERE action=? AND rid=?", (action,rid))
            db.execute("INSERT INTO audit(at,operator,action,rid,outcome) VALUES(?,?,?,?,?)",
                       (int(time.time()), os.environ.get("SUDO_UID", str(os.getuid())), action,rid,"STOP_REVOKED"))
        db.commit()


def publish(plan, rid, action, directory, gid, cancel=False, *, state, auto_window=None, native=None):
    if not re.fullmatch("[a-f0-9]{32}", rid):
        raise ValueError("Invalid request ID")
    path = state / JOURNAL
    operator = "native-policy" if native else "auto-canary" if auto_window else os.environ.get("SUDO_UID") or str(os.getuid())
    with path.open("rb") as lock, closing(sqlite3.connect(path.as_uri()+"?mode=rw", uri=True)) as db:
        fcntl.flock(lock, fcntl.LOCK_EX)
        db.execute("PRAGMA synchronous=FULL")

        def audit(outcome):
            db.execute("INSERT INTO audit(at,operator,action,rid,outcome) VALUES(?,?,?,?,?)",
                       (int(time.time()), operator, action, rid, outcome))
            db.commit()
            return outcome

        def deny(reason):
            audit("DENIED: " + reason)
            raise ValueError(reason)

        row = db.execute("SELECT plan,revoked FROM decisions WHERE action=? AND rid=?",
                         (action,rid)).fetchone()
        native_ip = action == "BLOCK_IP" and directory == Path("/run/ws-native-leases") and (native or cancel)
        if action not in DIRECTORIES and not native_ip:
            deny("No verified direct peer")
        if cancel:
            # Withdraw the exact lease before acknowledging a durable revocation.
            # A crash after unlink cannot republish: consumed approvals are never recreated.
            if row and row[0]:
                old = json.loads(row[0])
                target = directory / old["selector"]
                if target.exists() and target.read_text() == lease_record(old):
                    target.unlink()
                    sync_directory(directory)
            db.execute("""INSERT INTO decisions VALUES(?,?,NULL,1)
                          ON CONFLICT(action,rid) DO UPDATE SET revoked=1""", (action,rid))
            return audit("REVOKED")
        if db.execute("SELECT stopped FROM control").fetchone() != (0,):
            deny("Emergency stop latched")
        if row and row[1]:
            deny("Revoked decision")
        if plan is None or plan["request_id"] != rid or plan["action"] != action:
            deny("Plan binding mismatch")
        selector = plan["selector"]
        if not (action == "BLOCK_REQUEST" and (selector == "dev-canary" if not native else re.fullmatch(r"request-[a-f0-9]{64}", selector)) or
                native_ip and re.fullmatch(r"ip-[0-9.]{7,15}", selector) or
                action == "BLOCK_ACCOUNT" and re.fullmatch(r"account-[a-f0-9]{64}", selector) or
                action == "BLOCK_SESSION" and re.fullmatch(r"[a-f0-9]{64}\.[a-f0-9]{64}", selector)):
            deny("Invalid selector")
        issued, end = plan["issued"], plan["expires"]
        now = int(time.time())
        if not (type(issued) is int and type(end) is int and 0 < end-issued <= 120 and issued <= now < end):
            deny("Invalid or expired deadline")
        encoded = json.dumps(plan, sort_keys=True)
        target = directory / selector
        current = target.read_text() if target.exists() else None
        record = lease_record(plan)
        if auto_window and auto_window[1] is None:
            if not native or directory != Path("/run/ws-native-leases"):
                deny("Continuous authorization requires native actuator")
            from native_policy import current as current_policy, require_ready
            policy = current_policy()
            require_ready(policy)
            cfg = policy["actions"].get(action, {})
            if (policy.get("mode") != "CONTINUOUS" or policy["start"] != auto_window[0]
                    or native["action"] != action or any(native[k] != cfg.get(k) for k in
                    ("events","window_seconds","ttl","source_instance","cooldown"))):
                deny("Continuous authorization changed")
            evidence = plan["evidence"]
            if (len(set(evidence)) != len(evidence) or rid not in evidence or len(evidence) < cfg["events"]
                    or not all(re.fullmatch("[0-9a-f]{32}", e) for e in evidence)
                    or not policy["start"] <= plan["oldest"] <= issued
                    or now-plan["oldest"] > cfg["window_seconds"] or end-issued > cfg["ttl"]):
                deny("Insufficient fresh independent evidence")
            if ((action == "BLOCK_ACCOUNT" and selector != "account-"+cfg["lab_actor"])
                    or (action == "BLOCK_SESSION" and not selector.startswith(cfg["lab_actor"]+"."))):
                deny("Outside approved actor scope")
        if row:
            if row[0] == encoded and current == record:
                return audit("ALREADY_ACTIVE")
            deny("Consumed decision; new evidence required")
        if auto_window:
            start, until = auto_window
            if ((native is None and action != "BLOCK_REQUEST") or (native and action != native["action"]) or not start <= plan["oldest"] <= issued
                    or (until is None and not native) or (until is not None and (end > until or until-start > 900)) or end-issued > (native["ttl"] if native else 15)):
                deny("Outside automatic canary authorization")
            # Journal is locked across this check and reservation. Revocation never
            # erases previous consumption, and retries cannot extend cooldown.
            if db.execute("""SELECT 1 FROM decisions WHERE action=? AND
                    json_extract(plan,'$.selector')=? AND json_extract(plan,'$.expires') + ? > ? LIMIT 1""",
                          (action,selector,native["cooldown"] if native else 60,now)).fetchone():
                deny("Canary cooldown")
            for evidence in plan["evidence"]:
                if db.execute("""SELECT 1 FROM decisions d WHERE (d.action=? OR (? AND d.action<>'BLOCK_IP'))
                        AND (d.rid=? OR EXISTS (SELECT 1 FROM json_each(d.plan,'$.evidence') e
                        WHERE e.value=?)) LIMIT 1""", (action,bool(native) and action != "BLOCK_IP",evidence,evidence)).fetchone():
                    deny("Previously consumed evidence")
        if current and int(current.split()[2]) > now:
            deny("Conflicting live lease")
        db.execute("INSERT INTO decisions VALUES(?,?,?,0)", (action,rid,encoded))
        audit("RESERVED")
        install_record(target, record, gid)
        sync_directory(directory)
        return audit("APPROVED")


def lease_record(plan):
    return f"{plan['request_id']} {plan['issued']} {plan['expires']}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emergency-stop", action="store_true")
    parser.add_argument("--auto-canary", nargs=4, metavar=("START","END","RULES","IMMEDIATE"),
                        help="One guest-only tick for an approved canary window; use - for no immediate rules")
    parser.add_argument("--init-journal", action="store_true")
    parser.add_argument("--approve", metavar="REQUEST_ID")
    parser.add_argument("--action", choices=[*DIRECTORIES, "BLOCK_IP"])
    parser.add_argument("--confirm-account-lock", action="store_true")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    if (socket.gethostname() != "ws-i5-dev" or os.geteuid() != 0 or
            Path("/run/systemd/container").read_text().strip() != "systemd-nspawn"):
        raise RuntimeError("Requires ws-i5-dev administrator")
    if STATE.resolve() != STATE or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o077:
        raise RuntimeError("Journal requires private root-owned state directory")
    if args.auto_canary:
        if args.approve or args.action or args.revoke or args.emergency_stop or args.init_journal:
            parser.error("Automatic canary must run separately")
        start, until = map(int, args.auto_canary[:2])
        now = int(time.time())
        if not start <= now < until or not 0 < until-start <= 900:
            return
        directory = DIRECTORIES["BLOCK_REQUEST"]
        if directory.resolve() != directory or directory.stat().st_uid or directory.stat().st_mode & 0o022:
            raise RuntimeError("Untrusted lease directory")
        rules, critical = args.auto_canary[2:]
        plan = json.loads(subprocess.check_output([
            "systemd-run", "--quiet", "--wait", "--pipe", "--collect", "-p", "User=websentinel-security",
            "-p", "EnvironmentFile=/etc/websentinel-beta/security.env",
            "/opt/ws-auto-canary/pbl4-security-demo", "--dev-auto-canary", rules,
            "" if critical == "-" else critical], timeout=10))
        if plan:
            try:
                print(publish(plan, plan["request_id"], "BLOCK_REQUEST", directory,
                          grp.getgrnam("websentinel-evidence").gr_gid, state=STATE, auto_window=(start,until)))
            except ValueError as exc:
                print("SKIPPED", plan["request_id"], str(exc))
        return
    if args.emergency_stop:
        if args.approve or args.revoke or args.action or args.init_journal:
            parser.error("Stop is a separate operation")
        emergency_stop(STATE, DIRECTORIES)
        return
    if args.init_journal:
        if args.approve or args.revoke or args.action:
            parser.error("Initialization is a separate provisioning step")
        initialize(STATE)
        return
    if not args.action or not args.approve:
        parser.error("Expected --approve REQUEST_ID --action ACTION")
    rid, action = args.approve, args.action
    if action == "BLOCK_ACCOUNT" and not args.revoke and not args.confirm_account_lock:
        parser.error("Account-wide lock requires --confirm-account-lock")
    if not re.fullmatch("[a-f0-9]{32}", rid):
        raise ValueError("Invalid request ID")
    syslog.syslog(f"adaptive INTENT action={action} request={rid} revoke={args.revoke}")
    try:
        native_ip = action == "BLOCK_IP" and directory == Path("/run/ws-native-leases") and (native or cancel)
        if action not in DIRECTORIES and not native_ip:
            publish(None, rid, action, None, None, state=STATE)
        directory = DIRECTORIES[action]
        meta = directory.stat()
        if directory.resolve() != directory or meta.st_uid != 0 or meta.st_mode & 0o022:
            raise RuntimeError("Untrusted lease directory")
        plan = None
        if not args.revoke:
            command = ["systemd-run", "--quiet", "--wait", "--pipe", "--collect",
                       "-p", "User=websentinel-security",
                       "-p", "EnvironmentFile=/etc/websentinel-beta/security.env",
                       "/opt/ws-adaptive-dev/pbl4-security-demo", "--dev-action-plan", rid, action]
            plan = json.loads(subprocess.check_output(command, timeout=15))
        group = grp.getgrnam("websentinel-evidence").gr_gid
        outcome = publish(plan, rid, action, directory, group, args.revoke, state=STATE)
    except Exception:
        syslog.syslog(f"adaptive DENIED_OR_FAILED action={action} request={rid}")
        raise
    syslog.syslog(f"adaptive {outcome} action={action} request={rid}")
    print(outcome, action, rid)


if __name__ == "__main__":
    main()

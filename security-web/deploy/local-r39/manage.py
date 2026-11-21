#!/usr/bin/env python3
"""Install or operate the single-host WebSentinel monitoring beta."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import beta_profile as profile
import student_deps

SOURCE = Path(__file__).resolve().parent
BASE = Path("/opt/websentinel-beta")
CONFIG = Path(profile.CONFIG)
STATE = Path(profile.STATE)
CURRENT = BASE / "current"
MARKER = CONFIG / "deployment.json"
SYSTEM = Path("/etc/systemd/system")
SYSUSERS = Path("/etc/sysusers.d/websentinel-beta.conf")
UNITS = profile.UNITS
DATABASES = {
    "websentinel_student": "websentinel_student",
    "websentinel_security": "websentinel_security",
}
PACKAGES = (
    "acl",
    "ca-certificates",
    "curl",
    "nginx",
    "libnginx-mod-http-js",
    "nftables",
    "openjdk-25-jre-headless",
    "openssl",
    "postgresql-18",
    "python3-yaml",
    "suricata",
)


def run(*args, content=None, timeout=60):
    return subprocess.run(
        args,
        check=True,
        text=True,
        input=content,
        timeout=timeout,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def verify(root):
    expected = {}
    for row in (root / "SHA256SUMS").read_text().splitlines():
        sha, value = row.split("  ", 1)
        path = Path(value)
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != value
            or value in expected
            or not re.fullmatch(r"[0-9a-f]{64}", sha)
        ):
            raise ValueError("Invalid archive manifest path")
        expected[value] = sha
    paths = list(root.rglob("*"))
    actual = {
        str(p.relative_to(root))
        for p in paths
        if p.is_file() and p != root / "SHA256SUMS"
    }
    if any(p.is_symlink() for p in paths) or actual != set(expected):
        raise ValueError("Unexpected package contents")
    for name, sha in expected.items():
        if digest(root / name) != sha:
            raise ValueError(f"Package hash mismatch: {name}")
    slots = root / "scorer/ai-training/contracts/quality-freeze-r37/slots.json"
    slot = json.loads(slots.read_text())["slots"]["candidate"]
    if digest(slots.parent / slot["model"]) != slot["sha256"]:
        raise ValueError("Pinned ONNX mismatch")
    return json.loads((root / "release.json").read_text())


def require_root():
    if os.geteuid() != 0 or not Path("/run/systemd/system").is_dir():
        raise RuntimeError(
            "System installation requires root and a booted systemd host"
        )


def hardware_check():
    # Use the same pinned reader and admission predicate as the installed guardian.
    sys.path.insert(0, str(SOURCE / "scorer/ai-training/src"))
    from idps_ai.common import PipelineError
    from idps_ai.training.adaptive_thermal import SensorReader, hardware_snapshot
    from idps_ai.training.thermal_policy import admission

    try:
        snapshot = hardware_snapshot()
        result = admission(SensorReader(snapshot), "BETA_INSTALL_PREFLIGHT")
    except (OSError, ValueError, StopIteration, PipelineError) as exc:
        raise RuntimeError(f"Scorer hardware refused: {exc}") from exc
    if result["decision"] != "ACCEPT":
        raise RuntimeError(f"Scorer hardware refused: {result['state']}")
    return {
        "processor": snapshot["processor"],
        "sensor": result["sensor_source"],
        "sensor_count": len(snapshot["cpu_sensors"]),
        "temperature_C": result["reading"]["temperature_C"],
        "state": result["state"],
        "decision": result["decision"],
        "policy": result["policy"],
    }


def preflight():
    hardware_check()
    identifiers = dict(
        line.split("=", 1)
        for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    if (
        identifiers.get("ID") != "ubuntu"
        or identifiers.get("VERSION_ID", "").strip('"') != "26.04"
        or run("dpkg", "--print-architecture") != "amd64"
    ):
        raise RuntimeError("Install profile targets Ubuntu 26.04 amd64")
    for name in PACKAGES:
        if run("dpkg-query", "-W", "-f=${db:Status-Status}", name) != "installed":
            raise RuntimeError(f"Package must be installed: {name}")
    if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        raise RuntimeError("Unified cgroup v2 is required")
    if "LUA" not in run("/usr/bin/suricata", "--build-info").upper():
        raise RuntimeError("Suricata with Lua output is required")


def psql(sql, database="postgres"):
    return run(
        "runuser",
        "-u",
        "postgres",
        "--",
        "psql",
        "-XqAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-d",
        database,
        content=sql,
    )


def check_tls(cert, key, ca):
    run(
        "openssl",
        "verify",
        "-purpose",
        "sslserver",
        "-verify_ip",
        "127.0.0.1",
        "-CAfile",
        ca,
        cert,
    )
    pub = run("openssl", "x509", "-in", cert, "-noout", "-pubkey")
    if pub != run("openssl", "pkey", "-in", key, "-pubout", "-passin", "pass:"):
        raise ValueError("Certificate and private key do not match")


def passwd(prompt, file=None):
    value = file.read_text().rstrip("\n") if file else getpass.getpass(prompt)
    if not re.fullmatch(r"[A-Za-z0-9_!@%+=.,~-]{16,64}", value):
        raise ValueError("Use 16–64 ASCII letters, digits or _!@%+=.,~-")
    return value


def load_passwords(args, destination):
    student = passwd("Mật khẩu quản trị Student Web: ", args.student_password_file)
    admin = passwd("Mật khẩu quản trị Security Web: ", args.security_password_file)
    if student == admin:
        raise ValueError("Student and Security Web require distinct passwords")
    hashed = run(
        destination / "security/pbl4-security-demo",
        "--hash-password",
        content=admin + "\n",
    )
    if not hashed.startswith("$argon2"):
        raise RuntimeError("Security Web hash output is invalid")
    return student, hashed


def cgroup_wait(check, sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        try:
            if check():
                return
        except (subprocess.CalledProcessError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.75)
    raise RuntimeError("Service health deadline exceeded")


def control(action, units):
    run("systemctl", action, *units, timeout=180)


def health():
    for unit in UNITS:
        run("systemctl", "is-active", unit)
    response = run(
        "runuser",
        "-u",
        "websentinel-edge",
        "--",
        "curl",
        "-fsSi",
        "--max-time",
        "3",
        "--unix-socket",
        "/run/websentinel-edge-shadow/receiver.sock",
        "http://localhost/healthz",
    )
    expected = current_slot()["sha256"]
    if f"x-model-sha256: {expected}" not in response.lower().splitlines():
        raise RuntimeError("Unexpected scorer SHA")
    args = ("curl", "-fsS", "--max-time", "3", "--cacert", CONFIG / "edge-ca.crt")
    if json.loads(run(*args, "https://127.0.0.1:9443/health")) != {"status": "alive"}:
        raise RuntimeError("Security Web health response mismatch")
    with socket.create_connection(("127.0.0.1", 8080), timeout=1):
        pass
    run(*args, "-o", "/dev/null", "https://127.0.0.1/")
    reader = ("runuser", "-u", "websentinel-security", "-g", "websentinel-evidence", "--")
    for path in (STATE / "student/audit.jsonl", Path(profile.SCORER_STATE) / "observations.jsonl"):
        run(*reader, "test", "-r", path.parent)
        run(*reader, "test", "-x", path.parent)
        run(*reader, "test", "-r", path)
        run(*reader, "test", "!", "-w", path)
        run(*reader, "test", "!", "-w", path.parent)
    run(*reader, "test", "!", "-x", Path(profile.SCORER_STATE) / "private")
    print(json.dumps({"status": "HEALTHY", "model_sha256": expected}))


def current_slot():
    value = next(
        line.split("=", 1)[1]
        for line in (CONFIG / "scorer.env").read_text().splitlines()
        if line.startswith("MODEL_SLOT=")
    )
    slots = CURRENT / "scorer/ai-training/contracts/quality-freeze-r37/slots.json"
    return json.loads(slots.read_text())["slots"][value]


def install(args):
    meta = verify(SOURCE)
    preflight()
    student_deps.verify(SOURCE / "student/dependencies.json", args.student_cache)
    check_tls(args.cert, args.key, args.ca)
    if (
        any(
            path.exists() or path.is_symlink()
            for path in (
                BASE,
                CONFIG,
                STATE,
                Path(profile.SCORER_STATE),
                SYSUSERS,
                *(SYSTEM / unit for unit in UNITS),
            )
        )
        or shutil.which("nft")
        and "table inet pbl4_local_egress" in run("nft", "list", "tables")
    ):
        raise RuntimeError("Existing files or guard table overlap the beta profile")
    if any(
        subprocess.run(["systemctl", "is-active", "--quiet", u]).returncode == 0
        for u in ("nginx.service", "suricata.service")
    ):
        raise RuntimeError(
            "Clean beta host required: stop default distribution NGINX and Suricata"
        )
    run("systemctl", "start", "postgresql.service")
    cgroup_wait(lambda: psql("select 1;") == "1", 30)
    names = ", ".join(f"'{db}'" for db in DATABASES)
    for table, col in (("pg_database", "datname"), ("pg_roles", "rolname")):
        if psql(f"select 1 from {table} where {col} in ({names});"):
            raise RuntimeError("Database or role already exists")
    student_pw, admin_hash = load_passwords(args, SOURCE)
    # Parse the manifest before using its version as a file name.
    version = meta["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+-beta\.\d+", version):
        raise ValueError("Invalid release version")
    CONFIG.mkdir(mode=0o700)
    BASE.mkdir(mode=0o755)
    (BASE / "releases").mkdir(mode=0o755)
    destination = BASE / "releases" / version
    shutil.copytree(SOURCE, destination, symlinks=True)
    verify(destination)
    for path in (BASE, BASE / "releases", destination, *destination.rglob("*")):
        executable = (
            path == destination / "security/pbl4-security-demo"
            or path == destination / "scorer/bin/scorer"
        )
        path.chmod(0o755 if path.is_dir() or executable else 0o644)
    CURRENT.symlink_to(destination)
    lineage = "local-beta-" + secrets.token_hex(12)
    write(
        MARKER,
        json.dumps({"version": version, "lineage": lineage, "install": "STAGED"})
        + "\n",
    )
    sysusers = (destination / "support/websentinel-https.sysusers").read_text()
    for name in ("student", "sensor", "security"):
        sysusers += f'u websentinel-{name} - "WebSentinel Beta {name}" /nonexistent /usr/sbin/nologin\n'
    SYSUSERS.parent.mkdir(mode=0o755, exist_ok=True)
    write(SYSUSERS, sysusers, 0o644)
    run("systemd-sysusers", str(SYSUSERS))
    uid = shutil._get_uid("websentinel-edge")
    gid = shutil._get_gid("websentinel-evidence")
    edge_gid = shutil._get_gid("websentinel-edge")
    STATE.mkdir(mode=0o711)
    STATE.chmod(0o711)
    for kind, owner in (
        ("edge", 0),
        ("sensor", shutil._get_uid("websentinel-sensor")),
        ("student", shutil._get_uid("websentinel-student")),
    ):
        directory = STATE / kind
        directory.mkdir(mode=0o750)
        os.chown(directory, owner, gid)
        directory.chmod(0o2750 if kind == "student" else 0o750)
    audit = STATE / "student/audit.jsonl"
    audit.touch()
    os.chown(audit, shutil._get_uid("websentinel-student"), gid)
    audit.chmod(0o640)
    # The Rust watcher enumerates rotations. Only its UID may list this directory.
    # The scorer's SQLite state remains in its private 0700 child.
    scorer_state = Path(profile.SCORER_STATE)
    scorer_state.mkdir(mode=0o750)
    os.chown(scorer_state, shutil._get_uid("websentinel-scorer"), shutil._get_gid("websentinel-scorer"))
    run("setfacl", "-m", "g::---,u:websentinel-security:r-x", scorer_state)
    java_dir = STATE / "java"
    java_dir.mkdir(mode=0o700)
    runtime = java_dir / "lib"
    student_deps.install(
        SOURCE / "student/dependencies.json", args.student_cache, runtime
    )
    java_dir.chmod(0o755)
    access = STATE / "edge/access.jsonl"
    access.touch(mode=0o640)
    os.chown(access, 0, gid)
    access.chmod(0o640)
    if uid == 0 or edge_gid == gid:
        raise RuntimeError("Service identities overlap")
    for item, origin in (
        ("edge.crt", args.cert),
        ("edge.key", args.key),
        ("edge-ca.crt", args.ca),
    ):
        shutil.copyfile(origin, CONFIG / item)
        (CONFIG / item).chmod(0o600)
    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:3072",
        "-noenc",
        "-days",
        "365",
        "-subj",
        "/CN=student.internal",
        "-addext",
        "subjectAltName=DNS:student.internal",
        "-addext",
        "extendedKeyUsage=serverAuth",
        "-out",
        CONFIG / "origin.crt",
        "-keyout",
        CONFIG / "origin.key",
    )
    # Only the dedicated NGINX UID may traverse this directory to read the signing material.
    run("setfacl", "-m", f"u:{uid}:--x", CONFIG)
    run("setfacl", "-m", "u:websentinel-sensor:--x", CONFIG)
    write(CONFIG / "nginx.conf", profile.nginx(edge_gid))
    write(CONFIG / "suricata.yaml", profile.sensor(), 0o644)
    passwords = {db: secrets.token_hex(24) for db in DATABASES}
    for db, role in DATABASES.items():
        psql(
            f"SET password_encryption='scram-sha-256'; CREATE ROLE {role} LOGIN PASSWORD '{passwords[db]}';"
        )
        psql(f"CREATE DATABASE {db} OWNER {role};")
        psql(f"REVOKE CONNECT ON DATABASE {db} FROM PUBLIC;")
    write(
        CONFIG / "student.env",
        f"""DB_URL=jdbc:postgresql://127.0.0.1:5432/websentinel_student
DB_USERNAME=websentinel_student
DB_PASSWORD={passwords["websentinel_student"]}
SESSION_COOKIE_SECURE=true
PUBLIC_APP_URL=https://127.0.0.1
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD={student_pw}
STUDENT_SOURCE_INSTANCE={lineage}
STUDENT_AUDIT_LOG_PATH={STATE}/student/audit.jsonl
STUDENT_AUDIT_LOG_GROUP_READABLE=true
STUDENT_AUDIT_HMAC_KEY={secrets.token_hex(32)}
""",
    )
    write(
        CONFIG / "security.env",
        f"""DATABASE_URL=postgresql://websentinel_security:{passwords["websentinel_security"]}@127.0.0.1:5432/websentinel_security
ADMIN_PASSWORD_HASH={admin_hash}
APP_ADDR=127.0.0.1:3000
ENFORCEMENT_MODE=OFF
AUTO_BLOCK=false
PBL4_FIREWALL_CMD=/bin/false
COLLECT_ALL_EVENTS=true
NGINX_ACCESS_PATH={STATE}/edge/access.jsonl
SURICATA_EVE_PATH={STATE}/sensor/eve.json
SURICATA_LUA_PATH={STATE}/sensor/chain.tsv
STUDENT_AUDIT_LOG_PATH={STATE}/student/audit.jsonl
AI_HTTPS_RESULTS_PATH={profile.SCORER_STATE}/observations.jsonl
SURICATA_CAPTURE_MODE=post-proxy
SURICATA_POST_PROXY_INTERFACE=lo
SURICATA_EVE_GENERATION_HOST=true
SURICATA_PROXY_IP=127.77.0.1
SURICATA_WEB_IP=127.77.0.2
SURICATA_WEB_PORT=18080
""",
    )
    write(
        CONFIG / "scorer.env",
        f"MODEL_SLOT=candidate\nRELEASE_SHA256={digest(destination / 'scorer/files.json')}\nEVIDENCE_LINEAGE={lineage}\n",
    )
    for name, data in profile.units().items():
        write(SYSTEM / name, data, 0o644)
    run("systemd-analyze", "verify", *(SYSTEM / unit for unit in UNITS))
    run("systemctl", "daemon-reload")
    control("start", UNITS)

    def initialized():
        scorer = run("systemctl", "show", UNITS[0], "-p", "ExecMainStatus", "--value")
        if scorer == "78":
            raise RuntimeError(
                "Scorer safety refusal (exit 78). See the system journal for the admission predicate."
            )
        return health() is None

    cgroup_wait(initialized, 150)
    env = CONFIG / "student.env"
    write(
        env,
        "\n".join(
            line
            for line in env.read_text().splitlines()
            if not line.startswith(
                ("BOOTSTRAP_ADMIN_ENABLED=", "BOOTSTRAP_ADMIN_PASSWORD=")
            )
        )
        + "\n",
    )
    control("enable", UNITS)
    write(
        MARKER,
        json.dumps({"version": version, "lineage": lineage, "install": "HEALTHY"})
        + "\n",
    )


def rollback_model(slot):
    path = CONFIG / "scorer.env"
    old = path.read_text()
    write(path, re.sub(r"(?m)^MODEL_SLOT=.*$", f"MODEL_SLOT={slot}", old))
    try:
        control("restart", UNITS[:1])
        cgroup_wait(lambda: health() is None, 15)
    except Exception:
        write(path, old)
        control("restart", UNITS[:1])
        raise


def backup(destination):
    destination.mkdir(mode=0o700, exist_ok=False)
    for db in DATABASES:
        with (destination / (db + ".dump")).open("xb") as stream:
            subprocess.run(
                ["runuser", "-u", "postgres", "--", "pg_dump", "-Fc", db],
                stdout=stream,
                check=True,
                timeout=120,
            )
    state_db = Path(profile.SCORER_STATE) / "private/receipts.db"
    if state_db.exists():
        with (
            sqlite3.connect(state_db.as_uri() + "?mode=ro", uri=True) as src,
            sqlite3.connect(destination / "receipts.db") as dst,
        ):
            src.backup(dst)
            if dst.execute("pragma quick_check").fetchone() != ("ok",):
                raise RuntimeError("Receipt backup integrity failure")
    entries = sorted(destination.iterdir())
    write(
        destination / "SHA256SUMS", "".join(f"{digest(p)}  {p.name}\n" for p in entries)
    )


def restore_test(backup_path, suffix):
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,18}", suffix):
        raise ValueError("Use a new short ASCII restore suffix")
    if psql(
        "select 1 from pg_database where datname in ("
        + ",".join(f"'{db}_{suffix}'" for db in DATABASES)
        + ");"
    ):
        raise RuntimeError("Restore destination already exists")
    checksums = dict(
        line.split("  ", 1)[::-1]
        for line in (backup_path / "SHA256SUMS").read_text().splitlines()
    )
    for db in DATABASES:
        path = backup_path / (db + ".dump")
        if digest(path) != checksums[path.name]:
            raise RuntimeError("Backup SHA mismatch")
    for db, role in DATABASES.items():
        psql(f"CREATE DATABASE {db}_{suffix} OWNER {role};")
        psql(f"REVOKE CONNECT ON DATABASE {db}_{suffix} FROM PUBLIC;")
        with (backup_path / (db + ".dump")).open("rb") as stream:
            subprocess.run(
                [
                    "runuser",
                    "-u",
                    "postgres",
                    "--",
                    "pg_restore",
                    "--exit-on-error",
                    "--single-transaction",
                    "-d",
                    f"{db}_{suffix}",
                ],
                stdin=stream,
                check=True,
                timeout=120,
            )


def uninstall():
    control("stop", UNITS[::-1])
    control("disable", UNITS)
    for unit in UNITS:
        (SYSTEM / unit).unlink(missing_ok=True)
    run("systemctl", "daemon-reload")
    print(
        "Dịch vụ đã dừng. Bản cài, dữ liệu, cấu hình và deny-only guard được lưu để phục hồi."
    )


def main():
    os.umask(0o077)
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    for name in (
        "verify",
        "preflight",
        "health",
        "start",
        "stop",
        "restart",
        "uninstall",
    ):
        sub.add_parser(name)
    sub.add_parser("hardware-check")
    sub.add_parser("fetch-student-deps").add_argument("directory", type=Path)
    stage = sub.add_parser("install")
    stage.add_argument("--student-cache", type=Path, required=True)
    for name in ("cert", "key", "ca"):
        stage.add_argument("--" + name, type=Path, required=True)
    for name in ("student-password-file", "security-password-file"):
        stage.add_argument("--" + name, type=Path)
    sub.add_parser("model").add_argument("slot", choices=["candidate", "rollback"])
    sub.add_parser("backup").add_argument("directory", type=Path)
    restore = sub.add_parser("restore-test")
    restore.add_argument("directory", type=Path)
    restore.add_argument("suffix")
    sub.add_parser("request").add_argument("request_id")
    args = cli.parse_args()
    if args.action == "verify":
        print(json.dumps(verify(SOURCE)))
        return
    if args.action == "hardware-check":
        verify(SOURCE)
        print(json.dumps(hardware_check()))
        return
    if args.action == "fetch-student-deps":
        verify(SOURCE)
        student_deps.fetch(SOURCE / "student/dependencies.json", args.directory)
        return
    require_root()
    if args.action == "preflight":
        preflight()
        return
    if args.action == "install":
        install(args)
        return
    if not MARKER.is_file():
        raise RuntimeError("No owned beta installation")
    if args.action in ("start", "stop", "restart"):
        control(args.action, UNITS[::-1] if args.action == "stop" else UNITS)
    elif args.action == "health":
        health()
    elif args.action == "model":
        rollback_model(args.slot)
    elif args.action == "backup":
        backup(args.directory)
    elif args.action == "restore-test":
        restore_test(args.directory, args.suffix)
    elif args.action == "request":
        if not re.fullmatch(r"[a-f0-9]{32}", args.request_id):
            raise ValueError("Expected a trusted 32-hex request ID")
        decision = psql(
            "select json_build_object('request_id', request_id, 'policy', decision->>'policy_action', "
            "'research', decision->'https_research', 'automatic_block', decision->'automatic_block') "
            f"from hybrid_incidents where request_id='{args.request_id}';",
            "websentinel_security",
        )
        print(
            decision
            or json.dumps({"request_id": args.request_id, "status": "NOT_INGESTED"})
        )
    elif args.action == "uninstall":
        uninstall()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        # Child command output is not echoed because the DB or service may log secrets.
        print(f"Beta {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

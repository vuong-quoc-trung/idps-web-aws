"""Update the pinned R47 AWS staging deployment without replacing its databases."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import gateway

R47 = Path("/etc/websentinel-r47")
ACTIVE = Path("/opt/websentinel-r47/current")
R47_REVISION = "8265ea07e0d481879807b607d1ac7fc93be17ee8"
R47_GATEWAY = "f982d177ee8eef0bdb073fb225421cc5edbf7b55610e1a3efd94988896e4d87f"
CONFIG = Path("/etc/websentinel-r48")
STATE = Path("/var/lib/websentinel-r48")
KIT = Path("/opt/websentinel-r48/runtime")
SYSTEM = Path("/etc/systemd/system")
SITE = Path("/etc/nginx/conf.d/websentinel-staging.conf")
KEY = Path("/run/websentinel-r48-key/secret/key.json")
SCORER_SOCKET = Path("/run/websentinel-r47-scorer/receiver.sock")
SEC = "websentinel-r47-security.service"
STUDENT = "websentinel-r47-student.service"
SCORE = "websentinel-r47-scorer.service"
SENSOR = "websentinel-r48-sensor.service"
CORR = "websentinel-r48-correlator.service"
ROTATE = "websentinel-r48-rotate.timer"
KEY_UNIT = "websentinel-r48-key.service"
EDGE_UNIT = SYSTEM / "nginx.service.d/48-proof-key.conf"
SCORE_LIMIT = SYSTEM / (SCORE + ".d/48-receipt-size.conf")
STUDENT_READY = SYSTEM / (STUDENT + ".d/48-readiness.conf")
AUDIT = Path("/var/lib/websentinel-r47/student/audit.jsonl")
ENV = R47 / "security.env"
UNITS = [SENSOR, CORR, ROTATE]
FILES = ("gateway.py", "correlate.py", "update.py", "proof-probe.js",
         "https-shadow-mirror.conf", "transaction-evidence.lua",
         "run-suricata-generation.py", "pbl4.rules", "pbl4-access.conf")
DB_FILES = {
    "ws_r47_student": ("flyway_schema_history", 2),
    "ws_r47_security": ("_sqlx_migrations", 20),
}


def boot_dropins():
    return {
        EDGE_UNIT: f"[Unit]\nRequires={KEY_UNIT}\nAfter={KEY_UNIT} {STUDENT}\n",
        STUDENT_READY: ("[Service]\nTimeoutStartSec=155s\n"
                       f"ExecStartPost=/usr/bin/python3 -B {KIT}/update.py student-ready\n"),
    }


def student_ready():
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 145
    while time.monotonic() < deadline:
        try:
            with client.open("http://127.0.0.1:8080/api/auth/csrf", timeout=2) as response:
                if response.status == 200 and response.headers.get("Set-Cookie"):
                    return
        except OSError:
            pass
        time.sleep(0.7)
    raise RuntimeError("Student HTTPS upstream did not become ready")


def run(*args, timeout=35, check=True, stdout=None, cwd=None):
    output = subprocess.run(list(map(str, args)), check=check, text=True, timeout=timeout,
                            stdout=stdout if stdout is not None else subprocess.PIPE, cwd=cwd)
    return output.stdout.strip() if output.stdout else ""


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def replace(path, content, mode=0o600, gid=0):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(content.encode() if isinstance(content, str) else content)
            f.flush()
            os.fchown(f.fileno(), 0, gid)
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def secure_dir(path, uid, gid, mode):
    path.mkdir(mode=mode)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def rotate_key():
    group = pwd.getpwnam("www-data").pw_gid
    if not KEY.parent.exists():
        secure_dir(KEY.parent, 0, group, 0o750)
    st = KEY.parent.lstat()
    if not KEY.parent.is_dir() or KEY.parent.is_symlink() or st.st_uid != 0 or st.st_gid != group:
        raise RuntimeError("Unsafe proof key directory")
    run("setfacl", "-m", "u:ws-r48-correlator:--x", KEY.parent)
    # Prepare the ACL before replacing the live file so a concurrent verifier
    # either reads the preceding epoch or the fully permissioned new epoch.
    candidate = KEY.with_name("key.new")
    replace(candidate, json.dumps({
        "kid": secrets.token_hex(8), "epoch": secrets.token_hex(16), "key": secrets.token_hex(32)
    }), 0o640, group)
    run("setfacl", "-m", "u:ws-r48-correlator:r--", candidate)
    candidate.replace(KEY)


def units():
    return {
        KEY_UNIT: f"""[Unit]
Description=WebSentinel proof key for the active gateway epoch
PartOf=nginx.service
Before=nginx.service

[Service]
Type=oneshot
RemainAfterExit=yes
RuntimeDirectory=websentinel-r48-key
RuntimeDirectoryMode=0755
ExecStart=/usr/bin/python3 -B {KIT}/update.py key
""",
        SENSOR: f"""[Unit]
Description=WebSentinel passive Suricata on the private TLS egress leg
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=exec
Slice=websentinelr47.slice
User=ws-r48-sensor
Group=ws-r47-evidence
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
ExecStart=/usr/bin/python3 -IB {KIT}/run-suricata-generation.py -c {CONFIG}/suricata.yaml --af-packet=lo --runmode single
ReadWritePaths={STATE}/sensor
CPUQuota=25%
MemoryHigh=288M
MemoryMax=384M
MemorySwapMax=0
TasksMax=48
LimitFSIZE=64M
LimitCORE=0
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
PrivateTmp=yes
UMask=0027
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=multi-user.target
""",
        CORR: f"""[Unit]
Description=WebSentinel observe-only signed request correlation
After={KEY_UNIT} {SENSOR}
Wants={KEY_UNIT} {SENSOR}
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=exec
Slice=websentinelr47.slice
User=ws-r48-correlator
Group=ws-r47-evidence
ExecStart=/usr/bin/python3 -B {KIT}/correlate.py --key {KEY} --output {STATE}/proof/correlation.jsonl {STATE}/edge/access.jsonl {STATE}/sensor/chain.tsv {STATE}/sensor/eve.json {AUDIT}
ReadWritePaths={STATE}/proof
CPUQuota=10%
MemoryMax=96M
MemorySwapMax=0
TasksMax=12
LimitFSIZE=64M
LimitCORE=0
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX
UMask=0027
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=multi-user.target
""",
        "websentinel-r48-rotate.service": f"""[Unit]
Description=Rotate owned WebSentinel observation files

[Service]
Type=oneshot
ExecStart=/usr/sbin/logrotate -s {STATE}/logrotate.state {CONFIG}/logrotate.conf
""",
        ROTATE: """[Unit]
Description=Bound WebSentinel cloud observation log size

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
""",
    }


def logrotate():
    def target(paths, owner, hook=""):
        return f"""{' '.join(map(str, paths))} {{
    daily
    maxsize 8M
    rotate 3
    missingok
    notifempty
    nocompress
    create 0640 {owner} ws-r47-evidence
{hook}}}
"""
    return (
        target([STATE / "edge/access.jsonl"], "www-data",
               "    postrotate\n        systemctl kill --kill-whom=main --signal=USR1 nginx.service\n    endscript\n")
        + target([AUDIT], "ws-r47-student")
        + target([STATE / "proof/correlation.jsonl"], "ws-r48-correlator")
        + target([STATE / "sensor/eve.json", STATE / "sensor/chain.tsv"], "ws-r48-sensor",
                 f"    sharedscripts\n    postrotate\n        systemctl try-restart {SENSOR}\n    endscript\n")
    )


def check_host():
    if os.geteuid() != 0 or ACTIVE.resolve().name != R47_REVISION:
        raise RuntimeError("Expected the installed R47 source revision")
    sys.path.insert(0, str(ACTIVE))
    import cloud_profile as cloud
    identity = cloud.protected_json(R47 / "cloud-identity.json")
    cloud.verify_identity(cloud.metadata_identity(), identity,
                          Path("/sys/class/dmi/id/sys_vendor").read_text().strip())
    if sha(SITE) != R47_GATEWAY:
        raise RuntimeError("Expected the R47 gateway checksum")
    text = ENV.read_text()
    for field in ("ENFORCEMENT_MODE=OFF", "AUTO_BLOCK=false", "PBL4_FIREWALL_CMD=/bin/false"):
        if [line for line in text.splitlines() if line.startswith(field.split("=")[0] + "=")] != [field]:
            raise RuntimeError("The deployment must remain observation-only")
    if run("systemctl", "is-active", "suricata.service", check=False) != "inactive":
        raise RuntimeError("The distro sensor is already active")
    if shutil.disk_usage("/var/lib").free < 3 * 1024**3:
        raise RuntimeError("Insufficient rollback and runtime disk headroom")
    for db, (table, count) in DB_FILES.items():
        value = run("runuser", "-u", "postgres", "--", "psql", "-At", "-d", db,
                    "-c", f"select count(*) from {table} where success")
        if value != str(count):
            raise RuntimeError("Unexpected migration state")


def backup(destination):
    destination.mkdir(mode=0o700, exist_ok=False)
    sources = {"nginx.conf": SITE, "security.env": ENV, "student.env": R47 / "student.env",
               "scorer.env": R47 / "scorer.env"}
    for name, origin in sources.items():
        replace(destination / name, origin.read_bytes())
    for db in DB_FILES:
        path = destination / f"{db}.dump"
        with path.open("xb") as stream:
            run("runuser", "-u", "postgres", "--", "pg_dump", "-Fc", db, stdout=stream)
        run("pg_restore", "--list", path)
    run("tar", "-czf", destination / "active-release.tgz", "-C", ACTIVE.resolve().parent,
        ACTIVE.resolve().name, timeout=100)
    replace(destination / "SHA256SUMS", "".join(f"{sha(p)}  {p.name}\n" for p in sorted(destination.iterdir())))


def setup(source):
    manifest = json.loads((source / "SHA256SUMS.json").read_text())
    if set(manifest) != set(FILES) or any(not (source / p).is_file()
            or (source / p).is_symlink() or sha(source / p) != manifest[p] for p in FILES):
        raise ValueError("Staged kit checksum failed")
    if any(p.exists() for p in (CONFIG, STATE, KIT.parent, EDGE_UNIT, SCORE_LIMIT, STUDENT_READY,
                                *(SYSTEM / name for name in units()))):
        raise RuntimeError("Existing R48 paths require reviewed rollback or update")
    # The update service deliberately runs with umask 0077. The owners of the
    # passive workers still need to traverse their root-owned runtime paths.
    secure_dir(KIT.parent, 0, 0, 0o755)
    secure_dir(KIT, 0, 0, 0o755)
    secure_dir(CONFIG, 0, 0, 0o755)
    secure_dir(STATE, 0, 0, 0o751)
    for name in FILES:
        replace(KIT / name, (source / name).read_bytes(), 0o644)
    replace(CONFIG / "sysusers.conf",
            'u ws-r48-sensor -:ws-r47-evidence "Cloud sensor" /nonexistent /usr/sbin/nologin\n'
            'u ws-r48-correlator -:ws-r47-evidence "Cloud correlator" /nonexistent /usr/sbin/nologin\n')
    run("systemd-sysusers", CONFIG / "sysusers.conf")
    sensor = pwd.getpwnam("ws-r48-sensor")
    corr = pwd.getpwnam("ws-r48-correlator")
    # NGINX workers run as www-data, outside the collector group. They need
    # traversal to reopen the access log on USR1; log contents stay at 0640.
    secure_dir(STATE / "edge", 0, corr.pw_gid, 0o751)
    for name, uid in (("sensor", sensor.pw_uid), ("proof", corr.pw_uid)):
        secure_dir(STATE / name, uid, corr.pw_gid, 0o750)
    for path, uid in ((STATE / "edge/access.jsonl", pwd.getpwnam("www-data").pw_uid),
                       (STATE / "proof/correlation.jsonl", corr.pw_uid),
                       (STATE / "sensor/eve.json", sensor.pw_uid),
                       (STATE / "sensor/chain.tsv", sensor.pw_uid)):
        replace(path, "", 0o640, corr.pw_gid)
        os.chown(path, uid, corr.pw_gid)
    replace(CONFIG / "suricata.yaml", gateway.sensor_config(KIT, STATE / "sensor"), 0o644)
    replace(CONFIG / "logrotate.conf", logrotate(), 0o644)


def verify_active():
    target = "91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff"
    for _ in range(30):
        for unit in (SEC, SCORE, SENSOR, CORR):
            if run("systemctl", "is-active", unit, check=False) != "active":
                break
        else:
            read = subprocess.run(["runuser", "-u", "www-data", "--", "curl", "-fsSi",
                "--max-time", "3", "--unix-socket", str(SCORER_SOCKET), "http://localhost/healthz"],
                capture_output=True, text=True, timeout=5)
            if read.returncode == 0 and f"X-Model-SHA256: {target}" in read.stdout.splitlines():
                with urllib.request.urlopen("http://127.0.0.1:3000/health", timeout=3) as r:
                    if r.status == 200:
                        return
        time.sleep(0.5)
    raise RuntimeError("Cloud beta service readiness failed")


def rollback(snapshot):
    run("sha256sum", "--check", snapshot / "SHA256SUMS", timeout=50,
        stdout=subprocess.DEVNULL, cwd=snapshot)
    replace(SITE, (snapshot / "nginx.conf").read_bytes(), 0o644)
    replace(ENV, (snapshot / "security.env").read_bytes())
    EDGE_UNIT.unlink(missing_ok=True)
    SCORE_LIMIT.unlink(missing_ok=True)
    STUDENT_READY.unlink(missing_ok=True)
    run("systemctl", "disable", "--now", *UNITS, check=False)
    run("systemctl", "daemon-reload")
    run("nginx", "-t")
    run("systemctl", "reload", "nginx")
    run("systemctl", "stop", KEY_UNIT, check=False)
    run("systemctl", "restart", SEC, SCORE)


def update(source, snapshot):
    check_host()
    setup(source)
    backup(snapshot)
    old = SITE.read_text()
    try:
        for name, code in units().items():
            replace(SYSTEM / name, code, 0o644)
        for path, content in (boot_dropins() | {
            SCORE_LIMIT: "[Service]\nLimitFSIZE=128M\nLimitCORE=0\n",
        }).items():
            path.parent.mkdir(exist_ok=True, mode=0o755)
            replace(path, content, 0o644)
        run("systemd-analyze", "verify", *(SYSTEM / p for p in units()))
        run("systemctl", "daemon-reload")
        # Test sensor configuration without opening the active output files.
        run("suricata", "-T", "-c", CONFIG / "suricata.yaml", "-l", snapshot)
        env = ENV.read_text()
        remove = {"NGINX_ACCESS_PATH", "SURICATA_EVE_PATH"}
        filtered = [line for line in env.splitlines() if line.partition("=")[0] not in remove]
        replace(ENV, "\n".join(filtered) + f"""
COLLECT_ALL_EVENTS=true
NGINX_ACCESS_PATH={STATE}/edge/access.jsonl
SURICATA_EVE_PATH={STATE}/sensor/eve.json
SURICATA_LUA_PATH={STATE}/sensor/chain.tsv
THREE_SOURCE_RESULTS_PATH={STATE}/proof/correlation.jsonl
SURICATA_CAPTURE_MODE=post-proxy
SURICATA_POST_PROXY_INTERFACE=lo
SURICATA_PROXY_IP={gateway.SOURCE}
SURICATA_WEB_IP={gateway.EGRESS}
SURICATA_WEB_PORT={gateway.PORT}
SURICATA_EVE_GENERATION_HOST=true
SURICATA_TRUSTED_EDGE_CONFIRMED=false
""")
        run("systemctl", "start", KEY_UNIT, SENSOR, CORR)
        run("systemctl", "restart", SEC, SCORE)
        verify_active()
        replace(SITE, gateway.render(old, KIT, KEY, pwd.getpwnam("www-data").pw_gid,
                                    STATE / "edge/access.jsonl", SCORER_SOCKET), 0o644)
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        run("systemctl", "enable", "--now", *UNITS)
        print(json.dumps({"stage": "R48_RUNTIME_INSTALLED", "gateway_sha256": sha(SITE),
                          "backup_sha256": sha(snapshot / "SHA256SUMS"), "enforcement": "OFF"}))
    except Exception:
        rollback(snapshot)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("update", "rollback", "key", "student-ready"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--backup", type=Path, default=Path("/var/backups/websentinel-r48"))
    args = parser.parse_args()
    if args.action == "key":
        rotate_key()
    elif args.action == "student-ready":
        student_ready()
    elif args.action == "rollback":
        rollback(args.backup)
    elif args.bundle is None:
        parser.error("--bundle is required for update")
    else:
        update(args.bundle.resolve(strict=True), args.backup)

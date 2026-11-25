"""Install the initial observation-only AWS staging release on the verified EC2."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import cloud_profile as cloud

CONFIG = Path("/etc/websentinel-r47")
CURRENT = Path("/opt/websentinel-r47/current")
STATE = Path("/var/lib/websentinel-r47")
NGINX = Path("/etc/nginx/conf.d/websentinel-staging.conf")
SYSTEMD = Path("/etc/systemd/system")
R46_SHA = "22e4c12faaff75f2d012804dad5252b06fff460f95167dd38bc6da9d0b7af349"
SLICE = "websentinelr47.slice"
STUDENT = "websentinel-r47-student.service"
SECURITY = "websentinel-r47-security.service"
SCORER = "websentinel-r47-scorer.service"
ADMISSION = "websentinel-r47-admission.service"
DB = "postgresql@18-main.service"
UNITS = [STUDENT, SECURITY, SCORER]


def run(*args, input_text=None, timeout=40, check=True):
    return subprocess.run(
        list(map(str, args)), input=input_text, text=True, stdout=subprocess.PIPE,
        timeout=timeout, check=check,
    ).stdout.strip()


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write(path, text, mode=0o600):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w") as f:
        f.write(text)
        f.flush()
        os.fchmod(f.fileno(), mode)
        os.link(f.name, path)


def replace_gateway(text):
    with tempfile.NamedTemporaryFile(dir=NGINX.parent, mode="w", delete=False) as f:
        p = Path(f.name)
        try:
            f.write(text)
            f.flush()
            os.fchmod(f.fileno(), 0o644)
            p.replace(NGINX)
        finally:
            p.unlink(missing_ok=True)


def startup_check(release, revision):
    manifest = json.loads((release / "r47-files.json").read_text())
    for path, expected in manifest.items():
        p = release / path
        if not p.is_relative_to(release) or p.resolve() != p or sha(p) != expected:
            raise ValueError("Bundle digest mismatch")
    if not re.fullmatch("[0-9a-f]{40}", revision) or sha(NGINX) != R46_SHA:
        raise ValueError("Unexpected revision or existing R46 gateway configuration")
    if any(path.exists() for path in (CONFIG, CURRENT.parent, STATE, *(SYSTEMD / u for u in UNITS + [ADMISSION, SLICE]))):
        raise ValueError("Existing staged objects require a reviewed update")
    addresses = run("runuser", "-u", "postgres", "--", "psql", "-Atc", "show listen_addresses")
    if addresses not in ("localhost", "127.0.0.1"):
        raise ValueError("Database is not restricted to localhost")


def dbsetup(role, password):
    known = run("runuser", "-u", "postgres", "--", "psql", "-Atc",
                f"select 1 from pg_roles where rolname='{role}' union all select 1 from pg_database where datname='{role}'")
    if known:
        raise ValueError("An existing database or role overlaps the first deploy")
    run("runuser", "-u", "postgres", "--", "psql", "-q", "-v", "ON_ERROR_STOP=1",
        input_text=f"""SET password_encryption='scram-sha-256';
CREATE ROLE {role} LOGIN PASSWORD '{password}';
CREATE DATABASE {role} OWNER {role};
REVOKE CONNECT ON DATABASE {role} FROM PUBLIC;
""")


def service(user, description, env, command, memory, cpu, tasks, writable, extra=""):
    return f"""[Unit]
Description={description}
After=network.target {DB}
Requires={DB}
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=exec
Slice={SLICE}
User={user}
Group=ws-r47-evidence
EnvironmentFile={CONFIG}/{env}.env
ExecStart={command}
CPUQuota={cpu}%
MemoryHigh={int(memory * .8)}M
MemoryMax={memory}M
MemorySwapMax=0
TasksMax={tasks}
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
UMask=0077
KillMode=control-group
Restart=on-failure
RestartPreventExitStatus=78
RestartSec=3s
TimeoutStopSec=15s
{writable}
{extra}
[Install]
WantedBy=multi-user.target
"""


def units():
    p = CURRENT
    return {
        SLICE: """[Unit]
Description=WebSentinel AWS staging applications

[Slice]
CPUQuota=150%
MemoryHigh=5632M
MemoryMax=6144M
MemorySwapMax=0
TasksMax=512
""",
        ADMISSION: f"""[Unit]
Description=WebSentinel Cloud resource profile admission
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
RuntimeDirectory=websentinel-r47-cloud
RuntimeDirectoryMode=0755
ExecStart=/usr/bin/python3 -IB {p}/cloud_profile.py attest
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
RestrictAddressFamilies=AF_INET AF_UNIX
IPAddressDeny=any
IPAddressAllow=169.254.169.254/32
""",
        STUDENT: service("ws-r47-student", "Student Web AWS staging", "student",
                         f"/usr/bin/java -XX:ActiveProcessorCount=2 -Xmx512m -jar {p}/student.jar",
                         1536, 40, 160, f"ReadWritePaths={STATE}/student"),
        SECURITY: service("ws-r47-security", "Security Web observation AWS staging", "security",
                          f"{p}/security/pbl4-security-demo", 512, 15, 64, "",
                          f"""WorkingDirectory={p}/security
LogRateLimitIntervalSec=30s
LogRateLimitBurst=30"""),
        SCORER: service(
            "ws-r47-scorer", "Pinned R37 scorer under AWS resource guardian", "scorer",
            f"/usr/bin/python3 -IB {p}/cloud_profile.py run --release {p}/scorer",
            768, 25, 64, "",
            f"""RuntimeDirectory=websentinel-r47-scorer
RuntimeDirectoryMode=0711
StateDirectory=websentinel-r47-scorer
StateDirectoryMode=0750
NotifyAccess=main
WatchdogSec=3s
RestrictAddressFamilies=AF_UNIX
[Unit]
After={ADMISSION}
Requires={ADMISSION}
""",
        ).replace("MemoryHigh=614M", "MemoryHigh=608M"),
        f"{DB}.d/40-websentinel-r47.conf": f"""[Service]
Slice={SLICE}
CPUQuota=25%
MemoryHigh=1228M
MemoryMax=1536M
MemorySwapMax=0
TasksMax=96
""",
    }


def gateway(base):
    student = r"""    add_header X-Request-Id $request_id always;
    root /opt/websentinel-r47/current/student-ui;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Request-Id $request_id;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_hide_header X-Request-Id;
    }"""
    security = r"""    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Request-Id $request_id;
        proxy_set_header X-Forwarded-For "";
        proxy_buffering off;
        proxy_read_timeout 75s;
        client_max_body_size 16k;
    }"""
    for label, substitution in (("STUDENT DUT", student), ("WEBSENTINAL", security)):
        find = ('    location = / {\n        default_type text/plain;\n'
                f'        return 200 "{label} — AWS STAGING\\n";\n'
                '    }\n\n    location / {\n        return 404;\n    }')
        if base.count(find) != 1:
            raise ValueError("R46 virtual host placeholder no longer matches")
        base = base.replace(find, substitution)
    return base


def wait(url):
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    until = time.monotonic() + 120
    while time.monotonic() < until:
        try:
            with client.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Readiness timeout: {url}")


def scorer_health(release):
    expected = json.loads((release / "scorer/ai-training/contracts/quality-freeze-r37/slots.json").read_text())
    target = expected["slots"]["candidate"]["sha256"]
    until = time.monotonic() + 35
    while time.monotonic() < until:
        p = subprocess.run(
            ["runuser", "-u", "www-data", "--", "curl", "-fsSi", "--max-time", "3",
             "--unix-socket", "/run/websentinel-r47-scorer/receiver.sock", "http://localhost/healthz"],
            capture_output=True, text=True, timeout=5,
        )
        if p.returncode == 0 and f"x-model-sha256: {target}" in p.stdout.lower().splitlines():
            return target
        time.sleep(1)
    return None


def deploy(source, revision, identity):
    if os.geteuid() != 0:
        raise PermissionError("System installation needs root")
    vendor = Path("/sys/class/dmi/id/sys_vendor").read_text().strip()
    cloud.verify_identity(cloud.metadata_identity(), identity, vendor)
    startup_check(source, revision)
    base = NGINX.read_text()
    candidate = gateway(base)
    CONFIG.mkdir(mode=0o755)
    write(CONFIG / "cloud-identity.json", json.dumps(identity), 0o644)
    write(CONFIG / "nginx-r46.backup", base)
    release = CURRENT.parent / "releases" / revision
    release.parent.mkdir(parents=True, mode=0o755)
    shutil.copytree(source, release)
    for p in [release, *release.rglob("*")]:
        if p.is_symlink():
            raise ValueError("Symlinks are not allowed in the release bundle")
        access = p.is_dir() or p.name in {"pbl4-security-demo", "scorer"}
        p.chmod(0o755 if access else 0o644)
    CURRENT.symlink_to(release)
    users = """g ws-r47-evidence -
u ws-r47-student -:ws-r47-evidence "Student staging" /nonexistent /usr/sbin/nologin
u ws-r47-security -:ws-r47-evidence "Security staging" /nonexistent /usr/sbin/nologin
u ws-r47-scorer -:ws-r47-evidence "Scorer staging" /nonexistent /usr/sbin/nologin
"""
    write(CONFIG / "sysusers.conf", users)
    run("systemd-sysusers", CONFIG / "sysusers.conf")
    STATE.mkdir(mode=0o751)
    (STATE / "student").mkdir(mode=0o2750)
    run("chown", "ws-r47-student:ws-r47-evidence", STATE / "student")
    (STATE / "student").chmod(0o2750)
    audit = STATE / "student/audit.jsonl"
    write(audit, "", 0o640)
    run("chown", "ws-r47-student:ws-r47-evidence", audit)
    sd, rd, student_pw, admin_pw = (secrets.token_hex(24) for _ in range(4))
    admin_hash = run(CURRENT / "security/pbl4-security-demo", "--hash-password",
                     input_text=admin_pw + "\n")
    write(CONFIG / "admin-bootstrap.json", json.dumps({"student":student_pw,"security":admin_pw}))
    dbsetup("ws_r47_student", sd)
    dbsetup("ws_r47_security", rd)
    write(CONFIG / "student.env", f"""DB_URL=jdbc:postgresql://127.0.0.1:5432/ws_r47_student
DB_USERNAME=ws_r47_student
DB_PASSWORD={sd}
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=4
SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE=1
SESSION_COOKIE_SECURE=true
PUBLIC_APP_URL=https://student-dut.duckdns.org
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD={student_pw}
STUDENT_SOURCE_INSTANCE=aws-r47
STUDENT_AUDIT_LOG_PATH={STATE}/student/audit.jsonl
STUDENT_AUDIT_LOG_GROUP_READABLE=true
STUDENT_AUDIT_HMAC_KEY={secrets.token_hex(32)}
STUDENT_AUDIT_MAX_BYTES=16777216
""")
    write(CONFIG / "security.env", f"""DATABASE_URL=postgresql://ws_r47_security:{rd}@127.0.0.1:5432/ws_r47_security
ADMIN_PASSWORD_HASH='{admin_hash}'
APP_ADDR=127.0.0.1:3000
ENFORCEMENT_MODE=OFF
AUTO_BLOCK=false
PBL4_FIREWALL_CMD=/bin/false
STUDENT_AUDIT_LOG_PATH={STATE}/student/audit.jsonl
NGINX_ACCESS_PATH={STATE}/not-connected/edge.jsonl
SURICATA_EVE_PATH={STATE}/not-connected/eve.json
AI_HTTPS_RESULTS_PATH=/var/lib/websentinel-r47-scorer/observations.jsonl
TOKIO_WORKER_THREADS=2
""")
    write(CONFIG / "scorer.env", f"""MODEL_SLOT=candidate
RELEASE_SHA256={sha(release / "scorer/files.json")}
EVIDENCE_LINEAGE=aws-r47-{revision[:12]}
""")
    for name, content in units().items():
        path = SYSTEMD / name
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path, content, 0o644)
    run("systemctl", "daemon-reload")
    switch = False
    try:
        run("systemd-analyze", "verify", *(SYSTEMD / u for u in UNITS + [ADMISSION, SLICE]))
        run("systemctl", "restart", DB, timeout=90)
        run("systemctl", "start", STUDENT, SECURITY)
        wait("http://127.0.0.1:8080/api/auth/csrf")
        wait("http://127.0.0.1:3000/health")
        run("systemctl", "start", SCORER, check=False)
        model = scorer_health(release)
        if model is None:
            run("systemctl", "stop", SCORER, check=False)
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                "http://127.0.0.1:3000/api/events", timeout=3
            ).close()
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
        else:
            raise RuntimeError("Security evidence endpoint accepted unauthenticated access")
        if sha(NGINX) != R46_SHA:
            raise RuntimeError("Gateway changed during staging")
        raw = (CONFIG / "student.env").read_text()
        clean = "\n".join(line for line in raw.splitlines() if not line.startswith(("BOOTSTRAP_ADMIN_PASSWORD=", "BOOTSTRAP_ADMIN_ENABLED="))) + "\n"
        write(CONFIG / "student-runtime.env", clean)
        (CONFIG / "student-runtime.env").replace(CONFIG / "student.env")
        replace_gateway(candidate)
        switch = True
        run("nginx", "-t")
        run("systemctl", "reload", "nginx.service")
        run("systemctl", "enable", STUDENT, SECURITY, *([SCORER] if model else []))
        print(json.dumps({"revision":revision,"student":True,"security":True,"model_sha":model,
                          "automatic_blocking":False,"full_evidence_chain":False}))
    except Exception:
        if switch:
            replace_gateway(base)
            run("nginx", "-t")
            run("systemctl", "reload", "nginx.service")
        run("systemctl", "stop", *UNITS, check=False)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    deploy(args.bundle.resolve(strict=True), args.revision, {
        "accountId": args.account, "instanceId": args.instance, "region":"ap-southeast-1",
        "instanceType":"m7i-flex.large", "architecture":"x86_64",
    })

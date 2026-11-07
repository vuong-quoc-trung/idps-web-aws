#!/usr/bin/env python3
"""Prepare/install the host-only adapter. No local Student, DB, firewall or SSH."""
import argparse
import datetime
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SERVICE = "pbl4-ai-shadow.service"
SOCKET = "/run/pbl4-ai-shadow/nginx.sock"
JOURNAL = "/var/log/pbl4-ai-shadow/results.jsonl"
UNIT = Path("/etc/systemd/system") / SERVICE
FORMATS = Path("/etc/nginx/conf.d/pbl4-ai-shadow.conf")
MANIFEST_SHA = "b90383c55d943414ba5f185e1779914df163dec81f8b7fcf8f8f6b9ecc0ae96c"


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=180, **kwargs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_check(bundle):
    if sha(bundle / "manifest.json") != MANIFEST_SHA:
        raise RuntimeError("Frozen model manifest mismatch")
    manifest = json.loads((bundle / "manifest.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        file = bundle / name
        if file.is_symlink() or not file.resolve().is_relative_to(bundle.resolve()) or sha(file) != expected:
            raise RuntimeError("Model file integrity mismatch")
    if manifest["model_version"] != "request-intelligence-v2-frozen-step3072" or not manifest["shadow_only"]:
        raise RuntimeError("Model is not the expected frozen shadow model")


def patch_site(text):
    if "# PBL4 AI SHADOW HOST BEGIN" in text:
        required = ["listen 192.168.10.1:80;", "proxy_pass http://192.168.20.10",
                    "access_log /var/log/nginx/access.log pbl4_ai_access;",
                    "proxy_set_header X-Request-Id $request_id;",
                    "proxy_set_header X-Forwarded-For $remote_addr;",
                    "syslog:server=unix:" + SOCKET, "# PBL4 AI SHADOW HOST END"]
        if not all(value in text for value in required):
            raise RuntimeError("Previously installed site changed; manual review required")
        return text
    # Only support the audited single VM server layout. Fail rather than edit
    # unknown nested locations or replace a host's broader proxy configuration.
    if (len(re.findall(r"\bserver\s*\{", text)) != 1
        or len(re.findall(r"\blocation\s", text)) != 1
        or not re.search(r"location\s+/\s*\{", text)
        or not re.search(r"listen\s+192\.168\.10\.1:80\s*;", text)
        or not re.search(r"proxy_pass\s+http://192\.168\.20\.10(?::80)?/?\s*;", text)
        or len(re.findall(r"\baccess_log\s", text)) != 1
        or re.search(r"\binclude\s", text)
        or re.search(r"\b(?:real_ip_header|set_real_ip_from|proxy_set_header\s+X-Request-Id|add_header\s+X-Request-Id)\b", text)):
        raise RuntimeError("Host site differs from audited single-location VM layout; manual review required")
    text, n = re.subn(r"access_log\s+/var/log/nginx/access\.log\s+combined\s*;",
                     "access_log /var/log/nginx/access.log pbl4_ai_access;", text)
    if n != 1:
        raise RuntimeError("Expected combined access.log; do not overwrite a custom log format")
    text = re.sub(r"\bserver\s*\{", lambda _: "server {\n    # PBL4 AI SHADOW HOST BEGIN\n"
                        "    access_log syslog:server=unix:" + SOCKET +
                        ",tag=ai_shadow,nohostname pbl4_ai_telemetry if=$pbl4_ai_api;\n"
                        "    add_header X-Request-Id $request_id always;\n"
                        "    # PBL4 AI SHADOW HOST END", text, count=1)
    text = re.sub(r"proxy_set_header\s+X-Forwarded-For\s+[^;]+;",
                  "proxy_set_header X-Forwarded-For $remote_addr;", text)
    text = re.sub(r"(location\s+/\s*\{)", r"\1\n        proxy_set_header X-Request-Id $request_id;\n        proxy_hide_header X-Request-Id;\n        proxy_set_header Forwarded '';", text, count=1)
    return text


def formats():
    # Reuse all current query signature maps and redacted canonical access fields.
    src = (ROOT / "security-web/nginx/pbl4-proxy.conf").read_text().split("# Local services are preferred;")[0]
    src = src.replace("idps_", "pbl4_host_").replace("log_format pbl4_host_json", "log_format pbl4_ai_access")
    return src + "\n" + (ROOT / "security-web/deploy/ai-shadow/telemetry.conf").read_text()


def unit(user, group, python, package):
    for value in (user, group, str(python), str(package)):
        if not re.fullmatch(r"[A-Za-z0-9_./@-]+", value):
            raise RuntimeError("Unsupported characters in service path/user")
    return f"""[Unit]
Description=PBL4 frozen AI shadow worker (host/VM)
After=network.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={package}
ExecStart={python} {package}/scripts/ai-host-supervisor.py --bundle {package}/bundle --socket {SOCKET} --output {JOURNAL} --socket-mode 620
Restart=on-failure
RestartSec=10
RestartPreventExitStatus=78
TimeoutStopSec=20
KillMode=control-group
RuntimeDirectory=pbl4-ai-shadow
RuntimeDirectoryMode=0710
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
CPUQuota=100%
MemoryMax=2G
MemorySwapMax=0
TasksMax=64
LimitCORE=0
NoNewPrivileges=true
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/run/pbl4-ai-shadow /var/log/pbl4-ai-shadow

[Install]
WantedBy=multi-user.target
"""


def env_text(text):
    for key, value in {"AI_SHADOW_RESULTS_PATH": JOURNAL, "AUTO_BLOCK": "false", "ENFORCEMENT_MODE": "OFF"}.items():
        pattern = rf"(?m)^[ \t]*(?:export[ \t]+)?{key}[ \t]*=.*$"
        if re.search(pattern, text):
            text = re.sub(pattern, key + "=" + value, text)
        else:
            text += ("" if not text or text.endswith("\n") else "\n") + key + "=" + value + "\n"
    return text


def atomic(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(content)
        os.fchmod(f.fileno(), mode)
        tmp = Path(f.name)
    tmp.replace(path)


def snapshot(backup, paths):
    records = []
    for i, path in enumerate(paths):
        if path.is_symlink():
            raise RuntimeError("Refusing symlink target: " + str(path))
        item = {"path": str(path), "existed": path.exists()}
        if path.exists():
            st = path.stat()
            saved = backup / str(i)
            shutil.copy2(path, saved)
            item.update(saved=str(saved), mode=st.st_mode & 0o777, uid=st.st_uid, gid=st.st_gid)
        records.append(item)
    return records


def restore(records):
    for item in records:
        path = Path(item["path"])
        if item["existed"]:
            atomic(path, Path(item["saved"]).read_bytes(), item["mode"])
            os.chown(path, item["uid"], item["gid"])
        else:
            path.unlink(missing_ok=True)


def syntax(site, content, conf):
    # Use the actual nginx.conf and all other enabled sites, substituting only
    # the reviewed site and format include in a root-private candidate tree.
    with tempfile.TemporaryDirectory(prefix="pbl4-ai-nginx-") as d:
        d = Path(d)
        (d / "site").write_text(content)
        (d / "formats").write_text(conf)
        base = Path("/etc/nginx/nginx.conf").read_text()
        if base.count("include /etc/nginx/conf.d/*.conf;") != 1 or base.count("include /etc/nginx/sites-enabled/*;") != 1:
            raise RuntimeError("Nonstandard nginx includes; review required")
        confs = [p for p in sorted(Path("/etc/nginx/conf.d").glob("*.conf")) if p != FORMATS]
        sites = list(sorted(Path("/etc/nginx/sites-enabled").iterdir()))
        if sum(p.resolve() == site for p in sites) != 1:
            raise RuntimeError("Target site is not uniquely enabled")
        base = base.replace("include /etc/nginx/conf.d/*.conf;",
            "\n".join(f"include {p};" for p in confs) + f"\ninclude {d}/formats;")
        base = base.replace("include /etc/nginx/sites-enabled/*;",
            "\n".join(f"include {d / 'site' if p.resolve() == site else p};" for p in sites))
        (d / "nginx.conf").write_text(base)
        run(["/usr/sbin/nginx", "-t", "-c", str(d / "nginx.conf")])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--install", action="store_true")
    p.add_argument("--rollback", type=Path)
    p.add_argument("--backend-user", default=os.environ.get("SUDO_USER", os.environ.get("USER")))
    p.add_argument("--nginx-group", default="www-data")
    p.add_argument("--site", type=Path, default=Path("/etc/nginx/sites-available/pbl4-proxy"))
    p.add_argument("--configure-backend", action="store_true")
    p.add_argument("--output", type=Path, default=ROOT / ".local-dev/ai-host-plan")
    args = p.parse_args()
    if args.rollback:
        if os.geteuid() != 0:
            raise RuntimeError("Run rollback with sudo")
        data = json.loads((args.rollback / "rollback.json").read_text())
        for item in data["files"]:
            path = Path(item["path"])
            if path.exists() and sha(path) != item["installed_sha256"]:
                raise RuntimeError("File changed since install; manual rollback review required: " + str(path))
        subprocess.run(["systemctl", "stop", SERVICE], check=False)
        subprocess.run(["systemctl", "disable", SERVICE], check=False)
        restore(data["files"])
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
        run(["systemctl", "daemon-reload"])
        if data["was_enabled"]:
            run(["systemctl", "enable", SERVICE])
        if data["was_active"]:
            run(["systemctl", "start", SERVICE])
        print("Rolled back configs; retained model snapshot and all journals. Restart Rust manually.")
        return
    user = pwd.getpwnam(args.backend_user)
    if user.pw_uid == 0:
        raise RuntimeError("Worker must not run as root; pass --backend-user")
    group = grp.getgrnam(args.nginx_group)
    bundle = ROOT / "ai-training/.artifacts/integration_candidate_20261105/demo-request-bundle"
    python = ROOT / "ai-training/.venv/bin/python"
    model_check(bundle)
    run_prefix = ["runuser", "-u", user.pw_name, "--"] if os.geteuid() == 0 else []
    run(run_prefix + [str(python), "-c", "import numpy,sklearn,psutil,threadpoolctl; print('AI dependencies: OK')"])
    site = args.site.resolve()
    old_site = site.read_text()
    patched, conf = patch_site(old_site), formats()
    sources = ["scripts/ai-shadow-worker.py", "scripts/ai-host-supervisor.py",
               "ai-training/scripts/p0-thermal-run.py", "ai-training/scripts/rolling-resource-policy.py"]
    version = hashlib.sha256(("".join(sha(ROOT / f) for f in sources) + MANIFEST_SHA).encode()).hexdigest()[:16]
    package = Path("/opt/pbl4-ai-shadow") / version
    service = unit(user.pw_name, group.gr_name, python, package)
    if not args.install:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, value in [("pbl4-proxy", patched), ("pbl4-ai-shadow.conf", conf), (SERVICE, service)]:
            (args.output / name).write_text(value)
        print("PREPARED only: " + str(args.output))
        print("Model verified. No host or backend config modified.")
        return
    if os.geteuid() != 0:
        raise RuntimeError("Installation requires sudo")
    # Read-only resource preflight as the backend user, before any host writes.
    preflight = """
import importlib.util, sys, psutil
from pathlib import Path
root = Path(sys.argv[1])
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
try:
    thermal = load(root / 'ai-training/scripts/p0-thermal-run.py', 'thermal')
    worker = load(root / 'scripts/ai-shadow-worker.py', 'worker')
    temp = max(v['celsius'] for v in thermal.cpu_sensors().values())
    available = psutil.virtual_memory().available
    status = worker.startup_status(temp, available)
    print(f'AI preflight: {status}; CPU={temp:.1f}C; available={available/1024**3:.2f}GiB; required>=4GiB', flush=True)
    sys.exit(0 if status == 'READY' else 78)
except Exception as exc:
    print('AI preflight: sensor/resource check unavailable (' + type(exc).__name__ + ')', flush=True)
    sys.exit(78)
"""
    run(run_prefix + [str(python), "-c", preflight, str(ROOT)])
    # Validate current and candidate configs before changing any live file.
    run(["/usr/sbin/nginx", "-t"])
    syntax(site, patched, conf)
    changed = {site: patched.encode(), FORMATS: conf.encode(), UNIT: service.encode()}
    backend_env = ROOT / "security-web/.env"
    if args.configure_backend:
        if not backend_env.is_file() or backend_env.is_symlink():
            raise RuntimeError("Existing regular backend .env required")
        changed[backend_env] = env_text(backend_env.read_text()).encode()
    changed = {k:v for k,v in changed.items() if not k.exists() or k.read_bytes() != v}
    # Stable root-owned source/model snapshot; interpreter/venv remain user-managed.
    if not package.exists():
        package.mkdir(parents=True, mode=0o755)
        for name in sources:
            dest = package / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
            dest.chmod(0o644)
        shutil.copytree(bundle, package / "bundle", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in (package / "bundle").rglob("*"):
            f.chmod(0o755 if f.is_dir() else 0o644)
        (package / "bundle").chmod(0o755)
    for name in sources:
        if sha(package / name) != sha(ROOT / name):
            raise RuntimeError("Installed package differs; refusing overwrite")
    model_check(package / "bundle")
    journal_dir = Path(JOURNAL).parent
    if journal_dir.is_symlink():
        raise RuntimeError("Journal directory must not be symlink")
    if journal_dir.exists() and journal_dir.stat().st_uid != user.pw_uid:
        raise RuntimeError("Journal directory belongs to another user")
    if journal_dir.exists():
        if journal_dir.stat().st_mode & 0o777 != 0o700:
            raise RuntimeError("Existing journal permissions differ from 0700; review required")
    else:
        journal_dir.mkdir(mode=0o700)
        os.chown(journal_dir, user.pw_uid, user.pw_gid)
    was_active = subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode == 0
    was_enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", SERVICE], stdout=subprocess.DEVNULL).returncode == 0
    if not changed:
        run(["systemctl", "enable", "--now", SERVICE])
        print("Configuration unchanged; service enabled. No NGINX reload.")
        return
    backup = Path("/var/backups/pbl4-ai-shadow") / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, mode=0o700)
    records = snapshot(backup, changed)
    data = {"files": records, "was_active": was_active, "was_enabled": was_enabled}
    try:
        for record in records:
            path = Path(record["path"])
            atomic(path, changed[path], 0o600 if path == backend_env else 0o644)
            if path == backend_env:
                os.chown(path, record["uid"], record["gid"])
            record["installed_sha256"] = sha(path)
        atomic(backup / "rollback.json", json.dumps(data, indent=2).encode(), 0o600)
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", SERVICE])
        import time
        began = time.time()
        run(["systemctl", "restart" if was_active else "start", SERVICE])
        # Do not activate telemetry until the real model publishes READY.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if subprocess.run(["systemctl", "is-failed", "--quiet", SERVICE]).returncode == 0:
                subprocess.run(["journalctl", "-u", SERVICE, "-n", "12", "--no-pager"], check=False)
                raise RuntimeError("Worker failed before READY; see startup reason above and results.jsonl")
            if Path(JOURNAL).exists():
                with Path(JOURNAL).open("rb") as f:
                    f.seek(max(0, Path(JOURNAL).stat().st_size - 16384))
                    for line in reversed(f.read().splitlines()):
                        try:
                            value = json.loads(line)
                            if value.get("kind") == "heartbeat" and value.get("status") == "READY" and datetime.datetime.fromisoformat(value["observed_at"]).timestamp() >= began:
                                break
                        except ValueError:
                            continue
                    else:
                        time.sleep(1)
                        continue
                    break
            time.sleep(1)
        else:
            raise RuntimeError("Worker did not become READY; check journalctl")
        run(["systemctl", "reload", "nginx"])
    except Exception:
        subprocess.run(["systemctl", "stop", SERVICE], check=False)
        restore(records)
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
        run(["systemctl", "daemon-reload"])
        if not was_enabled:
            subprocess.run(["systemctl", "disable", SERVICE], check=False)
        if was_active:
            run(["systemctl", "start", SERVICE])
        raise
    print("INSTALLED. Backup/rollback: " + str(backup))
    print("Restart existing Rust backend manually to read " + JOURNAL)
    print("No database/service migration or end-to-end acceptance performed by installer.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No environment/credentials or raw HTTP values are included in errors.
        print("STOPPED: " + str(exc))
        raise SystemExit(1)

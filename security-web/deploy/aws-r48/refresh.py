"""Activate or roll back the R49 observation update on the existing staging host."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sys
import time

import gateway
import update as cloud_update

BACKUP = Path("/var/backups/websentinel-r49")
CORR = cloud_update.CORR
KIT = cloud_update.KIT
SITE = cloud_update.SITE
R48_GATEWAY_SHA = "3cbfe44ff5c34966d7c1127c58ef0bbde04a3260c35fefcd29db3e36ca739c6b"
MODEL_SHA = "91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff"
ASSETS = ("gateway.py", "update.py", "pbl4-access.conf", "refresh.py")


def verify_host():
    active = cloud_update.ACTIVE.resolve(strict=True)
    if os.geteuid() != 0 or active.name != cloud_update.R47_REVISION:
        raise RuntimeError("Unexpected staging identity or application revision")
    sys.path.insert(0, str(active))
    import cloud_profile as cloud

    expected = cloud.protected_json(cloud_update.R47 / "cloud-identity.json")
    cloud.verify_identity(cloud.metadata_identity(), expected,
                          Path("/sys/class/dmi/id/sys_vendor").read_text().strip())
    env = cloud_update.ENV.read_text().splitlines()
    for setting in ("ENFORCEMENT_MODE=OFF", "AUTO_BLOCK=false", "PBL4_FIREWALL_CMD=/bin/false"):
        key = setting.split("=", 1)[0] + "="
        if [line for line in env if line.startswith(key)] != [setting]:
            raise RuntimeError("Staging enforcement flags changed")
    model = active / "scorer/ai-training/contracts/quality-freeze-r37/release/finalist.onnx"
    if cloud_update.sha(model) != MODEL_SHA:
        raise RuntimeError("Unexpected scorer artifact")


def verify_database():
    for db, (table, count) in cloud_update.DB_FILES.items():
        value = cloud_update.run("runuser", "-u", "postgres", "--", "psql", "-XAt",
                                 "-d", db, "-c", f"select count(*) from {table} where success")
        if value != str(count):
            raise RuntimeError("Database migration count differs from R48")


def health():
    for unit in ("nginx.service", cloud_update.STUDENT, cloud_update.SEC, cloud_update.SCORE,
                 cloud_update.SENSOR, CORR):
        if cloud_update.run("systemctl", "is-active", unit) != "active":
            raise RuntimeError(f"Inactive unit {unit}")
    # Request via loopback with the public hostname, SNI and normal CA validation.
    for attempt in range(8):
        status = cloud_update.run(
            "curl", "--silent", "--show-error", "--max-time", "4", "--output", "/dev/null",
            "--write-out", "%{http_code}", "--resolve", "student-dut.duckdns.org:443:127.0.0.1",
            "https://student-dut.duckdns.org/api/auth/csrf", check=False,
        )
        if status == "200":
            return
        if attempt < 7:
            time.sleep(0.5)
    raise RuntimeError("Student HTTPS health did not recover")


def checksum_report(path):
    return "".join(f"{cloud_update.sha(item)}  {item.name}\n" for item in sorted(path.iterdir())
                   if item.name != "SHA256SUMS")


def rollback():
    verify_host()
    cloud_update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    baseline = (BACKUP / "nginx.conf").read_bytes()
    if hashlib.sha256(baseline).hexdigest() != R48_GATEWAY_SHA:
        raise RuntimeError("Rollback gateway SHA differs from R48")
    cloud_update.replace(SITE, baseline, 0o644)
    cloud_update.run("nginx", "-t")
    cloud_update.run("systemctl", "reload", "nginx")
    for name in ("gateway.py", "update.py"):
        cloud_update.replace(KIT / name, (BACKUP / ("runtime-" + name)).read_bytes(), 0o644)
    cloud_update.run("systemctl", "restart", CORR)
    health()


def activate(source):
    verify_host()
    verify_database()
    if cloud_update.sha(SITE) != R48_GATEWAY_SHA or BACKUP.exists():
        raise RuntimeError("R48 gateway or one-shot backup gate differs")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient rollback headroom")
    manifest = json.loads((source / "SHA256SUMS.json").read_text())
    if manifest.keys() != set(ASSETS) or any(
        (source / name).is_symlink() or cloud_update.sha(source / name) != manifest[name]
        for name in ASSETS
    ):
        raise RuntimeError("Unexpected R49 staged kit")
    if (KIT / "pbl4-access.conf").exists() or (KIT / "refresh.py").exists():
        raise RuntimeError("Colliding R49 deployment assets")
    r47_gateway = Path("/var/backups/websentinel-r48/nginx.conf")
    if cloud_update.sha(r47_gateway) != cloud_update.R47_GATEWAY:
        raise RuntimeError("R47 template digest differs")
    cloud_update.backup(BACKUP)
    for name in ("gateway.py", "update.py"):
        cloud_update.replace(BACKUP / ("runtime-" + name), (KIT / name).read_bytes())
    cloud_update.replace(BACKUP / "SHA256SUMS", checksum_report(BACKUP))
    cloud_update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)

    for name in ASSETS:
        cloud_update.replace(KIT / name, (source / name).read_bytes(), 0o644)
    try:
        candidate = gateway.render(r47_gateway.read_text(), KIT, cloud_update.KEY,
                                   pwd.getpwnam("www-data").pw_gid,
                                   cloud_update.STATE / "edge/access.jsonl", cloud_update.SCORER_SOCKET)
        cloud_update.replace(SITE, candidate, 0o644)
        cloud_update.run("nginx", "-t")
        cloud_update.run("systemctl", "restart", CORR)
        cloud_update.run("systemctl", "reload", "nginx")
        health()
    except Exception:
        rollback()
        raise
    print(json.dumps({
        "gateway_sha256": cloud_update.sha(SITE),
        "backup_sha256": cloud_update.sha(BACKUP / "SHA256SUMS"),
        "signed_routes": len(gateway.ROUTES),
        "mode": "observation",
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("rollback")
    deploy = sub.add_parser("activate")
    deploy.add_argument("source", type=Path)
    args = parser.parse_args()
    if args.action == "rollback":
        rollback()
    else:
        activate(args.source.resolve(strict=True))

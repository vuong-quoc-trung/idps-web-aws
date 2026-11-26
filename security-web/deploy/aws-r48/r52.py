"""Apply or roll back the R52 catalog observation update on AWS staging."""

import argparse
import json
import os
from pathlib import Path
import pwd
import shutil

import refresh
import update

BACKUP = Path("/var/backups/websentinel-r52")
BASE_GATEWAY = "99fa902dd1602e3e55c11c5ca8100361322a3e4572d78656a674b312fca49203"
FILES = ("gateway.py", "correlate.py")


def reconfigure(site, files):
    for name, contents in files.items():
        update.replace(update.KIT / name, contents, 0o644)
    update.replace(update.SITE, site, 0o644)
    update.run("nginx", "-t")
    update.run("systemctl", "restart", update.CORR)
    update.run("systemctl", "reload", "nginx")
    refresh.health()


def rollback():
    refresh.verify_host()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    if update.sha(BACKUP / "nginx.conf") != BASE_GATEWAY:
        raise ValueError("Rollback gateway does not match R51")
    reconfigure((BACKUP / "nginx.conf").read_bytes(),
                {name: (BACKUP / name).read_bytes() for name in FILES})


def install(stage):
    refresh.verify_host()
    refresh.verify_database()
    if update.sha(update.SITE) != BASE_GATEWAY or BACKUP.exists():
        raise ValueError("Expected the R51 gateway and a fresh backup directory")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise ValueError("Insufficient room for rollback artifacts")
    import gateway

    original = Path("/var/backups/websentinel-r48/nginx.conf")
    if update.sha(original) != update.R47_GATEWAY:
        raise ValueError("Unexpected original gateway template")
    candidate = gateway.render(original.read_text(), update.KIT, update.KEY,
                               pwd.getpwnam("www-data").pw_gid,
                               update.STATE / "edge/access.jsonl", update.SCORER_SOCKET)
    update.backup(BACKUP)
    for name in FILES:
        update.replace(BACKUP / name, (update.KIT / name).read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    try:
        reconfigure(candidate, {name: (stage / name).read_bytes() for name in FILES})
    except Exception:
        rollback()
        raise
    print(json.dumps({"gateway_sha": update.sha(update.SITE),
                      "backup_sha": update.sha(BACKUP / "SHA256SUMS")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        rollback()

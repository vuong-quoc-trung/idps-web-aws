"""Install the R50 observation gateway on the verified R49 staging baseline."""

import argparse
import hashlib
import os
from pathlib import Path
import pwd

import gateway
import refresh
import update

BACKUP = Path("/var/backups/websentinel-r50-gateway")
R49_SHA = "11bc07397e23c57ff4d6130a656a88785e9deabea371d89c7af682ee78f1007c"


def reconfigure(content, runtime):
    update.replace(update.KIT / "gateway.py", runtime, 0o644)
    update.replace(update.SITE, content, 0o644)
    update.run("nginx", "-t")
    update.run("systemctl", "restart", update.CORR)
    update.run("systemctl", "reload", "nginx")
    refresh.health()


def restore():
    refresh.verify_host()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    previous = BACKUP / "nginx.conf"
    if update.sha(previous) != R49_SHA:
        raise RuntimeError("Unexpected rollback gateway")
    reconfigure(previous.read_bytes(), (BACKUP / "gateway.py").read_bytes())


def install():
    refresh.verify_host()
    refresh.verify_database()
    if update.sha(update.SITE) != R49_SHA or BACKUP.exists():
        raise RuntimeError("Expected a fresh R49 baseline")
    original = Path("/var/backups/websentinel-r48/nginx.conf")
    if update.sha(original) != update.R47_GATEWAY:
        raise RuntimeError("Unexpected R47 template")
    candidate = gateway.render(original.read_text(), update.KIT, update.KEY,
                               pwd.getpwnam("www-data").pw_gid,
                               update.STATE / "edge/access.jsonl", update.SCORER_SOCKET)
    runtime = Path(gateway.__file__).read_bytes()
    update.backup(BACKUP)
    update.replace(BACKUP / "gateway.py", (update.KIT / "gateway.py").read_bytes(), 0o600)
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP), 0o600)
    try:
        reconfigure(candidate, runtime)
    except Exception:
        restore()
        raise
    print(f"GATEWAY_SHA={update.sha(update.SITE)} SIGNED_ROUTES={len(gateway.ROUTES)} "
          f"BACKUP_SHA={update.sha(BACKUP / 'SHA256SUMS')} SOURCE_SHA={hashlib.sha256(runtime).hexdigest()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "install":
        install()
    else:
        restore()

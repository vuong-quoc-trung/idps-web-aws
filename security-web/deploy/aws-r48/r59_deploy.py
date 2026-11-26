"""Install the R59 enforcement guard without changing the active scope."""

import argparse
import json
import os
from pathlib import Path
import shutil

import r57
import r58
import refresh
import update

BACKUP = Path("/var/backups/websentinel-r59")
BASE_BINARY = "28a22a7a3521c6cba82dee2736ad902cb0a06700c3ed6b6e108b2f69b1ae5797"
BASE_INDEX = "876b73f3eafcb3811ca7f2f5a6abc8975c35194ddb023b9f5bdd35c715364e38"


def assert_scope(index):
    r57.verify()
    if update.sha(index) != BASE_INDEX:
        raise RuntimeError("Unexpected R58 frontend")
    registry = r57.paths()["scorer-files.json"][0]
    if update.sha(registry) != r58.BASE_SCORER:
        raise RuntimeError("Unexpected scorer registry")


def web_health(index):
    r58.web_check(index, True)
    if json.loads(update.run("curl", "-fsS", "--max-time", "4",
                             "http://127.0.0.1:3000/health"))["status"] != "alive":
        raise RuntimeError("Security API did not recover")


def verify_backup():
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    if update.sha(BACKUP / "security-bin") != BASE_BINARY:
        raise RuntimeError("Unexpected rollback binary")
    for name in ("student.env", "security.env", "scorer.env"):
        if update.sha(update.R47 / name) != update.sha(BACKUP / name):
            raise RuntimeError(f"Configuration changed for {name}")
    if update.sha(update.SITE) != update.sha(BACKUP / "nginx.conf"):
        raise RuntimeError("NGINX configuration changed")


def restore(binary, index):
    verify_backup()
    update.replace(binary, (BACKUP / "security-bin").read_bytes(), 0o755)
    r58.restart()
    web_health(index)


def install(binary, index, stage):
    if BACKUP.exists() or update.sha(binary) != BASE_BINARY:
        raise RuntimeError("Expected R58 serving binary and a fresh backup path")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient space for rollback")
    candidate = stage / "candidate"
    update.run("zstd", "-qd", f"--patch-from={binary}", stage / "security.zst", "-o", candidate)
    if update.sha(candidate) != (stage / "security.sha256").read_text().strip():
        raise RuntimeError("Reconstructed binary digest differs")
    update.backup(BACKUP)
    update.replace(BACKUP / "security-bin", binary.read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    verify_backup()
    try:
        update.replace(binary, candidate.read_bytes(), 0o755)
        r58.restart()
        web_health(index)
        assert_scope(index)
        verify_backup()
    except BaseException:
        restore(binary, index)
        raise
    print(json.dumps({
        "serving_sha": update.sha(binary),
        "index_sha": update.sha(index),
        "backup_sha": update.sha(BACKUP / "SHA256SUMS"),
    }), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("install", "rollback"))
    args = cli.parse_args()
    os.umask(0o077)
    binary, dist = r58.paths()
    index = dist / "index.html"
    assert_scope(index)
    if args.action == "install":
        install(binary, index, Path(__file__).resolve().parent)
    else:
        restore(binary, index)

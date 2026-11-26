"""Install the observation-only R56 binary on the verified EC2 staging host."""

import argparse
import os
from pathlib import Path

import r55
import refresh
import update

BACKUP = Path("/var/backups/websentinel-r56")
BASELINE = "96681283805c457ec7ab02278deefc419897d871659c2cceb405536373b8f960"


def verify():
    refresh.verify_host()
    refresh.verify_database()
    if r55.DROP_IN.read_bytes() != r55.PROFILE:
        raise RuntimeError("Expected the verified AWS operations profile")


def restore(binary):
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    if update.sha(BACKUP / "security-bin") != BASELINE:
        raise RuntimeError("Unexpected rollback binary")
    update.replace(binary, (BACKUP / "security-bin").read_bytes(), 0o755)
    r55.settle()


def install(binary, stage):
    if BACKUP.exists() or update.sha(binary) != BASELINE:
        raise RuntimeError("Expected the R55 serving binary and a fresh backup path")
    candidate = stage / "candidate"
    update.run("zstd", "-qd", f"--patch-from={binary}", stage / "serving.zst", "-o", candidate)
    if update.sha(candidate) != (stage / "serving.sha256").read_text().strip():
        raise RuntimeError("Reconstructed binary SHA differs")
    update.backup(BACKUP)
    update.replace(BACKUP / "security-bin", binary.read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    try:
        update.replace(binary, candidate.read_bytes(), 0o755)
        r55.settle()
        for name in ("student.env", "security.env", "scorer.env"):
            if update.sha(update.R47 / name) != update.sha(BACKUP / name):
                raise RuntimeError("Environment changed during deployment")
    except Exception:
        restore(binary)
        raise
    print("R56_SERVING_SHA=" + update.sha(binary), flush=True)
    print("R56_BACKUP_SHA=" + update.sha(BACKUP / "SHA256SUMS"), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("install", "rollback"))
    args = cli.parse_args()
    os.umask(0o077)
    verify()
    binary, _ = r55.paths()
    if args.action == "install":
        install(binary, Path(__file__).resolve().parent)
    else:
        restore(binary)

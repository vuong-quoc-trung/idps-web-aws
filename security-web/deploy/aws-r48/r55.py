"""Update the AWS operations dashboard on the pinned staging instance."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import time

import refresh
import update

BACKUP = Path("/var/backups/websentinel-r55")
DROP_IN = update.SYSTEM / (update.SEC + ".d/55-operations-profile.conf")
PROFILE = b"[Service]\nEnvironment=WS_OPERATIONS_PROFILE=aws-staging\n"
R54_BINARY = "33de408556d22c60950ac00a66b8de18a6fa9aa35073bba0f21dd9e18b6da99f"
R54_INDEX = "bc091063ee08d118df11471921949b434b6fee909977407bb6fdc81d9493bc70"


def paths():
    security = update.ACTIVE.resolve(strict=True) / "security"
    return security / "pbl4-security-demo", security / "frontend/dist/index.html"


def verify_backup():
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    for name in ("student.env", "security.env", "scorer.env"):
        if update.sha(BACKUP / name) != update.sha(update.R47 / name):
            raise RuntimeError(f"Service environment differs: {name}")


def settle():
    update.run("systemctl", "daemon-reload")
    update.run("systemctl", "restart", update.SEC, timeout=45)
    refresh.health()
    for _ in range(12):
        output = update.run("curl", "-fsS", "--max-time", "3", "http://127.0.0.1:3000/health", check=False)
        if output and json.loads(output).get("status") == "alive":
            return
        time.sleep(1)
    raise RuntimeError("Security Web did not recover")


def restore():
    verify_backup()
    if DROP_IN.exists() and DROP_IN.read_bytes() != PROFILE:
        raise RuntimeError("Operations drop-in differs from the R55 release")
    binary, index = paths()
    update.replace(binary, (BACKUP / "security-bin").read_bytes(), 0o755)
    update.replace(index, (BACKUP / "security-index.html").read_bytes(), 0o644)
    DROP_IN.unlink(missing_ok=True)
    settle()


def install(stage):
    binary, index = paths()
    if DROP_IN.exists() or update.sha(binary) != R54_BINARY or update.sha(index) != R54_INDEX:
        raise RuntimeError("Expected the R54 Security Web baseline")
    manifest = json.loads((stage / "release.json").read_text())
    required = {"security.zst", "security.sha256", "index.html"}
    assets = manifest.keys() - required
    if required - manifest.keys() or not assets or not all(
        re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(js|css|png)", name) for name in assets
    ):
        raise ValueError("Unexpected bundle manifest")
    for name, expected in manifest.items():
        source = stage / name
        if source.is_symlink() or not source.is_file() or update.sha(source) != expected:
            raise ValueError(f"Bundle checksum differs: {name}")
    candidate = stage / "security-bin"
    update.run("zstd", "-qd", f"--patch-from={binary}", stage / "security.zst", "-o", candidate)
    if update.sha(candidate) != (stage / "security.sha256").read_text().strip():
        raise ValueError("Reconstructed binary checksum differs")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient disk for rollback")
    if not BACKUP.exists():
        update.backup(BACKUP)
        update.replace(BACKUP / "security-bin", binary.read_bytes())
        update.replace(BACKUP / "security-index.html", index.read_bytes())
        update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    verify_backup()
    if (update.sha(BACKUP / "security-bin") != R54_BINARY
            or update.sha(BACKUP / "security-index.html") != R54_INDEX):
        raise ValueError("Rollback files differ from the staged baseline")
    for name in sorted(assets):
        target = index.parent / name
        if not target.exists():
            update.replace(target, (stage / name).read_bytes(), 0o644)
        elif update.sha(target) != manifest[name]:
            raise ValueError(f"Existing immutable asset differs: {name}")
    try:
        update.replace(DROP_IN, PROFILE, 0o644)
        update.replace(binary, candidate.read_bytes(), 0o755)
        update.replace(index, (stage / "index.html").read_bytes(), 0o644)
        settle()
        verify_backup()
    except Exception:
        restore()
        raise
    print(json.dumps({"binary_sha": update.sha(binary), "index_sha": update.sha(index),
                      "backup_sha": update.sha(BACKUP / "SHA256SUMS")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    os.umask(0o077)
    refresh.verify_host()
    refresh.verify_database()
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        restore()

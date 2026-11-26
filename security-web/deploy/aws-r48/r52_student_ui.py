"""Install the R52 Student Web static build without restarting Java."""

import argparse
import json
import os
from pathlib import Path
import re

import refresh
import update

BACKUP = Path("/var/backups/websentinel-r52-student-ui")


def ui_root():
    return update.ACTIVE.resolve(strict=True) / "student-ui"


def rollback():
    refresh.verify_host()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP)
    update.replace(ui_root() / "index.html", (BACKUP / "index.html").read_bytes(), 0o644)
    refresh.health()


def install(stage):
    refresh.verify_host()
    refresh.verify_database()
    target = ui_root()
    manifest = json.loads((stage / "ui-manifest.json").read_text())
    if not manifest or "index.html" not in manifest or any(
        name != "index.html" and not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(js|css)", name)
        for name in manifest
    ):
        raise ValueError("Unexpected static build manifest")
    for name, expected in manifest.items():
        source = stage / "student-ui" / name
        if source.is_symlink() or update.sha(source) != expected:
            raise ValueError("Staged static asset mismatch")
        if name != "index.html" and (target / name).exists() and update.sha(target / name) != expected:
            raise ValueError("Existing hashed asset has different contents")

    BACKUP.mkdir(mode=0o700)
    update.replace(BACKUP / "index.html", (target / "index.html").read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    try:
        for name in manifest:
            if name != "index.html" and not (target / name).exists():
                update.replace(target / name, (stage / "student-ui" / name).read_bytes(), 0o644)
        update.replace(target / "index.html", (stage / "student-ui/index.html").read_bytes(), 0o644)
        refresh.health()
    except Exception:
        rollback()
        raise
    print(json.dumps({"student_index_sha": update.sha(target / "index.html"),
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

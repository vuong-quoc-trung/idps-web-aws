"""Deploy the R54 web builds and Security API on the verified AWS staging instance."""

import argparse
import json
import os
from pathlib import Path
import re
import time

import refresh
import update

BACKUP = Path("/var/backups/websentinel-r54")
INDEX = ("student-index.html", "security-index.html")
ASSET = re.compile(r"(student|security)-ui/assets/[A-Za-z0-9_-]+\.(js|css|png)")


def roots():
    release = update.ACTIVE.resolve(strict=True)
    return {"student-ui": release / "student-ui",
            "security-ui": release / "security/frontend/dist"}


def backup_paths():
    ui = roots()
    return dict(zip(INDEX, (root / "index.html" for root in ui.values()))) | {
        "security-bin": update.ACTIVE.resolve(strict=True) / "security/pbl4-security-demo",
    }


def verify():
    refresh.verify_host()
    refresh.verify_database()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)


def assert_envs():
    for name in ("student.env", "security.env", "scorer.env"):
        if update.sha(BACKUP / name) != update.sha(update.R47 / name):
            raise ValueError(f"Config differs from R54 backup: {name}")


def settle():
    update.run("systemctl", "restart", update.SEC, timeout=45)
    refresh.health()
    for _ in range(12):
        raw = update.run("curl", "-fsS", "--max-time", "3",
                         "http://127.0.0.1:3000/health", check=False)
        if raw and json.loads(raw).get("status") == "alive":
            return
        time.sleep(1)
    raise RuntimeError("Security API did not recover")


def restore():
    for name, target in backup_paths().items():
        update.replace(target, (BACKUP / name).read_bytes(),
                       0o755 if name == "security-bin" else 0o644)
    settle()


def install(stage):
    verify()
    assert_envs()
    targets = backup_paths()
    if any(update.sha(BACKUP / name) != update.sha(path)
           for name, path in targets.items()):
        raise ValueError("Unexpected change since the R54 backup")
    manifest = json.loads((stage / "release.json").read_text())
    ui = roots()
    indexes = {f"{name}/index.html" for name in ui}
    assets = set(manifest) - indexes - {"security.zst", "security.sha256"}
    if (set(manifest) != indexes | assets | {"security.zst", "security.sha256"}
            or not all(ASSET.fullmatch(name) for name in assets)
            or any(not any(asset.startswith(name + "/") for asset in assets) for name in ui)):
        raise ValueError("Unexpected release manifest")
    for name, sha in manifest.items():
        source = stage / name
        if source.is_symlink() or not source.is_file() or update.sha(source) != sha:
            raise ValueError(f"Staged digest differs: {name}")
    binary = stage / "security-bin"
    update.run("zstd", "-qd", f"--patch-from={targets['security-bin']}",
               stage / "security.zst", "-o", binary)
    if update.sha(binary) != (stage / "security.sha256").read_text().strip():
        raise ValueError("Reconstructed Security API digest differs")
    for name in sorted(assets):
        slot, asset = name.split("/", 1)
        target = ui[slot] / asset
        if target.exists():
            if update.sha(target) != manifest[name]:
                raise ValueError(f"Existing hashed asset differs: {name}")
        else:
            update.replace(target, (stage / name).read_bytes(), 0o644)

    try:
        update.replace(targets["security-bin"], binary.read_bytes(), 0o755)
        for slot, root in ui.items():
            update.replace(root / "index.html", (stage / slot / "index.html").read_bytes(), 0o644)
        settle()
        assert_envs()
    except Exception:
        restore()
        raise
    print(json.dumps({name: update.sha(path) for name, path in targets.items()}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        verify()
        restore()

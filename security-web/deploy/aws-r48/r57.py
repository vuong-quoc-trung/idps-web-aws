"""Install or roll back R57 on the verified AWS staging host."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import time

import refresh
import r55
import update

BACKUP = Path("/var/backups/websentinel-r57")
BASE_BINARY = "96681283805c457ec7ab02278deefc419897d871659c2cceb405536373b8f960"
BASE_INDEX = "5f5f27726dd427afb5dc80f8aeb1b5bec91d16471d16a5b6142f37d404f6e5d7"
SCORER_FILES = {
    "receiver.py": "ai-training/contracts/https-shadow-r35/receiver.py",
    "serve.py": "ai-training/contracts/https-model-r36/serve.py",
}


def verify():
    refresh.verify_host()
    refresh.verify_database()
    if r55.DROP_IN.read_bytes() != r55.PROFILE:
        raise RuntimeError("Expected the AWS operations profile")


def paths():
    binary, index = r55.paths()
    scorer = update.ACTIVE.resolve(strict=True) / "scorer"
    return {
        "security-bin": (binary, 0o755),
        "index.html": (index, 0o644),
        "scorer-files.json": (scorer / "files.json", 0o644),
        "scorer.env": (update.R47 / "scorer.env", 0o600),
        **{name: (scorer / path, 0o644) for name, path in SCORER_FILES.items()},
    }


def settle():
    for unit in (update.SCORE, update.SEC):
        update.run("systemctl", "restart", unit, timeout=35)
    refresh.health()
    for _ in range(15):
        health = update.run(
            "runuser", "-u", "www-data", "--", "curl", "-fsS", "--max-time", "3",
            "-D", "-", "-o", "/dev/null", "--unix-socket", update.SCORER_SOCKET,
            "http://localhost/healthz", check=False,
        )
        web = update.run("curl", "-fsS", "--max-time", "3",
                         "http://127.0.0.1:3000/health", check=False)
        if ("x-model-sha256: " + refresh.MODEL_SHA in health.lower()
                and json.loads(web or "{}").get("status") == "alive"):
            return
        time.sleep(1)
    raise RuntimeError("Pinned scorer or Security API did not recover")


def verify_backup():
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    if (update.sha(BACKUP / "security-bin") != BASE_BINARY
            or update.sha(BACKUP / "index.html") != BASE_INDEX):
        raise RuntimeError("Unexpected rollback baseline")


def restore():
    verify_backup()
    for name, (target, mode) in paths().items():
        update.replace(target, (BACKUP / name).read_bytes(), mode)
    settle()


def install(stage):
    files = paths()
    binary, _ = files["security-bin"]
    index, _ = files["index.html"]
    if BACKUP.exists() or update.sha(binary) != BASE_BINARY or update.sha(index) != BASE_INDEX:
        raise RuntimeError("Expected the verified serving baseline and a fresh backup path")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient space for backup")
    manifest = json.loads((stage / "manifest.json").read_text())
    assets = sorted(name for name in manifest
                    if re.fullmatch(r"index-[A-Za-z0-9_-]+\.(js|css)", name))
    expected = {"security.zst", "security.sha256", "index.html", *SCORER_FILES, *assets}
    if not assets or set(manifest) != expected:
        raise RuntimeError("Unexpected release assets")
    for name, digest in manifest.items():
        source = stage / name
        if source.is_symlink() or not source.is_file() or update.sha(source) != digest:
            raise RuntimeError(f"Staged digest differs for {name}")
    candidate = stage / "security-bin"
    update.run("zstd", "-qd", f"--patch-from={binary}", stage / "security.zst", "-o", candidate)
    if update.sha(candidate) != (stage / "security.sha256").read_text().strip():
        raise RuntimeError("Reconstructed binary digest differs")

    registry, _ = files["scorer-files.json"]
    env_path, _ = files["scorer.env"]
    release = json.loads(registry.read_text())
    env = env_path.read_text()
    pin = f"RELEASE_SHA256={update.sha(registry)}"
    if env.splitlines().count(pin) != 1:
        raise RuntimeError("Scorer pin does not match the current registry")
    for name, path in SCORER_FILES.items():
        if update.sha(files[name][0]) != release[path]:
            raise RuntimeError(f"Scorer baseline digest differs for {name}")
        release[path] = manifest[name]

    update.backup(BACKUP)
    for name, (target, _) in files.items():
        if name != "scorer.env":
            update.replace(BACKUP / name, target.read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    verify_backup()

    try:
        for name in assets:
            target = index.parent / "assets" / name
            if not target.exists():
                update.replace(target, (stage / name).read_bytes(), 0o644)
            elif update.sha(target) != manifest[name]:
                raise RuntimeError(f"Existing immutable asset differs for {name}")
        for name in ("receiver.py", "serve.py", "security-bin", "index.html"):
            target, mode = files[name]
            update.replace(target, (stage / name).read_bytes(), mode)
        update.replace(registry, json.dumps(release, sort_keys=True) + "\n", 0o644)
        update.replace(env_path, env.replace(pin, f"RELEASE_SHA256={update.sha(registry)}", 1))
        settle()
        verify()
        verify_backup()
        for name in ("student.env", "security.env"):
            if update.sha(update.R47 / name) != update.sha(BACKUP / name):
                raise RuntimeError(f"Unrelated configuration differs for {name}")
    except BaseException:
        restore()
        raise

    print(json.dumps({"serving_sha": update.sha(binary), "index_sha": update.sha(index),
                      "backup_sha": update.sha(BACKUP / "SHA256SUMS"),
                      "scorer_manifest_sha": update.sha(registry)}), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("install", "rollback"))
    args = cli.parse_args()
    os.umask(0o077)
    verify()
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        restore()

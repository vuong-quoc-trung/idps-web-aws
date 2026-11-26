"""Apply the R51 gateway, readiness UI and scorer transport update in AWS staging."""

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import time

import refresh
import update

BACKUP = Path("/var/backups/websentinel-r51")
BASE_GATEWAY = "a045b6bb67cf3264f9896864c753e2ba236bfea59156393efbac074f401d318d"
BASE_BINARY = "0d20b58c9f10eb4e5bed7d4c055cd19da1b97fedaad9738ca0d2f54962b8470f"
RECEIVER = "ai-training/contracts/https-shadow-r35/receiver.py"


def targets():
    release = update.ACTIVE.resolve(strict=True)
    return {
        "receiver.py": release / "scorer" / RECEIVER,
        "scorer-files.json": release / "scorer/files.json",
        "security-bin": release / "security/pbl4-security-demo",
        "index.html": release / "security/frontend/dist/index.html",
        "gateway.py": update.KIT / "gateway.py",
    }


def settle():
    update.run("nginx", "-t")
    for unit in (update.SCORE, update.SEC, update.CORR):
        update.run("systemctl", "restart", unit, timeout=75)
    update.run("systemctl", "reload", "nginx")
    refresh.health()
    for _ in range(15):
        scorer = update.run("runuser", "-u", "www-data", "--", "curl", "-fsS", "--max-time", "3",
                            "-o", "/dev/null", "-w", "%{http_code}", "--unix-socket", update.SCORER_SOCKET,
                            "http://localhost/healthz", check=False)
        web = update.run("curl", "-fsS", "--max-time", "3", "http://127.0.0.1:3000/health", check=False)
        if scorer == "200" and json.loads(web or "{}").get("status") == "alive":
            return
        time.sleep(1)
    raise RuntimeError("Scorer or Security API did not recover")


def restore():
    refresh.verify_host()
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=75)
    if update.sha(BACKUP / "nginx.conf") != BASE_GATEWAY:
        raise RuntimeError("Unexpected R50 rollback gateway")
    files = targets()
    for key, target in files.items():
        update.replace(target, (BACKUP / key).read_bytes(), 0o755 if key == "security-bin" else 0o644)
    update.replace(update.R47 / "scorer.env", (BACKUP / "scorer.env").read_bytes())
    update.replace(update.SITE, (BACKUP / "nginx.conf").read_bytes(), 0o644)
    for name in json.loads((BACKUP / "new-assets.json").read_text()):
        (files["index.html"].parent / "assets" / name).unlink(missing_ok=True)
    settle()


def install(stage):
    refresh.verify_host()
    refresh.verify_database()
    files = targets()
    if (BACKUP.exists() or update.sha(update.SITE) != BASE_GATEWAY
            or update.sha(files["security-bin"]) != BASE_BINARY):
        raise RuntimeError("Expected the verified R50 staging baseline")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient disk for rollback")
    sources = json.loads((stage / "manifest.json").read_text())
    assets = [name for name in sources if re.fullmatch(r"index-[A-Za-z0-9_-]+\.(js|css)", name)]
    if set(sources) != {"receiver.py", "gateway.py", "security.zst", "index.html", *assets} or not assets:
        raise RuntimeError("Unexpected release assets")
    for name, sha in sources.items():
        if (stage / name).is_symlink() or update.sha(stage / name) != sha:
            raise RuntimeError("Staged digest differs")
    output = stage / "security-bin"
    update.run("zstd", "-qd", f"--patch-from={files['security-bin']}", stage / "security.zst", "-o", output)
    if update.sha(output) != (stage / "security.sha256").read_text().strip():
        raise RuntimeError("Reconstructed binary digest differs")

    import gateway
    original = Path("/var/backups/websentinel-r48/nginx.conf")
    if update.sha(original) != update.R47_GATEWAY:
        raise RuntimeError("Unexpected R47 gateway template")
    candidate = gateway.render(original.read_text(), update.KIT, update.KEY,
                               pwd.getpwnam("www-data").pw_gid,
                               update.STATE / "edge/access.jsonl", update.SCORER_SOCKET)
    manifest = json.loads(files["scorer-files.json"].read_text())
    if update.sha(files["receiver.py"]) != manifest[RECEIVER]:
        raise RuntimeError("Scorer baseline pin differs")
    manifest[RECEIVER] = sources["receiver.py"]
    env_path = update.R47 / "scorer.env"
    env = env_path.read_text()
    pin = f"RELEASE_SHA256={update.sha(files['scorer-files.json'])}"
    if env.splitlines().count(pin) != 1:
        raise RuntimeError("Unexpected scorer environment pin")
    existing_assets = files["index.html"].parent / "assets"
    new_assets = [name for name in assets if not (existing_assets / name).exists()]
    for name in set(assets) - set(new_assets):
        if update.sha(existing_assets / name) != sources[name]:
            raise RuntimeError("Hashed UI asset differs")

    update.backup(BACKUP)
    for key, target in files.items():
        update.replace(BACKUP / key, target.read_bytes())
    update.replace(BACKUP / "new-assets.json", json.dumps(new_assets))
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    try:
        for name in new_assets:
            update.replace(existing_assets / name, (stage / name).read_bytes(), 0o644)
        for key in ("receiver.py", "index.html", "gateway.py", "security-bin"):
            update.replace(files[key], (stage / key).read_bytes(), 0o755 if key == "security-bin" else 0o644)
        update.replace(files["scorer-files.json"], json.dumps(manifest, sort_keys=True) + "\n", 0o644)
        update.replace(env_path, env.replace(pin, f"RELEASE_SHA256={update.sha(files['scorer-files.json'])}", 1))
        update.replace(update.SITE, candidate, 0o644)
        settle()
    except Exception:
        restore()
        raise
    print(json.dumps({"backup_sha": update.sha(BACKUP / "SHA256SUMS"),
                      "gateway_sha": update.sha(update.SITE), "security_sha": update.sha(output),
                      "scorer_manifest_sha": update.sha(files["scorer-files.json"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        restore()

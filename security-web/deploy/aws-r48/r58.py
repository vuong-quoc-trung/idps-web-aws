"""Deploy R58 UI and Rust API on the pinned WebSentinel staging instance."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

import r57
import refresh
import update

BACKUP = Path("/var/backups/websentinel-r58")
BASE_BINARY = "bebda62ca01e6e6d85ffddd3ea5bd2f7d19aeb171c70ee23e440dfc9a44249bb"
BASE_INDEX = "95b899efb7623be5fd378f8fd2201b6228ee816ec3bf43635519952cd9ec70d6"
BASE_SCORER = "a030a13faa65aedd49dfc024f035b269d9bfce58c639502ba6ec14c828e51a5e"
ORIGIN = "websentinal.duckdns.org"


def paths():
    release = update.ACTIVE.resolve(strict=True)
    return (release / "security/pbl4-security-demo",
            release / "security/frontend/dist")


def web_check(expected_index, expected_cache):
    for _ in range(12):
        output = update.run(
            "curl", "-fsS", "--max-time", "3", "--resolve", f"{ORIGIN}:443:127.0.0.1",
            "-D", "-", "-I", f"https://{ORIGIN}/", check=False,
        )
        if output.startswith("HTTP/") and "200 OK" in output and (
                not expected_cache or "cache-control: no-cache" in output.lower()):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("Gateway did not return Security HTML with the expected cache policy")
    page = update.run(
        "curl", "-fsS", "--max-time", "3", "--resolve", f"{ORIGIN}:443:127.0.0.1",
        f"https://{ORIGIN}/",
    )
    if page != expected_index.read_text().strip():
        raise RuntimeError("Gateway HTML differs from the installed frontend")
    for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', page):
        update.run("curl", "-fsS", "--max-time", "3", "--resolve", f"{ORIGIN}:443:127.0.0.1",
                   "-o", "/dev/null", f"https://{ORIGIN}{asset}")
    refresh.health()


def restart():
    update.run("systemctl", "restart", update.SEC, timeout=35)


def verify_backup():
    update.run("sha256sum", "--check", "--quiet", "SHA256SUMS", cwd=BACKUP, timeout=100)
    if update.sha(BACKUP / "security-bin") != BASE_BINARY:
        raise RuntimeError("Unexpected rollback binary")


def restore():
    verify_backup()
    binary, dist = paths()
    retired = dist.with_name(".r58-previous-dist")
    if retired.exists():
        if retired.is_symlink() or update.sha(retired / "index.html") != BASE_INDEX:
            raise RuntimeError("Unexpected rollback frontend")
        if dist.exists():
            with tempfile.TemporaryDirectory(prefix=".r58-displaced-", dir=dist.parent) as path:
                dist.rename(Path(path) / "dist")
                retired.rename(dist)
        else:
            retired.rename(dist)
    if update.sha(dist / "index.html") != BASE_INDEX:
        raise RuntimeError("Rollback frontend changed")
    update.replace(binary, (BACKUP / "security-bin").read_bytes(), 0o755)
    restart()
    web_check(dist / "index.html", False)


def install(stage):
    binary, dist = paths()
    retired = dist.with_name(".r58-previous-dist")
    scorer_manifest = r57.paths()["scorer-files.json"][0]
    if (BACKUP.exists() or retired.exists() or update.sha(binary) != BASE_BINARY
            or update.sha(dist / "index.html") != BASE_INDEX or update.sha(scorer_manifest) != BASE_SCORER):
        raise RuntimeError("Expected the verified R57 serving baseline")
    if shutil.disk_usage(BACKUP.parent).free < 3 * 1024**3:
        raise RuntimeError("Insufficient disk space for rollback")
    manifest = json.loads((stage / "manifest.json").read_text())
    names = sorted(n for n in manifest
                   if re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(?:js|css|png|svg|webp|ico)", n))
    if not names or set(manifest) != {"security.zst", "security.sha256", "index.html", *names}:
        raise RuntimeError("Invalid asset manifest")
    for name, digest in manifest.items():
        source = stage / name
        if source.is_symlink() or not source.is_file() or update.sha(source) != digest:
            raise RuntimeError(f"Staged digest mismatch for {name}")
    index_assets = set(re.findall(r'(?:src|href)="/(assets/[^"]+)"',
                                  (stage / "index.html").read_text()))
    if index_assets != set(names):
        raise RuntimeError("HTML and frontend asset manifest differ")
    candidate = stage / "candidate"
    update.run("zstd", "-qd", f"--patch-from={binary}", stage / "security.zst", "-o", candidate)
    if update.sha(candidate) != (stage / "security.sha256").read_text().strip():
        raise RuntimeError("Reconstructed binary digest differs")

    update.backup(BACKUP)
    update.replace(BACKUP / "security-bin", binary.read_bytes())
    update.replace(BACKUP / "SHA256SUMS", refresh.checksum_report(BACKUP))
    verify_backup()
    with tempfile.TemporaryDirectory(prefix=".r58-stage-", dir=dist.parent) as path:
        new_dist = Path(path) / "dist"
        new_dist.mkdir(mode=0o755)
        (new_dist / "assets").mkdir()
        (new_dist / "assets").chmod(0o755)
        for name in ("index.html", *names):
            update.replace(new_dist / name, (stage / name).read_bytes(), 0o644)
        new_dist.chmod(0o755)
        try:
            update.replace(binary, candidate.read_bytes(), 0o755)
            dist.rename(retired)
            new_dist.rename(dist)
            restart()
            web_check(dist / "index.html", True)
            r57.verify()
            for name in ("student.env", "security.env", "scorer.env"):
                if update.sha(update.R47 / name) != update.sha(BACKUP / name):
                    raise RuntimeError(f"Configuration changed for {name}")
        except BaseException:
            restore()
            raise
    print(json.dumps({"serving_sha": update.sha(binary), "index_sha": update.sha(dist / "index.html"),
                      "assets": {n: manifest[n] for n in names},
                      "backup_sha": update.sha(BACKUP / "SHA256SUMS"),
                      "scorer_manifest_sha": update.sha(scorer_manifest)}), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("install", "rollback"))
    args = cli.parse_args()
    os.umask(0o077)
    r57.verify()
    if args.action == "install":
        install(Path(__file__).resolve().parent)
    else:
        restore()

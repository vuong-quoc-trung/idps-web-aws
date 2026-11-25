"""Native-only, read-only admission before installing units or starting any backend."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from docker_pg import endpoint

PORTS = (23000,24443,28080,28081,28443,29443)


def partial_install(path, bundle):
    if path.resolve() != path or not path.is_dir():
        return False
    st = path.stat()
    if st.st_uid != 0 or st.st_mode & 0o022:
        return False
    if path == Path("/opt/ws-native"):
        return bundle == path/"current" and set(path.iterdir()) == {bundle}
    return path in (Path("/etc/ws-native"), Path("/var/lib/ws-native")) and not any(path.iterdir())


def check(bundle, resume=False):
    issues = []
    def require(ok, message):
        print("PASS" if ok else "BLOCKED", message)
        if not ok:
            issues.append(message)

    require(not Path("/run/systemd/container").exists(), "native system manager")
    subprocess.run(["sha256sum","--check","--quiet","SHA256SUMS"],cwd=bundle,check=True)
    binary = bundle/"security/pbl4-security-demo"
    data = binary.read_bytes()
    require(all(bytes.fromhex(line.split("|")[1]) in data for line in
            (bundle/"migrations.expected").read_text().splitlines()), "binary matches SQLx migration digest inventory")
    for cmd in ("java","nginx","suricata","nft","setfacl","systemd-analyze"):
        require(shutil.which(cmd) is not None, "executable "+cmd)
    # ss can return zero while reporting a netlink error on stderr.
    listeners = subprocess.run(["ss", "-Hltn"], capture_output=True, text=True)
    if listeners.returncode or listeners.stderr.strip():
        require(False, "cannot inspect listening TCP sockets")
    else:
        ports = {int(row.split()[3].rsplit(":", 1)[1]) for row in listeners.stdout.splitlines()}
        require(not ports.intersection(PORTS), "native ports free: "+str(PORTS))
    try:
        port = endpoint()
        require(True, f"PostgreSQL 17 Docker tools and loopback mapping on {port}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        require(False, f"PostgreSQL Docker unavailable: {type(exc).__name__}")
    for unit in sorted((bundle/"units").iterdir()):
        result = subprocess.run(["systemctl","show","-p","LoadState","--value",unit.name],
                                capture_output=True, text=True)
        require(result.returncode == 0 and result.stdout.strip() == "not-found",
                "unit name available: "+unit.name)
    for p in ("/etc/ws-native","/opt/ws-native","/var/lib/ws-native","/run/ws-native-leases"):
        path=Path(p)
        available = not path.exists() and not path.is_symlink()
        require(available or (resume and partial_install(path, bundle)), "native install path safe: "+p)
    return not issues


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle",type=Path)
    parser.add_argument("--resume-copied-bundle", action="store_true")
    args = parser.parse_args()
    sys.exit(0 if check(args.bundle.resolve(), args.resume_copied_bundle) else 1)

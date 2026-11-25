"""Admission and supervision for the EC2 scorer. The Local thermal path is separate."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.request

ROOT = Path("/sys/fs/cgroup")
EXPECTED = Path("/etc/websentinel-r47/cloud-identity.json")
ATTESTED = Path("/run/websentinel-r47-cloud/identity.json")
BOOT = Path("/proc/sys/kernel/random/boot_id")
CGROUP = ROOT / "websentinelr47.slice/websentinel-r47-scorer.service"
LIMITS = {"memory.max": 768 * 1024**2, "memory.swap.max": 0, "pids.max": 64}
METADATA = "http://169.254.169.254/latest/"
MAX_CPU_PERCENT = 25
MIN_DISK_FREE = 2 * 1024**3


class AdmissionError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise AdmissionError("Unexpected metadata redirect")


def protected_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r") as f:
        st = os.fstat(f.fileno())
        if st.st_uid != 0 or st.st_mode & 0o022 or not stat.S_ISREG(st.st_mode):
            raise AdmissionError("Identity file must be root-owned and immutable to the service")
        return json.load(f)


def metadata_identity():
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    token = urllib.request.Request(
        METADATA + "api/token", method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
    )
    with client.open(token, timeout=2) as response:
        credential = response.read(4096).decode("ascii")
    request = urllib.request.Request(
        METADATA + "dynamic/instance-identity/document",
        headers={"X-aws-ec2-metadata-token": credential},
    )
    with client.open(request, timeout=2) as response:
        return json.loads(response.read(8192))


def verify_identity(document, expected, vendor):
    fields = {"accountId", "instanceId", "region", "instanceType", "architecture"}
    if (vendor != "Amazon EC2" or expected.keys() != fields
            or any(document.get(key) != expected[key] for key in fields)
            or not re.fullmatch(r"\d{12}", expected["accountId"])
            or not re.fullmatch(r"i-[a-f0-9]{17}", expected["instanceId"])
            or expected["region"] != "ap-southeast-1"
            or expected["instanceType"] != "m7i-flex.large"
            or expected["architecture"] != "x86_64"):
        raise AdmissionError("EC2 identity does not match the staging deployment pin")
    return {key: document[key] for key in sorted(fields)}


def attest():
    if os.geteuid() != 0:
        raise AdmissionError("EC2 admission must run as root")
    expected = protected_json(EXPECTED)
    identity = verify_identity(metadata_identity(), expected,
                               Path("/sys/class/dmi/id/sys_vendor").read_text().strip())
    ATTESTED.parent.mkdir(mode=0o755, exist_ok=True)
    path = ATTESTED.with_suffix(".tmp")
    with path.open("x") as f:
        json.dump({"boot_id": BOOT.read_text().strip(), "identity": identity}, f)
        os.fchmod(f.fileno(), 0o644)
    path.replace(ATTESTED)
    print("Cloud admission verified; physical thermal monitoring NOT_APPLICABLE", flush=True)


def counters(path):
    return {k: int(v) for k, v in (line.split() for line in path.read_text().splitlines())}


def cpu_limit(path, ceiling):
    quota, period = map(int, path.read_text().split())
    if quota <= 0 or period <= 0 or quota * 100 != period * ceiling:
        raise AdmissionError("CPU quota readback differs from profile")


def limits():
    if not (ROOT / "cgroup.controllers").is_file():
        raise AdmissionError("Unified cgroup v2 is required")
    own = Path("/proc/self/cgroup").read_text().strip()
    if own != "0::/" + str(CGROUP.relative_to(ROOT)):
        raise AdmissionError("Scorer is outside its assigned systemd unit")
    for key, wanted in LIMITS.items():
        if int((CGROUP / key).read_text()) != wanted:
            raise AdmissionError(f"Kernel readback mismatch for {key}")
    if int((CGROUP / "memory.high").read_text()) != 608 * 1024**2:
        raise AdmissionError("Memory pressure limit differs from profile")
    cpu_limit(CGROUP / "cpu.max", MAX_CPU_PERCENT)
    cpu_limit(CGROUP.parent / "cpu.max", 150)
    for key, wanted in {"memory.max": 6144 * 1024**2, "memory.swap.max": 0, "pids.max": 512}.items():
        if int((CGROUP.parent / key).read_text()) != wanted:
            raise AdmissionError(f"Parent slice readback mismatch for {key}")
    for name in ("cpu.pressure", "memory.pressure", "io.pressure"):
        if not (CGROUP / name).read_text().startswith("some "):
            raise AdmissionError("Pressure telemetry is unavailable")


def verify_release(path):
    manifest = path / "files.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != os.environ["RELEASE_SHA256"]:
        raise AdmissionError("Frozen scorer release pin differs")
    for name, digest in json.loads(manifest.read_text()).items():
        candidate = path / name
        if not candidate.is_relative_to(path) or candidate.resolve() != candidate:
            raise AdmissionError("Unsafe scorer manifest path")
        with candidate.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != digest:
                raise AdmissionError("Scorer release bytes differ")


def ping():
    name = os.environ["NOTIFY_SOCKET"]
    if name.startswith("@"):
        name = "\0" + name[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
        channel.sendto(b"WATCHDOG=1", name)


def stop_child(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def run(release):
    expected = protected_json(EXPECTED)
    marker = protected_json(ATTESTED)
    if (marker["boot_id"] != BOOT.read_text().strip() or marker["identity"] != expected):
        raise AdmissionError("Cloud attestation is absent for this boot")
    if os.geteuid() == 0:
        raise AdmissionError("Scorer must use a dedicated unprivileged user")
    limits()
    verify_release(release)
    state = Path(os.environ["STATE_DIRECTORY"])
    runtime = Path(os.environ["RUNTIME_DIRECTORY"])
    private = state / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    if private.is_symlink() or private.stat().st_uid != os.geteuid() or private.stat().st_mode & 0o077:
        raise AdmissionError("Scorer receipt directory ownership differs")
    if shutil.disk_usage(state).free < MIN_DISK_FREE:
        raise AdmissionError("Insufficient disk headroom")
    oom = counters(CGROUP / "memory.events")["oom"]
    edge_uid = pwd.getpwnam("www-data").pw_uid
    if edge_uid == os.geteuid():
        raise AdmissionError("Scorer and gateway identities must differ")
    args = [
        sys.executable, "-IB", str(release / "ai-training/contracts/https-model-r36/serve.py"),
        "--socket", str(runtime / "receiver.sock"), "--database", str(private / "receipts.db"),
        "--journal", str(state / "observations.jsonl"), "--binary", str(release / "bin/scorer"),
        "--ort", str(release / "lib/onnxruntime.so"), "--slot", os.environ.get("MODEL_SLOT", "candidate"),
        "--lineage", os.environ["EVIDENCE_LINEAGE"], "--peer-uid", str(edge_uid),
        "--journal-gid", str(os.getgid()),
    ]
    env = {k: value for k, value in os.environ.items()
           if k not in {"WATCHDOG_PID", "WATCHDOG_USEC", "NOTIFY_SOCKET"}}
    process = subprocess.Popen(args, cwd=release, env=env)
    stopping = False

    def request_stop(*_):
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    try:
        while not stopping:
            if process.poll() is not None:
                return process.returncode or 1
            limits()
            if str(process.pid) not in (CGROUP / "cgroup.procs").read_text().split():
                raise AdmissionError("Scorer left the kernel resource envelope")
            if (counters(CGROUP / "memory.events")["oom"] != oom
                    or shutil.disk_usage(state).free < MIN_DISK_FREE):
                raise AdmissionError("Scorer stopped at the memory or disk safety gate")
            ping()
            time.sleep(0.5)
        return 0
    finally:
        stop_child(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("attest", "run"))
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "attest":
            attest()
            return 0
        if args.release is None:
            parser.error("--release is required for run")
        return run(args.release.resolve(strict=True))
    except (AdmissionError, OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
        print(f"Cloud scorer refused: {type(error).__name__}", file=sys.stderr, flush=True)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())

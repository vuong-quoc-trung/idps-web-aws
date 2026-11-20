"""Verify the installed release before executing the delegated sensor guardian."""

import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import sys


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    release = Path(__file__).resolve().parent
    manifest = release / "files.json"
    if sha(manifest) != os.environ["RELEASE_SHA256"]:
        raise ValueError("Release digest mismatch")
    for rel, expected in json.loads(manifest.read_text()).items():
        p = release / rel
        if p.resolve() != p or sha(p) != expected:
            raise ValueError("Release file verification failed")
    runtime, state = (
        Path(os.environ[k]) for k in ["RUNTIME_DIRECTORY", "STATE_DIRECTORY"]
    )
    private = state / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    if (
        private.is_symlink()
        or private.stat().st_uid != os.geteuid()
        or private.stat().st_mode & 0o077
    ):
        raise ValueError("Unsafe receipt directory")
    args = [
        sys.executable,
        "-IB",
        release / "ai-training/contracts/https-model-r36/serve.py",
        "--socket",
        runtime / "receiver.sock",
        "--database",
        private / "receipts.db",
        "--journal",
        state / "observations.jsonl",
        "--lineage",
        os.environ["EVIDENCE_LINEAGE"],
        "--slot",
        os.environ.get("MODEL_SLOT", "candidate"),
        "--binary",
        release / "bin/scorer",
        "--ort",
        release / "lib/onnxruntime.so",
    ]
    if os.environ.get("SINGLE_USER_STAGING") == "1":
        if "INVOCATION_ID" not in os.environ or os.getuid() == 0:
            raise ValueError("Invalid user staging identity")
    else:
        edge = pwd.getpwnam("websentinel-edge")
        if edge.pw_uid == os.geteuid() or os.geteuid() == 0:
            raise ValueError(
                "Separate unprivileged scorer and edge identities required"
            )
        if edge.pw_gid in {*os.getgroups(), os.getegid()}:
            raise ValueError("Scorer must have no access to the edge signing group")
        args += [
            "--peer-uid",
            str(edge.pw_uid),
            "--journal-gid",
            str(grp.getgrnam("websentinel-evidence").gr_gid),
        ]
    os.environ["PYTHONPATH"] = str(release / "ai-training/src")
    os.environ["PYTHONNOUSERSITE"] = "1"
    os.chdir(release)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-Bs",
            "-m",
            "idps_ai.training.delegated_guard",
            "--",
            *map(str, args),
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError) as exc:
        print("Release refused:", type(exc).__name__, str(exc), file=sys.stderr)
        sys.exit(78)

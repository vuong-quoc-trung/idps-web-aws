"""Package application builds and the pinned R38 scorer for Local monitoring."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERSION = "0.1.0-beta.1"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def transfer(source, target, mode=0o644):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Expected regular input file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)


def static(source, target):
    if not (source / "index.html").is_file():
        raise ValueError(f"Missing frontend build at {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("Unexpected frontend symlink")
        if path.is_file():
            if path.name.endswith(".map"):
                raise ValueError("Unexpected frontend source map")
            transfer(path, target / path.relative_to(source))


def build(args):
    name = f"idps-local-monitoring-{VERSION}-linux-amd64"
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / (name + ".tar.gz")
    checksums = args.output / "SHA256SUMS"
    if archive.exists() or checksums.exists():
        raise ValueError("Use a new output directory")
    expected = (HERE.parent / "local-r38/evidence/release-files.json").read_bytes()
    if (args.scorer / "files.json").read_bytes() != expected:
        raise ValueError("Scorer release manifest mismatch")
    with tempfile.TemporaryDirectory(dir=args.output) as work:
        stage = Path(work) / name
        for relative, digest in json.loads(expected).items():
            source = args.scorer / relative
            if sha(source) != digest:
                raise ValueError(f"Scorer release content mismatch: {relative}")
            transfer(
                source,
                stage / "scorer" / relative,
                0o755 if relative == "bin/scorer" else 0o644,
            )
        transfer(args.scorer / "files.json", stage / "scorer/files.json")
        for relative in ("LICENSE", "ThirdPartyNotices.txt"):
            transfer(
                args.ort_notices / relative, stage / "notices/onnxruntime" / relative
            )
        transfer(ROOT / "LICENSE", stage / "LICENSE")
        transfer(
            ROOT / "release/THIRD_PARTY_DATA.md", stage / "notices/WAF-provenance.md"
        )
        transfer(args.backend, stage / "security/pbl4-security-demo", 0o755)
        transfer(args.student, stage / "student/student.jar")
        static(args.dashboard, stage / "security/frontend/dist")
        static(args.frontend, stage / "student/frontend/dist")
        for relative in ("manage.py", "INSTALL.md", "beta_profile.py"):
            transfer(HERE / relative, stage / relative)
        for relative in (
            "websentinel-https-scorer.service",
            "websentinel-https.sysusers",
        ):
            transfer(HERE.parent / "local-r38" / relative, stage / "support" / relative)
        paths = (
            [
                "scripts/" + n
                for n in (
                    "prepare-proof-egress.py",
                    "prepare-nginx-host.py",
                    "prepare-suricata-post-proxy.py",
                    "proof-nginx-lifecycle.py",
                    "local-egress-guard.py",
                    "run-suricata-generation.py",
                    "proof-flow-readiness.py",
                    "pbl4-firewall-policy.py",
                    "pbl4.nft",
                )
            ]
            + [
                "nginx/" + n
                for n in (
                    "https-shadow-mirror.conf",
                    "pbl4-proxy.conf",
                    "pbl4-egress.conf.template",
                    "pbl4-access.conf",
                    "pbl4-edge-limits.conf",
                )
            ]
            + [
                "config/suricata/suricata.yaml",
                "config/suricata/transaction-evidence.lua",
                "deploy/ai-shadow/telemetry.conf",
                "suricata/pbl4.rules",
                "tests/njs/proof-probe.js",
            ]
        )
        for relative in paths:
            transfer(
                ROOT / "security-web" / relative,
                stage / "support/security-web" / relative,
            )
        (stage / "release.json").write_text(
            json.dumps(
                {
                    "version": VERSION,
                    "build_source": args.app_revision,
                    "platform": "Ubuntu 26.04 amd64",
                    "mode": "LOCAL_MONITORING",
                    "security_prevention_execution": False,
                    "postgresql": 18,
                },
                indent=2,
            )
            + "\n"
        )
        entries = [p for p in sorted(stage.rglob("*")) if p.is_file()]
        (stage / "SHA256SUMS").write_text(
            "".join(f"{sha(p)}  {p.relative_to(stage)}\n" for p in entries)
        )
        temporary = Path(work) / archive.name
        subprocess.run(
            [
                "tar",
                "--sort=name",
                "--mtime=@0",
                "--owner=0",
                "--group=0",
                "--numeric-owner",
                "-I",
                "gzip -n",
                "-cf",
                temporary,
                "-C",
                work,
                name,
            ],
            check=True,
        )
        temporary.rename(archive)
        checksums.write_text(f"{sha(archive)}  {archive.name}\n")
    print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "output",
        "backend",
        "student",
        "dashboard",
        "frontend",
        "scorer",
        "ort-notices",
    ):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--app-revision", required=True)
    build(parser.parse_args())

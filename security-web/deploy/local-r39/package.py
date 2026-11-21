"""Package application builds and the pinned R38 scorer for Local monitoring."""

import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

import release_inputs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERSION = "0.1.0-beta.2"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def transfer(source, target, mode=0o644):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Expected regular input file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)


BETA_MARK = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#153454"/>'
    '<path d="M14 21l7 23 11-16 11 16 7-23" fill="none" '
    'stroke="#fff" stroke-width="4" stroke-linejoin="round"/></svg>\n'
)


def static(source, target):
    if not (source / "index.html").is_file():
        raise ValueError(f"Missing frontend build at {source}")
    target.mkdir(parents=True)
    (target / "beta-mark.svg").write_text(BETA_MARK)
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Unexpected frontend symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.parts[0] == "images" or relative.name in {
            "favicon.svg",
            "icons.svg",
        }:
            continue
        if re.fullmatch(r"logo-security-[A-Za-z0-9_-]+\.png", path.name):
            continue
        if path.suffix not in {".html", ".js", ".css"}:
            raise ValueError(f"Unreviewed frontend output: {path.name}")
        text = path.read_text()
        text = re.sub(
            r"/assets/logo-security-[A-Za-z0-9_-]+\.png|/images/dut-logo\.jpg",
            "/beta-mark.svg",
            text,
        )
        text = (
            text.replace("image/jpeg", "image/svg+xml")
            if path.suffix == ".html"
            else text
        )
        text = text.replace(
            'type="image/png" href="/beta-mark.svg"',
            'type="image/svg+xml" href="/beta-mark.svg"',
        )
        text = text.replace("/favicon.svg", "/beta-mark.svg")
        text = text.replace("Logo Đại học Bách khoa Đà Nẵng", "WebSentinel Beta")
        text = re.sub(
            r",url\(/images/bkdn\.jpg\)\s*(?:center|50%)\s*/\s*cover", "", text
        )
        text = re.sub(
            r"""@import\s+["']https://fonts\.googleapis\.com/[^"']+["'];""", "", text
        )
        if any(
            name in text
            for name in ("/images/", "logo-security-", "fonts.googleapis.com/")
        ):
            raise ValueError(f"Unresolved third-party asset reference in {path.name}")
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)


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
        student = stage / "student"
        student.mkdir()
        java_count = release_inputs.split_student(
            args.student, args.maven_repo, student
        )
        notices = stage / "notices"
        inventory = {
            "java_publisher_downloads": java_count,
            "jvm_libraries_redistributed": False,
            "npm": release_inputs.frontend_notices(
                {
                    "Student Web": args.frontend.parent,
                    "Security Web": args.dashboard.parent,
                },
                notices,
            ),
            "rust": release_inputs.rust_notices(
                {
                    "security": ROOT / "security-web/Cargo.toml",
                    "scorer": ROOT
                    / "ai-training/contracts/quality-acceleration-r26/r26_rust/Cargo.toml",
                },
                args.cargo_home,
                notices,
            ),
        }
        (notices / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
        transfer(HERE / "RELEASE_NOTES.md", stage / "RELEASE_NOTES.md")
        static(args.dashboard, stage / "security/frontend/dist")
        static(args.frontend, stage / "student/frontend/dist")
        for relative in (
            "manage.py",
            "INSTALL.md",
            "beta_profile.py",
            "student_deps.py",
        ):
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
    parser.add_argument(
        "--maven-repo", type=Path, default=Path.home() / ".m2/repository"
    )
    parser.add_argument("--cargo-home", type=Path, default=Path.home() / ".cargo")
    parser.add_argument("--app-revision", required=True)
    build(parser.parse_args())

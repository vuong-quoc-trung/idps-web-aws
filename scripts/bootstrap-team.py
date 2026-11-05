#!/usr/bin/env python3
"""Clone -> isolated Python/dependencies -> checksum restore -> offline smoke.

Never starts Web/production services, creates deployment credentials, downloads
raw/private datasets or trains. Downloads only pinned public tools and explicitly
selected release groups. A local asset-dir is for prepublication verification.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UV_URL = "https://files.pythonhosted.org/packages/b9/93/0e053a2ca4523ee9825ccbedeb7121470d0a188933f11688b6d90d7f5c08/uv-0.13.7-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
UV_SHA = "2c9bdc4a872b60a93c5f26c0791089ea11585a4f9d3b3c017d78eb8487505e25"


def sha(p):
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def download(url, path, checksum, expected_bytes=None):
    path = Path(path)
    if path.exists():
        if sha(path) == checksum:
            return
        raise RuntimeError("Existing download checksum mismatch: " + path.name)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".download-", dir=path.parent)
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "AI-IDPS-Team-Bootstrap/1"}
        )
        with (
            urllib.request.urlopen(request, timeout=60) as incoming,
            os.fdopen(fd, "wb") as out,
        ):
            shutil.copyfileobj(incoming, out, 1024**2)
        if (
            sha(tmp) != checksum
            or expected_bytes is not None
            and Path(tmp).stat().st_size != expected_bytes
        ):
            raise RuntimeError("Downloaded asset checksum/size mismatch")
        os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def safe_destination(relative):
    p = Path(relative)
    if (
        p.is_absolute()
        or ".." in p.parts
        or not str(p).startswith("ai-training/.artifacts/")
    ):
        raise RuntimeError("Artifact destination outside allowed root")
    destination = ROOT / p
    if not destination.resolve().is_relative_to(ROOT):
        raise RuntimeError("Artifact path escaped project")
    if any(
        parent.is_symlink()
        for parent in [destination, *destination.parents]
        if parent.is_relative_to(ROOT)
    ):
        raise RuntimeError("Refusing symlink artifact destination")
    return destination


def restore(archive, state):
    objects = state / "objects"
    objects.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tarfile.open(archive, "r:gz") as tar:
        manifest = json.load(tar.extractfile("asset-manifest.json"))
        for member in tar:
            if member.name == "asset-manifest.json":
                continue
            if not member.isfile() or not re.fullmatch(
                r"objects/[0-9a-f]{64}", member.name
            ):
                raise RuntimeError("Unapproved archive member")
            checksum = member.name.split("/")[1]
            destination = objects / checksum
            if destination.exists():
                if sha(destination) != checksum:
                    raise RuntimeError("Object cache checksum mismatch")
                continue
            fd, tmp = tempfile.mkstemp(prefix=".object-", dir=objects)
            try:
                with os.fdopen(fd, "wb") as out:
                    shutil.copyfileobj(tar.extractfile(member), out, 1024**2)
                if sha(tmp) != checksum:
                    raise RuntimeError("Object content checksum mismatch")
                os.link(tmp, destination)
            finally:
                Path(tmp).unlink(missing_ok=True)
    count = 0
    for entry in manifest["entries"]:
        source = objects / entry["sha256"]
        destination = safe_destination(entry["destination"])
        if not source.is_file() or source.stat().st_size != entry["bytes"]:
            raise RuntimeError("Missing object")
        if destination.exists():
            if not destination.is_file() or sha(destination) != entry["sha256"]:
                raise RuntimeError(
                    "Refusing to overwrite an existing artifact: "
                    + entry["destination"]
                )
        else:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with source.open("rb") as incoming, destination.open("xb") as out:
                shutil.copyfileobj(incoming, out, 1024**2)
            destination.chmod(0o600)
        count += 1
    return count


def setup_python(tools, state):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise RuntimeError(
            "Automated managed toolchain currently supports Linuxx86_64. Install Python3.12.14 and exact ai-training requirements manually on other platforms; model compatibility must be verified."
        )
    wheel = tools / "uv.whl"
    download(UV_URL, wheel, UV_SHA)
    uv = tools / "uv"
    if not uv.exists():
        with zipfile.ZipFile(wheel) as archive:
            members = [n for n in archive.namelist() if n.endswith("/uv")]
            if len(members) != 1:
                raise RuntimeError("Unexpected pinned uv wheel layout")
            with uv.open("xb") as out:
                out.write(archive.read(members[0]))
        uv.chmod(0o700)
    env = os.environ.copy()
    env.update(
        {
            "UV_PYTHON_INSTALL_DIR": str(tools / "python"),
            "UV_PYTHON_BIN_DIR": str(tools / "bin"),
            "UV_CACHE_DIR": str(tools / "cache"),
            "UV_SYSTEM_CERTS": "true",
            "UV_NO_CACHE": "1",
            "UV_NO_CONFIG": "1",
            "UV_NO_ENV_FILE": "1",
            "UV_CONCURRENT_DOWNLOADS": "2",
            "UV_CONCURRENT_INSTALLS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    def run(args):
        subprocess.run([str(uv), *args], env=env, cwd=ROOT, check=True)

    run(["python", "install", "3.12.14", "--no-cache"])
    python = subprocess.check_output(
        [str(uv), "python", "find", "--managed-python", "3.12.14"],
        env=env,
        cwd=ROOT,
        text=True,
    ).strip()
    venv = ROOT / "ai-training/.venv"
    venv_preexisted = venv.exists()
    if not venv_preexisted:
        run(["venv", "--python", python, str(venv)])
    interpreter = venv / "bin/python"
    actual = subprocess.check_output(
        [str(interpreter), "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if actual != "3.12.14":
        raise RuntimeError(
            "Existing venv is not Python3.12.14; choose a new clone, do not overwrite it"
        )
    run(
        [
            "pip",
            "install",
            "--python",
            str(interpreter),
            "--no-cache",
            "--index-url",
            "https://pypi.org/simple",
            "--only-binary",
            ":all:",
            "-r",
            str(ROOT / "ai-training/requirements.txt"),
        ]
    )
    run(
        [
            "pip",
            "install",
            "--python",
            str(interpreter),
            "--no-cache",
            "--index-url",
            "https://pypi.org/simple",
            "--no-deps",
            "-e",
            str(ROOT / "ai-training"),
        ]
    )
    (state / "python-environment.json").write_text(
        json.dumps(
            {
                "python": actual,
                "managed_interpreter": python,
                "requirements_sha256": sha(ROOT / "ai-training/requirements.txt"),
                "existing_project_venv_reused": venv_preexisted,
                "external_package_cache_enabled": False,
            },
            indent=2,
        )
        + "\n"
    )
    return interpreter, env


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--asset-dir",
        type=Path,
        help="Local release assets for prepublication verification only",
    )
    p.add_argument(
        "--with-research-data",
        action="store_true",
        help="Opt in to numeric WAF derivative tensors and new training checkpoint state",
    )
    p.add_argument("--with-historical-models", action="store_true")
    p.add_argument(
        "--tests",
        action="store_true",
        help="Run non-training contract/safety tests only",
    )
    a = p.parse_args()
    os.umask(0o077)
    state = ROOT / ".team-state"
    state.mkdir(mode=0o700, exist_ok=True)
    tools = ROOT / ".team-tools"
    tools.mkdir(mode=0o700, exist_ok=True)
    release = json.loads((ROOT / "release/assets.json").read_text())
    groups = {"inference"}
    if a.with_research_data:
        groups.add("request_training")
    if a.with_historical_models:
        groups.add("historical_models")
    python, env = setup_python(tools, state)
    restored = {}
    for asset in release["assets"]:
        if asset["group"] not in groups:
            continue
        archive = state / "downloads" / asset["name"]
        if a.asset_dir:
            source = a.asset_dir.resolve() / asset["name"]
            if (
                sha(source) != asset["sha256"]
                or source.stat().st_size != asset["bytes"]
            ):
                raise RuntimeError("Local asset checksum mismatch")
            archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not archive.exists():
                shutil.copyfile(source, archive)
        else:
            download(asset["url"], archive, asset["sha256"], asset["bytes"])
        if sha(archive) != asset["sha256"]:
            raise RuntimeError("Asset changed before restore")
        restored[asset["group"]] = restore(archive, state)
    subprocess.run(
        [str(python), str(ROOT / "scripts/verify-team-models.py")],
        env=env,
        cwd=ROOT,
        check=True,
    )
    actual = json.loads((state / "model-smoke-report.json").read_text())["observed"]
    if a.tests:
        subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "ai-training/tests/test_mvp_inference.py",
                "ai-training/tests/test_p0_research.py",
                "ai-training/tests/test_integration_candidate.py",
            ],
            env=env,
            cwd=ROOT,
            check=True,
        )
    report = {
        "status": "TEAM_INFERENCE_SETUP_VERIFIED",
        "release_tag": release["release_tag"],
        "models": ["GLU207 frozen", "Request Intelligence v2 frozen"],
        "smoke_records": len(actual),
        "restored_groups": restored,
        "new_training_started": False,
        "services_started": False,
        "private_raw_or_sealed_data_downloaded": False,
        "inference_models_ready": True,
        "request_training_material_ready": "request_training" in restored,
        "GLU_full_training_dataset": "RESTRICTED_LOCAL_NOT_DISTRIBUTED",
        "independent_GT_evidence": "PRIVATE_LOCAL_PENDING_REVIEW",
        "tests_requested": a.tests,
        "restore_source": "LOCAL_PREPUBLICATION_ASSETS"
        if a.asset_dir
        else "PUBLIC_GITHUB_RELEASE",
        "platform": platform.platform(),
    }
    (state / "bootstrap-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print("Team setup failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)

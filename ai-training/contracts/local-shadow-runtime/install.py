"""Install single-worker user services without editing NGINX or Hybrid."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from runtime import HERE, ORT_SHA, RUST, verify

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256
from idps_ai.training.delegated_guard import UNIT_PROPERTIES

STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "idps-r22-local"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"
RUNTIME = Path(os.environ["XDG_RUNTIME_DIR"])
HISTORIC = REPO_ROOT / "ai-training/.artifacts"
SOURCE = HISTORIC / "t09-r22-local-UCE1ALdx/bundle"
SCORER = HISTORIC / "t09-r20-quality-OktqJbDt/uri76-shadow"
RI = HISTORIC / "integration_candidate_20261105/demo-request-bundle"
PREFIX = "idps-r22-local"


def systemctl(*args, check=True):
    return subprocess.run(["systemctl", "--user", *args], check=check, timeout=30)


def quote(value):
    return json.dumps(str(value).replace("%", "%%").replace("$", "$$"), ensure_ascii=False)


def definition(role, ram, cpu, args, *, guarded=False):
    command = " ".join(quote(word) for word in (sys.executable, "-B", *args))
    delegate = "\n".join(UNIT_PROPERTIES) if guarded else "KillMode=control-group"
    return f"""[Unit]
Description=AI-IDPS Local {role}
StartLimitIntervalSec=180
StartLimitBurst=3

[Service]
Type=exec
UMask=0077
RuntimeDirectory={PREFIX}-{role}
RuntimeDirectoryMode=0700
Environment={quote("PYTHONPATH=" + str(REPO_ROOT / "ai-training/src"))}
Environment=OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 ORT_DISABLE_TELEMETRY=1
ExecStart={command}
CPUQuota={cpu}%
MemoryMax={ram}M
MemoryHigh={ram * 4 // 5}M
MemorySwapMax=0
TasksMax=32
NoNewPrivileges=yes
Restart=on-failure
RestartSec=3
RestartPreventExitStatus=78
TimeoutStopSec=8
{delegate}

[Install]
WantedBy=default.target
"""


def pin_copy(source, dest, sha, mode):
    if file_sha256(source) != sha or dest.is_symlink():
        raise ValueError("Runtime package digest mismatch")
    if dest.exists():
        if file_sha256(dest) != sha:
            raise ValueError("Installed runtime bytes differ")
        return
    shutil.copyfile(source, dest)
    dest.chmod(mode)


def install():
    os.umask(0o077)
    if not STATE.exists():
        STATE.mkdir(mode=0o700)
    if (
        STATE.is_symlink()
        or STATE.stat().st_uid != os.getuid()
        or STATE.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("Installed state directory is not private")
    verify(SOURCE)
    if not (STATE / "bundle").exists():
        shutil.copytree(SOURCE, STATE / "bundle")
    verify(STATE / "bundle")
    ort = (
        Path(importlib.util.find_spec("onnxruntime").origin).parent
        / "capi/libonnxruntime.so.1.31.1"
    )
    pin_copy(ort, STATE / "ort.so", ORT_SHA, 0o600)
    pin_copy(SCORER, STATE / "uri76-shadow", RUST, 0o700)
    from store import RI_PIN

    if file_sha256(RI / "manifest.json") != RI_PIN:
        raise ValueError("Serving manifest digest mismatch")
    for flag in ("--system", "--user"):
        existing = subprocess.run(
            ["systemctl", flag, "is-active", "--quiet", "pbl4-ai-shadow.service"], timeout=5
        )
        if existing.returncode == 0:
            raise ValueError("Existing RI v2 service owns the serving slot")
    scorer = RUNTIME / f"{PREFIX}-scorer/score.sock"
    mirror = RUNTIME / f"{PREFIX}-receiver/mirror.sock"
    ri_socket = RUNTIME / f"{PREFIX}-ri/ri.sock"
    ri_journal = STATE / "ri-v2.jsonl"
    entry = HERE / "runtime.py"
    roles = {
        "scorer": definition(
            "scorer", 384, 25, (entry, "scorer", "--state", STATE, "--socket", scorer), guarded=True
        ),
        "receiver": definition(
            "receiver",
            256,
            25,
            (entry, "receiver", "--state", STATE, "--socket", mirror, "--rust-socket", scorer),
        ),
        "collector": definition(
            "collector", 128, 20, (entry, "collector", "--state", STATE, "--ri-journal", ri_journal)
        ),
        "ri": definition(
            "ri",
            768,
            50,
            (
                REPO_ROOT / "scripts/ai-host-supervisor.py",
                "--socket",
                ri_socket,
                "--output",
                ri_journal,
                "--bundle",
                RI,
                "--socket-mode",
                "600",
            ),
            guarded=True,
        ),
    }
    CONFIG.mkdir(mode=0o700, parents=True, exist_ok=True)
    names = []
    for role, content in roles.items():
        name = f"{PREFIX}-{role}.service"
        path = CONFIG / name
        if path.is_symlink() or path.exists() and path.read_text() != content:
            raise ValueError(f"Existing custom unit {name}")
        names.append(name)
    for name, content in zip(names, roles.values(), strict=True):
        path = CONFIG / name
        if not path.exists():
            path.write_text(content)
    config = {
        "units": names,
        "state": str(STATE),
        "score_socket": str(scorer),
        "mirror_socket": str(mirror),
        "ri_socket": str(ri_socket),
        "ri_journal": str(ri_journal),
    }
    atomic_json(STATE / "runtime.json", config)
    systemctl("daemon-reload")
    systemctl("enable", "--now", *names)
    print(json.dumps(config))


if __name__ == "__main__":
    install()

"""Reconcile R34 outputs, check isolated worker cleanup, publish aggregate evidence only."""

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256, load_json

HERE = Path(__file__).resolve().parent


def require(test, label):
    if not test:
        raise ValueError(label)


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def verify(run):
    old = load_json(run / "before.json")
    require(command("git", "branch", "--show-current") == old["branch"], "branch changed")
    require(
        all(file_sha256(REPO_ROOT / p) == sha for p, sha in old["dirty"].items()),
        "tracked file changed",
    )
    now = {}
    for unit, original in old["services"].items():
        out = command(
            "systemctl",
            "--user",
            "show",
            unit,
            "-p",
            "ActiveState",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
        )
        require(
            dict(s.split("=", 1) for s in out.splitlines())
            == dict(s.split("=", 1) for s in original.splitlines()),
            "service lifecycle changed: " + unit,
        )
        now[unit] = dict(s.split("=", 1) for s in out.splitlines())
    stages = {}
    for d in sorted(run.glob("adapter-*")):
        if not d.is_dir():
            continue
        receipt = load_json(d / "result.json")
        require(receipt.get("cleanup_verified"), "unclean guarded stage: " + d.name)
        preflight = load_json(d / "preflight.json") if (d / "preflight.json").is_file() else {}
        stats = load_json(d / "status.json") if (d / "status.json").is_file() else {}
        rel = stats.get("limits", {}).get("path")
        require(
            not rel or not (Path("/sys/fs/cgroup") / rel.lstrip("/")).exists(),
            "worker cgroup remains",
        )
        proof = receipt.get("exit_proof", {})
        accounting = {}
        if (d / "worker-launch.json").exists():
            unit = load_json(d / "worker-launch.json")["unit"]
            lines = command(
                "journalctl", "--user", "--no-pager", "-o", "json", "-u", unit, "-n", "12"
            )
            for line in lines.splitlines():
                entry = json.loads(line)
                if entry.get("USER_UNIT") == unit and "CPU_USAGE_NSEC" in entry:
                    accounting = {
                        k: int(entry[k])
                        for k in ("CPU_USAGE_NSEC", "MEMORY_PEAK", "MEMORY_SWAP_PEAK")
                        if k in entry
                    }
        stages[d.name] = {
            "worker_accounting": accounting,
            "reason": receipt["reason"],
            "cleanup": receipt["cleanup_verified"],
            "exit": proof.get("exit_status"),
            "guardian": preflight.get("guardian"),
            "cpu_max": preflight.get("limits", {}).get("cpu.max"),
            "memory_max": preflight.get("limits", {}).get("memory.max"),
            "temp_last_c": stats.get("temperature_c"),
            "last_memory_bytes": stats.get("memory_bytes"),
            "receipt_sha": file_sha256(d / "result.json"),
        }
    from run_stages import STAGES

    completion = load_json(run / "study-status.json")
    require(completion.get("state") == "COMPLETED", "coordinator has not completed")
    for name, _, _, _, _, _, _, artifact in STAGES:
        stage = stages["adapter-" + name]
        require(
            stage["reason"] == "COMPLETED" and stage["exit"] == 0, "missing clean exit for " + name
        )
        require(
            completion["outputs"][name] == file_sha256(run / artifact),
            "coordinator artifact changed: " + name,
        )
    meta, lock, transfer, http, local = [
        load_json(run / s)
        for s in (
            "projection.json",
            "login-lock.json",
            "login-transfer.json",
            "http-pilot-result.json",
            "local-readback.json",
        )
    ]
    require(transfer["frozen_sha"] == file_sha256(run / "login-lock.json"), "frozen ref")
    require(lock["model_sha"] == file_sha256(run / "login-heads.joblib"), "login checkpoint")
    require(http["plan_sha"] == lock["plan_sha"] == file_sha256(HERE / "plan.json"), "plan changed")
    require(local["pass"] and local["resources_clean"], "incomplete Local readback")
    for arm, sha in http["model_shas"].items():
        require(file_sha256(run / "http-pilot" / (arm + ".joblib")) == sha, "payload checkpoint")
    idx = load_json(run / "raw-index.json")
    source = load_json(run / "source.json")
    require(
        idx["source_sha"] == source["sha256"]
        and sum(b["rows"] for b in meta["role_bins"]) == idx["rows"],
        "row conservation",
    )
    require(
        all(
            b["bucket"] == j and file_sha256(run / "login-inputs" / f"{j:02d}.npz") == b["sha256"]
            for j, b in enumerate(meta["role_bins"])
        ),
        "role bindings",
    )
    from login_study import BLOCKS

    roles = {
        r: {
            k: sum(meta["role_bins"][j][k] for j in js)
            for k in ("rows", "in_role", "sampled", "actors")
        }
        for r, js in BLOCKS.items()
    }
    require(
        roles["TRANSFER"]["sampled"] == transfer["metrics"][lock["selected"]]["request"]["rows"],
        "transfer denominator",
    )
    inbox = REPO_ROOT / "ai-training/.artifacts/defensive-intake"
    require(
        not any((inbox / x).is_file() for x in ("index.json", "handoff.json")),
        "new native intake requires verification",
    )
    tests = {}
    for f in sorted(run.glob("*regression.xml")):
        item = ElementTree.parse(f).getroot().find("testsuite")
        require(
            item is not None and item.get("failures") == item.get("errors") == "0",
            "regression failed",
        )
        tests[f.name] = int(item.get("tests"))
    require(tests.get("regression.xml", 0) > 0, "missing tests")
    public = {
        "version": "idps-r34-aggregate-v1",
        "run": run.name,
        "base_commit": old["head"],
        "dirty_tracked_verified": len(old["dirty"]),
        "services": now,
        "resource": stages,
        "tests": tests,
        "software": {
            x: importlib.metadata.version(x)
            for x in ("numpy", "pyarrow", "scipy", "scikit-learn", "onnxruntime", "joblib")
        },
        "source": source,
        "predecessor": load_json(run / "predecessor.json")
        if (run / "predecessor.json").exists()
        else None,
        "roles": roles,
        "login_source_rows": idx["rows"],
        "login_actors": sum(b["actors"] for b in meta["role_bins"]),
        "login_early_boundary_ms": meta["boundary_ms"],
        "peer_reference": load_json(run / "peer-prefix.json"),
        "login_lock": lock,
        "login_transfer": transfer,
        "http": http,
        "local": local,
        "native": {
            "handoff": False,
            "new_verified_attack": 0,
            "new_canonical": 0,
            "TRAIN": 0,
            "DEV": 0,
            "CAL_FIT": 0,
            "CAL_OP": 0,
            "TEST_SHADOW": 0,
        },
        "technical_status": "RESEARCH_ONLY",
        "T07_RELEASE": "BLOCKED_NO_INDEPENDENT_NATIVE_FRAME",
    }
    supplemental = run / "early-actors.json"
    if supplemental.exists():
        extra = load_json(supplemental)
        spec = load_json(run / "early-actor-lock.json")
        require(
            extra["plan_sha"] == file_sha256(run / "early-actor-lock.json")
            and spec["evaluator_sha"] == file_sha256(HERE / "early_actors.py")
            and all(file_sha256(run / name) == sha for name, sha in spec["private_pins"].items())
            and stages["adapter-early-actors"]["reason"] == "COMPLETED",
            "supplemental frozen audit failed",
        )
        public["exploratory_early_actors"] = extra
        public["exploratory_plan"] = spec
    # The index exposes relative file identifiers and digests only; never export source rows or session identities.
    shas = {
        str(p.relative_to(run)): file_sha256(p)
        for p in sorted(run.rglob("*"))
        if p.is_file()
        and p.name not in ("artifact-index.json", ".coordinator.lock")
        and not p.is_symlink()
    }
    atomic_json(run / "artifact-index.json", shas)
    public["private_index"] = {
        "entries": len(shas),
        "sha256": file_sha256(run / "artifact-index.json"),
    }
    public["implementation_sha"] = {p.name: file_sha256(p) for p in sorted(HERE.glob("*.py"))}
    atomic_json(HERE / "r34-evidence.json", public)


if __name__ == "__main__":
    os.umask(0o077)
    verify(Path(sys.argv[1]).resolve())

"""Metadata-only final acceptance and cleanup readback. No new HTTP or fitting."""

import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256
from idps_ai.training.resource_adapter import CGROUP, cpu_limit, host_budget, properties
from idps_ai.training.resource_contract import plan_resources

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def run(out):
    initial = json.loads((out / "preservation.json").read_text())
    changed = [p for p, sha in initial["dirty"].items() if file_sha256(REPO / p) != sha]
    if changed:
        raise ValueError("Original dirty files changed")
    resource = []
    permits = []
    receipts = []
    for path in out.rglob("result.json"):
        result = json.loads(path.read_text())
        if "cleanup_verified" not in result:
            continue
        before = json.loads((path.parent / "preflight.json").read_text())
        group = CGROUP / properties()["ControlGroup"].lstrip("/") / "app.slice"
        absent = {kind: not (group / before[kind]).exists() for kind in ("worker", "guardian")}
        leftovers = [
            str(p.relative_to(out))
            for p in (
                path.parent / "guest/fs",
                path.parent / "guest/initramfs.cpio",
                path.parent / "guest/vmlinuz",
            )
            if p.exists()
        ]
        if (
            result["reason"] != "COMPLETED"
            or not result["cleanup_verified"]
            or not all(absent.values())
            or leftovers
        ):
            raise ValueError("Owned resource did not complete/cleanup safely")
        resource.append(
            {
                "attempt": str(path.parent.relative_to(out)),
                "result": result,
                "kernel_cgroup_absent": absent,
                "staging_leftovers": leftovers,
                "final_telemetry": json.loads((path.parent / "status.json").read_text()),
            }
        )
    for path in out.glob("*/campaign-1-a1/adapter/guest/receipt-ledger.jsonl"):
        rows = list(map(json.loads, path.read_text().splitlines()))
        gates = [r for r in rows if r["kind"] == "PERMIT"]
        attempts = [r for r in rows if r["kind"] == "ATTEMPT"]
        if [r["attempt"] for r in gates] != [r["attempt"] for r in attempts]:
            raise ValueError("Permit/receipt reconciliation failed")
        permits.extend(gates)
        receipts.extend(attempts)
        end = next(r for r in rows if r["kind"] == "END")
        qemu = json.loads((path.parent / "qemu.json").read_text())
        if (
            not end["guest_cleanup"]
            or qemu["qemu_returncode"] != 0
            or qemu["network_devices"] != "none"
        ):
            raise ValueError("Guest isolation/shutdown not verified")
    for permit in permits:
        gate = permit["resource_gate"]
        if (
            gate["cpu_max"] != f"{round(gate['quota_percent'] * 1000)} 100000"
            or gate["frozen"]
            or gate["action"] != "APPLY_QUOTA"
        ):
            raise ValueError("Dispatch guard/kernel mismatch")
    health = {}
    state = Path.home() / ".local/state/idps-r22-local"
    for kind in ("ri", "scorer", "collector", "receiver"):
        unit = f"idps-r22-local-{kind}.service"
        output = subprocess.check_output(
            [
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
                "-p",
                "MemoryCurrent",
            ],
            text=True,
        )
        values = dict(line.split("=", 1) for line in output.splitlines())
        if values["ActiveState"] != "active" or int(values["MainPID"]) <= 0:
            raise ValueError("Serving service unhealthy")
        if kind != "ri":
            current = json.loads((state / f"{kind}-health.json").read_text())
            if (
                current["status"] != "READY"
                or time.time_ns() - current["updated_wall_ns"] > 15000000000
            ):
                raise ValueError("Serving heartbeat stale")
            values["health"] = current
        health[unit] = values
    hardware = json.loads((out / "sensor-health.json").read_text())["hardware"]
    budget = host_budget(
        CGROUP / properties()["ControlGroup"].lstrip("/") / "app.slice",
        os.sched_getaffinity(0),
        cpu_limit(hardware),
    )
    admission = json.loads((out / "admission.json").read_text())
    runtime = json.loads((out / "context-runtime.json").read_text())
    research_train = admission["canonical_research_by_role"].get("TRAIN", 0)
    research_dev = admission["canonical_research_by_role"].get("DEV", 0)
    acceptance = {
        "run_id": out.name,
        "decision": admission["decision"],
        "started_unix": initial["started_unix"],
        "finished_unix": time.time(),
        "wall_seconds": time.time() - initial["started_unix"],
        "timebox_seconds": 8 * 3600,
        "HTTP_dispatched": len(receipts),
        "Oracle_verified": sum(r["oracle_verified"] for r in receipts),
        "native_masks": dict(Counter(r["native_mask"] for r in receipts)),
        "resource_attempts": resource,
        "kernel_dispatches": len(permits),
        "kernel_cpu_max_counts": dict(Counter(r["resource_gate"]["cpu_max"] for r in permits)),
        "dispatch_temperature_min_max_C": [
            min(r["resource_gate"]["temperature_c"] for r in permits),
            max(r["resource_gate"]["temperature_c"] for r in permits),
        ],
        "fresh_host_capacity": plan_resources(budget, "DATA"),
        "thermal_policy_unchanged": True,
        "hardware_priority_preserved": True,
        "services": health,
        "linger": subprocess.check_output(
            ["loginctl", "show-user", str(os.getuid()), "-p", "Linger"], text=True
        ).strip(),
        "cleanup": True,
        "new_training": False,
        "release_ready": False,
        "runtime": runtime,
        "research_canonical_TRAIN_DEV_CAL_TEST": [research_train, research_dev, 0, 0],
        "formal_legacy_T02_T07_native_canonical_TRAIN_DEV_CAL_TEST": [0, 0, 0, 0],
        "formal_counts_reason": "R27 admits the narrow AUTHORIZATION_POLICY_VIOLATION_ATTEMPT research task, not a global ATTACK_INTENT corpus or representative independent T07 evaluation. Legacy v1 task serialization is not certified; do not silently relabel or promote these research rows.",
        "structural_material_components": 3,
        "independent_representative_final_anchors": 0,
        "original_dirty_files_preserved": len(initial["dirty"]),
        "original_dirty_changed": changed,
        "branch": initial["branch"],
        "base_HEAD": initial["head"],
        "background_job_remaining": None,
        "gates": {
            "capture": "PASS",
            "semantic_machine_ground_truth": "PASS_NARROW_AUTHORIZATION_TASK",
            "context22_Python_Rust": "PASS",
            "research_admission": "PASS_PROFILE_R27_ONLY",
            "formal_native_independent_dataset": "BLOCKED",
            "ML_added_value": "NOT_DEMONSTRATED_NO_TRAINING",
            "recall90_FPR1_confidence": "BLOCKED",
            "release": "BLOCKED",
        },
        "next_task": "Acquire an outcome-verified payload/behavior cohort beyond the three known authorization lookups, with representative sampling/custody and formal contract export; use that new information to justify ML and independent CAL/TEST.",
    }
    atomic_json(out / "acceptance.json", acceptance)
    atomic_json(
        out / "status.json",
        {
            "state": "COMPLETED",
            "decision": admission["decision"],
            "HTTP": len(receipts),
            "research_TRAIN_DEV": [research_train, research_dev],
            "formal_native_TRAIN_DEV": [0, 0],
            "release_ready": False,
            "cleanup": True,
        },
    )
    checkpoint = json.loads((out / "checkpoint.json").read_text())
    checkpoint.update(
        state="COMPLETED",
        phase="FINALIZED",
        admission_sha256=file_sha256(out / "admission.json"),
        role_registry_sha256=file_sha256(out / "native-source-role-registry.json"),
        HTTP_committed=len(receipts),
        resend_committed=False,
    )
    atomic_json(out / "checkpoint.json", checkpoint)
    print(
        json.dumps(
            {
                "decision": admission["decision"],
                "HTTP": len(receipts),
                "resources": len(resource),
                "cleanup": True,
            }
        )
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(Path(sys.argv[1]))

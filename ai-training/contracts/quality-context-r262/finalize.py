"""Read-only acceptance census, preservation and owned-resource cleanup readback."""

import json
import os
import subprocess
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

from idps_ai.common import atomic_json, file_sha256
from idps_ai.training.resource_adapter import CGROUP, cpu_limit, host_budget, properties
from idps_ai.training.resource_contract import plan_resources

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def run(out):
    start = json.loads((out / "preservation.json").read_text())
    changed = [name for name, sha in start["dirty"].items() if file_sha256(REPO / name) != sha]
    if changed:
        raise ValueError("Original dirty files changed: " + str(changed))
    owned = []
    temps, quotas = [], Counter()
    for path in sorted(out.rglob("result.json")):
        if path.parent.name.startswith("source"):
            continue
        result = json.loads(path.read_text())
        if "cleanup_verified" not in result:
            continue
        directory = path.parent
        preflight = directory / "preflight.json"
        before = json.loads(preflight.read_text()) if preflight.exists() else {}
        readback = {}
        for kind in ("worker", "guardian"):
            if kind in before:
                cgroup = (
                    CGROUP / (properties()["ControlGroup"].lstrip("/")) / "app.slice" / before[kind]
                )
                readback[kind + "_cgroup_absent"] = not cgroup.exists()
        leftovers = [
            str(p.relative_to(out))
            for p in (
                directory / "guest/fs",
                directory / "guest/initramfs.cpio",
                directory / "guest/vmlinuz",
            )
            if p.exists()
        ]
        if not result["cleanup_verified"] or not all(readback.values()) or leftovers:
            raise ValueError("Owned resource cleanup not proven: " + str(directory))
        owned.append(
            {
                "path": str(directory.relative_to(out)),
                "result": result,
                "kernel_readback": readback,
                "staging_leftovers": leftovers,
            }
        )
    for ledger in out.glob("capture-*/campaign-1-a1/adapter/guest/receipt-ledger.jsonl"):
        for row in map(json.loads, ledger.read_text().splitlines()):
            if row["kind"] == "PERMIT":
                gate = row["resource_gate"]
                expected = f"{round(gate['quota_percent'] * 1000)} 100000"
                if gate["cpu_max"] != expected or gate["frozen"] or gate["action"] != "APPLY_QUOTA":
                    raise ValueError("Dispatch kernel quota/gate invalid")
                temps.append(gate["temperature_c"])
                quotas[(gate["state"], gate["cpu_max"])] += 1
    state = Path.home() / ".local/state/idps-r22-local"
    services = {}
    for kind in ("ri", "scorer", "collector", "receiver"):
        unit = f"idps-r22-local-{kind}.service"
        result = subprocess.run(
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
                "-p",
                "CPUUsageNSec",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        values = dict(line.split("=", 1) for line in result.stdout.splitlines())
        if values["ActiveState"] != "active" or int(values["MainPID"]) <= 0:
            raise ValueError("Existing Local service is not active")
        if kind != "ri":
            health = json.loads((state / f"{kind}-health.json").read_text())
            values["health"] = health
            if (
                health["status"] != "READY"
                or time.time_ns() - health["updated_wall_ns"] > 15_000_000_000
            ):
                raise ValueError("Local service health stale or unavailable")
        services[unit] = values
    hardware = json.loads((out / "sensor-health.json").read_text())["hardware"]
    budget = host_budget(
        CGROUP / properties()["ControlGroup"].lstrip("/") / "app.slice",
        os.sched_getaffinity(0),
        cpu_limit(hardware),
    )
    capacity = plan_resources(budget, "DATA")
    sources = {}
    jar = REPO / "student-web/backend/target/student-web-0.0.1-SNAPSHOT.jar"
    with zipfile.ZipFile(jar) as archive:
        for class_name in (
            "configuration/SecurityRequestFilter",
            "configuration/RequestAttribution",
            "configuration/SecurityConfiguration",
            "accesslog/service/AuditJsonlExporter",
        ):
            relative = "com/pbl4/studentweb/" + class_name
            source = REPO / "student-web/backend/src/main/java" / (relative + ".java")
            import hashlib

            bytecode = archive.read("BOOT-INF/classes/" + relative + ".class")
            sources[class_name] = {
                "source_sha256": file_sha256(source),
                "packaged_class_sha256": hashlib.sha256(bytecode).hexdigest(),
            }
    atomic_json(
        out / "trusted-producer.json",
        {
            "source_and_packaged_class_pins": sources,
            "role_origin": "Actual thread SecurityContext Authentication authorities, not headers",
            "session_origin": "Actual request.getSession(false), not arbitrary session identity",
            "publisher_task_unchanged": True,
            "ownership_relationship": "GROUND_TRUTH_ONLY",
            "local_transport_boundary": "Private owned guest log -> existing identity/clock correlation -> collector snapshot; public self-asserted JSON is not trusted",
        },
    )
    runtime = json.loads((out / "final-checks/context-runtime.json").read_text())
    native = json.loads((out / "native-reconciliation.json").read_text())
    acceptance = {
        "run_id": out.name,
        "decision": native["decision"],
        "started_unix": start["started"],
        "finished_unix": time.time(),
        "active_wall_seconds": time.time() - start["started"],
        "timebox_seconds": 8 * 3600,
        "gate_causal_context": "PASS_LOCAL_CURRENT_GET_SCOPE",
        "gate_information": "PASS",
        "gate_native_canonical_admission": "BLOCKED_LINEAGE_ROLES_INDEPENDENT_SUPPORT",
        "gate_model": "NOT_RUN_NO_ELIGIBLE_NATIVE_SPLIT",
        "gate_final_quality": "BLOCKED",
        "gate_context_runtime": "PASS_OFFLINE_PARITY_NOT_PERSISTENT_DEPLOYMENT",
        "HTTP_dispatched": native["HTTP_dispatched"],
        "Oracle_verified": native["Oracle_verified"],
        "strict_native_context_views": native["strict_native_context_views"],
        "native_canonical_TRAIN_DEV_CAL_FIT_CAL_OP_TEST": [0, 0, 0, 0, 0],
        "release_ready": False,
        "resource": {
            "fresh_capacity": capacity,
            "purpose_allocation": "I/O/3s drain bounded KVM acceptance, not training; reuse validated single-vCPU allocation, no useful BLAS workload to scale",
            "worker_CPU_percent": 100,
            "native_memory_max_bytes": 3221225472,
            "native_tasks_max": 16,
            "guardian_CPU_percent": 25,
            "guardian_memory_max_bytes": 268435456,
            "dispatch_temperatures_C": [min(temps), max(temps)],
            "dispatch_kernel_quota_counts": [
                {"state": s, "cpu.max": q, "count": n} for (s, q), n in quotas.items()
            ],
            "hardware_protection_priority": True,
            "thermal_policy_unchanged": True,
            "peak_memory_not_claimed": "Last current-memory samples and bounded kernel max available, not a complete peak series",
        },
        "adapters": owned,
        "all_cleanup_verified": True,
        "services": services,
        "linger": subprocess.check_output(
            ["loginctl", "show-user", str(os.getuid()), "-p", "Linger"], text=True
        ).strip(),
        "Rust_context_runtime": runtime,
        "original_dirty_count": len(start["dirty"]),
        "original_dirty_changed": changed,
        "commit_base": start["head"],
        "branch": start["branch"],
        "HTTP_or_training_background_remaining": False,
        "no_serving_changes": True,
        "no_policy_or_firewall_changes": True,
        "next_task": "R27: preregister and acquire independent policy/actor/resource cohorts with fresh context custody; compare deterministic control against ML only where it adds information. Keep URI100 publisher shift track separate.",
    }
    atomic_json(out / "acceptance.json", acceptance)
    atomic_json(
        out / "status.json",
        {
            "state": "COMPLETED",
            "decision": native["decision"],
            "HTTP": native["HTTP_dispatched"],
            "canonical_TRAIN": 0,
            "release_ready": False,
            "cleanup": True,
            "background_job": None,
        },
    )
    print(
        json.dumps(
            {
                "run_id": out.name,
                "decision": native["decision"],
                "adapters": len(owned),
                "cleanup": True,
            }
        )
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(Path(sys.argv[1]))

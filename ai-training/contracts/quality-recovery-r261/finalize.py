"""Readback and package a research candidate; never promote or dispatch HTTP."""

# isort: skip_file

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from common import HERE, PARENT, atomic_json, check, file_sha256, output_arg, read, status
from idps_ai.common import REPO_ROOT


def systemd(unit):
    result = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "-p",
            "Id",
            "-p",
            "MainPID",
            "-p",
            "ActiveState",
            "-p",
            "SubState",
            "-p",
            "Result",
            "-p",
            "NRestarts",
            "-p",
            "ControlGroup",
            "-p",
            "MemoryPeak",
            "-p",
            "CPUUsageNSec",
        ],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def run(out):
    selection = read(out / "model-selection.json")
    lock = read(out / "evaluation-lock.json")
    evaluation = read(out / "evaluation.json")
    verification = read(out / "verification.json")
    native_new = read(out / "native-live-v2/summary.json")
    native_old = read(out / "native-live/summary.json")
    chosen = selection["selected"]
    spec = lock["models"][chosen]
    native_unit = systemd(out.name + "-native-recovery-v2.service")
    check(native_unit["MainPID"] == "0", "Native supervisor is still running")
    check(
        file_sha256(PARENT / "source2-recovery/research_test.npz")
        == lock["source2_RESEARCH_TEST_sha256"],
        "Frozen research cohort SHA changed",
    )
    check(
        file_sha256(out / "bundle" / spec["calibrated_file"]) == spec["calibrated_sha256"],
        "Final candidate digest changed",
    )
    # Record paired differences; these are research diagnostic intervals only.
    with np.load(PARENT / "source2-recovery/research_test.npz", allow_pickle=False) as z:
        y, groups = z["y"], z["group"]
    with np.load(out / "source2-research-scores.npz", allow_pickle=False) as z:
        a, b = z["R26A"] > lock["models"]["R26A"]["cutoff"], z[chosen] > spec["cutoff"]
    rows = []
    for group in np.unique(groups):
        mask = groups == group
        rows.append(
            [
                ((y == 1) & mask).sum(),
                ((y == 0) & mask).sum(),
                ((b.astype(int) - a.astype(int)) * (y == 1) * mask).sum(),
                ((b.astype(int) - a.astype(int)) * (y == 0) * mask).sum(),
            ]
        )
    rows = np.asarray(rows, dtype=np.int64)
    rng = np.random.default_rng(2612)
    boot = rows[rng.integers(len(rows), size=(1000, len(rows)))].sum(axis=1)
    paired = {
        "recall_delta": float(rows[:, 2].sum() / rows[:, 0].sum()),
        "FPR_delta": float(rows[:, 3].sum() / rows[:, 1].sum()),
        "component_bootstrap_95pct_recall_delta": np.quantile(
            boot[:, 2] / np.maximum(1, boot[:, 0]), [0.025, 0.975]
        ).tolist(),
        "scope": "Previously exposed publisher FIT research groups; not native independent acceptance",
    }
    atomic_json(out / "paired-comparison.json", paired)
    preservation = read(out / "preservation.json")
    check(
        all(
            file_sha256(REPO_ROOT / name) == sha
            for name, sha in preservation["dirty_tracked_sha256"].items()
        ),
        "Pre-existing tracked content changed",
    )
    old_index = read(PARENT / "artifact-index.json")["artifacts"]
    for name, expected in old_index.items():
        check(file_sha256(PARENT / name) == expected, "Historical R26 artifact changed: " + name)
    resources = []
    for result_file in sorted(out.rglob("result.json")):
        if result_file.parent.name.startswith("resource-") or result_file.parent.name == "adapter":
            result = read(result_file)
            check(result.get("cleanup_verified") is True, "Owned attempt cleanup missing")
            entry = {"path": str(result_file.parent.relative_to(out)), "result": result}
            preflight = result_file.parent / "preflight.json"
            if preflight.exists():
                proof = read(preflight)
                cgroup = Path("/sys/fs/cgroup") / proof["limits"]["path"].lstrip("/")
                check(not cgroup.exists(), "Owned cgroup still exists")
                entry.update(
                    limits=proof["limits"],
                    temperature_c=proof["temperature_c"],
                    current_cgroup_absent=True,
                    worker=systemd(proof["worker"]),
                    guardian=systemd(proof["guardian"]),
                )
                check(
                    entry["worker"]["MainPID"] == entry["guardian"]["MainPID"] == "0",
                    "Owned process still alive",
                )
            resources.append(entry)
    units = {
        name: systemd(f"idps-r22-local-{name}.service")
        for name in ("ri", "scorer", "collector", "receiver")
    }
    check(
        all(u["ActiveState"] == "active" and u["MainPID"] != "0" for u in units.values()),
        "Local inference no longer healthy",
    )
    bundle = out / "research-bundle"
    bundle.mkdir(exist_ok=True, mode=0o700)
    shutil.copy2(out / "bundle" / spec["calibrated_file"], bundle / "model.onnx")
    shutil.copy2(PARENT / "feature-schema.json", bundle / "feature-schema.json")
    parameters = {
        "version": "idps-r261-research-model-v1",
        "model": "B16_URI100_SWIGLU",
        "parameters": 400256,
        "model_sha256": file_sha256(bundle / "model.onnx"),
        "raw_model_sha256": spec["raw_sha256"],
        "feature_schema_sha256": file_sha256(bundle / "feature-schema.json"),
        "schema": "idps-uri100-raw-ascii-r26-v1",
        "calibration": spec["calibration"],
        "threshold": spec["cutoff"],
        "threshold_float32_le_hex": spec["cutoff_float32_le_hex"],
        "comparator": ">",
        "fit_originals": 433261,
        "fit_unique_uri100": 50230,
        "equal_source_original_Kish": read(out / "diagnosis.json")["diversity"][
            "equal_source_Kish_original"
        ],
        "counts": {
            "FIT": 433261,
            "TUNING": 11082,
            "CAL_FIT": 11354,
            "CAL_OP": 3901,
            "SOURCE2_RESEARCH_TEST": 3750,
        },
        "source2_holdout_independence": "Research subrole of exposed historical R13 FIT, not pristine TEST",
        "best_checkpoint": selection["best_checkpoint"],
        "best_epoch": 16,
        "continuation_completed_epoch": 21,
        "research_only": True,
        "hybrid_allowed": False,
        "release_ready": False,
        "active_default": False,
        "validated_runtime_scope": verification["raw_target_runtime"]["scope_limit"],
        "rollback": "No cutover performed; RI v2 default and existing R20 shadow artifacts/units remain unchanged",
    }
    atomic_json(bundle / "manifest.json", parameters)
    atomic_json(
        out / "resource-acceptance.json",
        {
            "owned_attempts": resources,
            "local_units": units,
            "all_Adapter_cleanup_verified": True,
            "native_supervisor": native_unit,
            "benchmark": read(out / "compute-benchmark.json"),
            "effective_allocation": read(out / "final-allocation.json"),
            "thermal_boundary_fixture": read(out / "thermal-boundary-kernel.json"),
            "host_sensor_start": read(out / "sensor-health.json"),
            "host_sensor_end": read(out / "health-end/sensor-health.json"),
            "host_sensor_after_interruption": read(
                out / "health-after-interruption/sensor-health.json"
            ),
            "interruption_recovery": read(out / "interruption-recovery.json"),
            "hardware_kernel_or_firmware_changes": False,
            "additional_software_temperature_thresholds": False,
        },
    )
    labels = native_new["semantic_label_counts"]
    decision = "QUALITY_IMPROVED_NATIVE_BLOCKED"
    acceptance = {
        "version": "idps-r261-acceptance-v1",
        "run_id": out.name,
        "decision": decision,
        "finished_utc": datetime.now(UTC).isoformat(),
        "branch": "feature/ai-idps-shadow-integration",
        "host_safety": "PASS_OBSERVED_WINDOW_ACPI_RECURRENCE_NOT_CURED",
        "Local_services": units,
        "B16_integrity": "PASS",
        "continuation": "COMPLETED_EARLY_STOP_EPOCH21_BEST16",
        "research_model_selected": chosen,
        "parameters": 400256,
        "dataset": parameters["counts"],
        "quality_metrics": evaluation["models"][chosen],
        "CAL_OP": evaluation["CAL_OP"][chosen],
        "paired_vs_A": paired,
        "external_stress": read(out / "diagnosis.json")["external_benign_stress"],
        "native_live": {
            "first_campaign": native_old["state"],
            "first_HTTP": native_old["capture"]["completed"],
            "repair_campaign": native_new["state"],
            "repair_HTTP": native_new["capture"]["completed"],
            "total_HTTP": native_old["capture"]["completed"] + native_new["capture"]["completed"],
            "semantic_label_counts_repair": labels,
            "task": native_new["semantic_task"],
            "native_TRAIN_DEV_CAL_TEST": [0, 0, 0, 0],
            "URI100_at_cutoff": native_new["URI100_views_at_cutoff"],
            "URI100_mixed_authorization_vectors": native_new["URI100_mixed_task_vectors"],
            "independent_human_review_claimed": False,
        },
        "verification": verification,
        "regression_junit_sha256": file_sha256(out / "final-tests.xml"),
        "cleanup_attempts": len(resources),
        "original_R26_artifact_hashes_preserved": True,
        "original_dirty_tracked_preserved": len(preservation["dirty_tracked_sha256"]),
        "release_ready": False,
        "native_pilot": "BLOCKED_SINGLE_CAMPAIGN_AND_CONTEXT_COLLISION",
        "no_native_or_exposed_TEST_used_to_change_model_or_threshold": True,
        "model_promotion_performed": False,
        "background_job_remaining": False,
        "next_task": "Project trusted authorization/session context before cutoff on the independently witnessed task, collect independent lineage cohorts, and evaluate against URI-only and deterministic policy controls. Do not retrain URI100 blindly.",
    }
    atomic_json(out / "acceptance.json", acceptance)
    index = {}
    for file in out.rglob("*"):
        if (
            file.is_file()
            and not file.is_symlink()
            and file.suffix in {".json", ".xml", ".onnx", ".py", ".log", ".txt"}
            and not any(p in {"fs", "chunks"} for p in file.relative_to(out).parts)
            and file.stat().st_size < 32 * 1024**2
            and file.name not in {"artifact-index.json", "status.json"}
        ):
            index[str(file.relative_to(out))] = file_sha256(file)
    source = {str(file.relative_to(HERE)): file_sha256(file) for file in HERE.glob("*.py")}
    source.update(
        {
            str(file.relative_to(REPO_ROOT)): file_sha256(file)
            for file in (
                REPO_ROOT / "ai-training/src/idps_ai/training/resource_adapter.py",
                REPO_ROOT / "ai-training/src/idps_ai/training/allocation_review.py",
            )
        }
    )
    atomic_json(
        out / "artifact-index.json",
        {"artifacts": index, "source": source, "private_keys_or_raw_payloads_committed": False},
    )
    status(
        out,
        "COMPLETED",
        "FINALIZED",
        decision=decision,
        model_release_ready=False,
        background_job_running=False,
    )
    print(
        json.dumps(
            {
                "decision": decision,
                "model": chosen,
                "native": acceptance["native_live"],
                "cleanup_attempts": len(resources),
            }
        )
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

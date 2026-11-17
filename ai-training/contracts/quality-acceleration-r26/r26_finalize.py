"""Assemble immutable R26 results without starting training, scoring or services."""

# isort: skip_file

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from r26_common import BULK, HERE, atomic_json, check, file_sha256, read, status
from idps_ai.common import REPO_ROOT
from idps_ai.features.request_time import schema as uri76_schema


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
            "NRestarts",
            "-p",
            "Result",
            "-p",
            "ControlGroup",
        ],
        text=True,
        capture_output=True,
        timeout=3,
        check=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def run(out):
    selection, lock = read(out / "model-selection.json"), read(out / "evaluation-lock.json")
    evaluation, verification = read(out / "evaluation.json"), read(out / "verification.json")
    runtime = read(out / "runtime.json")
    for root in (out / "training/model", out / "augmentation-b/training/model"):
        for name in ("best", "latest", "previous"):
            pointer = read(root / f"{name}.json")
            generation = root / pointer["path"]
            check(
                file_sha256(generation / "manifest.json") == pointer["manifest_sha256"],
                "Committed checkpoint pointer digest",
            )
            for filename, expected in read(generation / "manifest.json")["files"].items():
                check(
                    file_sha256(generation / filename) == expected,
                    "Committed checkpoint file digest",
                )
    spec = lock["models"][lock["selected_before_calibration"]]
    check(
        file_sha256(out / "bundle" / spec["calibrated_file"]) == spec["calibrated_sha256"],
        "Final calibrated model digest",
    )
    notes = read(out / "notes/manifest.json")
    recovery = read(out / "source2-recovery/manifest.json")
    metrics = evaluation["RESEARCH_TEST"][evaluation["selected_before_research_test"]]
    attempts = []
    for folder in sorted(out.glob("resource-*")):
        if not (folder / "result.json").exists():
            continue
        result = read(folder / "result.json")
        entry = {"attempt": folder.name, "result": result}
        if (folder / "preflight.json").exists():
            preflight = read(folder / "preflight.json")
            cgroup = Path("/sys/fs/cgroup") / preflight["limits"]["path"].lstrip("/")
            entry.update(
                limits=preflight["limits"],
                admission_temperature_c=preflight["temperature_c"],
                current_cgroup_absent=not cgroup.exists(),
                worker=systemd(preflight["worker"]),
                guardian=systemd(preflight["guardian"]),
            )
            check(not cgroup.exists(), "R26 cgroup remains")
            check(
                all(entry[n]["MainPID"] == "0" for n in ("worker", "guardian")),
                "R26 worker/guardian remains",
            )
        check(result.get("cleanup_verified") is True, "R26 cleanup not verified")
        attempts.append(entry)
    services = {
        name: systemd(f"idps-r22-local-{name}.service")
        for name in ("collector", "receiver", "ri", "scorer")
    }
    resource = {
        "attempts": attempts,
        "local_services": services,
        "hardware_diagnosis": read(out / "host-safety/diagnosis.json"),
        "training_resume_after_terminal_stop": False,
        "all_r26_cleanup_verified": True,
    }
    atomic_json(out / "resource-acceptance.json", resource)
    shape = (
        "available",
        "items",
        "length",
        "max_item_length",
        "first_length",
        "last_length",
        "digit_symbols",
        "upper_symbols",
        "lower_symbols",
        "punctuation",
        "other_symbols",
        "transitions",
    )
    feature_schema = {
        "version": runtime["schema"],
        "tensor": {"input": "input", "width": 100, "dtype": "float32"},
        "columns": uri76_schema()["columns"]
        + [f"{lane}_shape_{name}" for lane in ("path", "query") for name in shape],
        "preprocessing": {
            "base": uri76_schema(),
            "shape": "r23_features.sketch + describe_lane; clip(0,31)/31",
            "python": "r26_runtime.python_uri100",
            "rust": "r26_rust/src/features.rs",
        },
        "validated_scope": "Raw method/origin target and three-round decoded target ASCII only",
        "unsupported": "Explicit ABSTAIN on Unicode, invalid envelope or model unavailability",
        "private_values": "Existing URI76/R23 privacy screens; no literal raw data retained in numeric derivatives",
        "source_masks": "Not inferred from publisher records; no claim of native NSA or cutoff proof",
    }
    check(len(feature_schema["columns"]) == 100, "Final feature ABI width")
    atomic_json(out / "feature-schema.json", feature_schema)
    manifest = {
        "version": "idps-r26-research-candidate-v1",
        "run_id": out.name,
        "candidate": "R26A_SwiGLU_URI100",
        "parameters": 400256,
        "raw_file": "bundle/swiglu.onnx",
        "raw_sha256": selection["sha256"]["swiglu"],
        "calibrated_file": "bundle/" + spec["calibrated_file"],
        "calibrated_sha256": spec["calibrated_sha256"],
        "calibration": spec["calibration"],
        "threshold": spec["cutoff"],
        "threshold_float32_le_hex": spec["cutoff_float32_le_hex"],
        "comparator": ">",
        "feature_schema_sha256": file_sha256(out / "feature-schema.json"),
        "schema": feature_schema["version"],
        "checkpoint": selection["best_checkpoint"],
        "fit_originals": selection["fit_originals"],
        "fit_unique_uri100": verification["union_unique_final_vectors"],
        "kish_equal_source_original_weight": verification[
            "combined_kish_original_equal_source_weight"
        ],
        "publisher_counts": {
            "FIT": 401745,
            "TUNING": 6316,
            "CAL_FIT": 224,
            "CAL_OP": 438,
            "RESEARCH_TEST": 271,
        },
        "native_train_dev_cal_test": [0, 0, 0, 0],
        "native_attack_verified": 0,
        "preprocessing_and_runtime": {
            k: runtime[k] for k in ("binary_sha256", "ort_library_sha256", "scope_limit")
        },
        "release_ready": False,
        "promotion_ready": False,
        "hybrid_allowed": False,
        "default_model_changed": False,
        "RI_v2_R20_artifacts_preserved": True,
        "new_http_shadow": "NOT_RUN_QUALITY_AND_HOST_SAFETY_BLOCKED",
        "rollback": "R26 is a separate offline scorer, never activated; retain existing RI v2 and R20 manifests",
    }
    atomic_json(out / "model-manifest.json", manifest)
    ledger = {
        "WAF": {
            "source": "https://huggingface.co/datasets/puyang2025/waf_data_v2",
            "role": "Existing 400K FIT and 6042 TUNING only",
            "label": "PUBLISHER_NORMAL_ANOMALOUS",
            "publisher_eval_test_heldout_opened": False,
            "raw_sha256": "3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6",
        },
        "NOTES": {
            "source": "https://huggingface.co/datasets/notesbymuneeb/ai-waf-dataset",
            "revision": "1b4d732b3c227fe2345240cbb7e6c30e936ed81b",
            "publisher_license": "MIT",
            "label_task": notes["label_semantics"],
            "sha256": notes["source_sha256"],
            "raw_records": notes["raw_records"],
            "rejected": notes["rejected"],
            "roles": notes["roles"],
            "campaign_independence_proven": False,
            "physical_capture_proven": False,
        },
        "SRBH": {
            "source": "https://doi.org/10.7910/DVN/OGOIXX",
            "label": "PUBLISHER_CAPEC_NORMAL",
            "global_role": "Existing R13 FIT only",
            "historical_protected_payloads_opened": False,
            "recovery_roles": recovery["roles"],
            "raw_sha256": recovery["source_sha256"],
            "holdout_limitation": "Source FIT aggregate transfer previously exposed; new grouped research holdout is not pristine final independent TEST",
            "recovery_training": "INTERRUPTED_GUARDIAN_WATCHDOG_EPOCH16_NO_AUTO_RESUME",
        },
        "CSIC_PKDD": {
            "role": "Existing benign TRAIN stress only, no fitting or threshold selection",
            "evaluation_files_opened": False,
            "new_native_examples": 0,
        },
        "excluded": {
            "MODSEC_LEARN": "No explicit training license in publisher repository metadata",
            "BIBLIOUS17": "Existing restricted access/permission blocker unchanged",
            "WEBREQUESTS_TFIDF": "Global corpus vocabulary and upstream role/license limitations unchanged",
        },
    }
    atomic_json(out / "source-ledger.json", ledger)
    summary = {
        "version": "idps-r26-acceptance-v1",
        "run_id": out.name,
        "finished_utc": datetime.now(UTC).isoformat(),
        "research_training_A": "PASS",
        "recovery_training_B": "BLOCKED_GUARDIAN_WATCHDOG",
        "original_fit": 401745,
        "unique_uri100": 18714,
        "parameters": 400256,
        "fresh_publisher_research_test": metrics,
        "CAL_OP": evaluation["CAL_OP"][evaluation["selected_before_research_test"]],
        "quality_target_90_recall_1_fpr": "BLOCKED",
        "T07_release": "BLOCKED",
        "native_labels_roles": "NO_NEW_NATIVE_TRAIN_DEV_CAL_TEST",
        "python_onnx": {"state": "PASS", "max_abs": selection["numpy_onnx_max_abs"]},
        "raw_rust_python": runtime,
        "exact_epoch_resume": verification["resume"],
        "ETL_rebuild": verification["etl_committed_chunk_rebuild"],
        "regression": {
            "python_tests": 14,
            "state": "PASS",
            "junit_sha256": file_sha256(out / "regression.xml"),
            "final_extra_rust_unit_test": "NOT_RERUN_AFTER_PLATFORM_SENSOR_FAILURE; final raw parity worker already PASS",
        },
        "resource_cleanup": {"attempts": len(attempts), "state": "PASS"},
        "local_service_health": {
            k: {n: v[n] for n in ("ActiveState", "SubState", "MainPID", "NRestarts")}
            for k, v in services.items()
        },
        "runtime_shadow_hybrid": "BLOCKED_NO_NATIVE_COMMON_REQUEST_EVIDENCE_AND_FAILED_HOST_SENSOR",
        "no_http_requests_sent": True,
        "no_original_data_or_serving_code_changed": True,
        "safety_policy_changed": False,
        "background_job_running": False,
        "next_task": "Restore bounded valid ACPI sensor reads and unchanged Local RI/scorer services; review terminal stop before any checkpoint continuation. Then evaluate the committed three-source candidate without reopening R26A research TEST.",
    }
    atomic_json(out / "acceptance.json", summary)
    atomic_json(
        out / "environment.json",
        {
            "python": sys.version,
            "packages": {
                name: version(name)
                for name in ("numpy", "scikit-learn", "onnx", "onnxruntime", "pyarrow", "pytest")
            },
        },
    )
    selected_paths = [
        *out.glob("*.json"),
        *out.glob("*.xml"),
        *out.glob("bundle/*.onnx"),
        *out.glob("notes/*.npz"),
        out / "notes/manifest.json",
        out / "data-v2/waf-manifest.json",
        out / "data-v2/waf-r26.npz",
        *out.glob("source2-recovery/*.json"),
        out / "training/model/best.json",
        out / "training/model/latest.json",
        *out.glob("training/model/checkpoints/*/manifest.json"),
        *out.glob("augmentation-b/training/model/checkpoints/*/manifest.json"),
        *out.glob("host-safety/*"),
        out / "sensor-read-diagnosis.jsonl",
        out / "notes_readme.md",
    ]
    index = {
        str(p.relative_to(out)): file_sha256(p)
        for p in selected_paths
        if p.is_file() and p.name not in {"artifact-index.json", "status.json"}
    }
    code = {
        str(p.relative_to(HERE)): file_sha256(p)
        for p in HERE.rglob("*")
        if p.is_file()
        and (p.suffix in {".py", ".rs", ".toml", ".lock"} or p.name == "uri76-columns.json")
    }
    atomic_json(
        out / "artifact-index.json",
        {
            "artifacts": index,
            "r26_source": code,
            "shared_python_source": {
                str(p.relative_to(REPO_ROOT)): file_sha256(p)
                for p in [
                    *(REPO_ROOT / "ai-training/src/idps_ai").rglob("*.py"),
                    *BULK.glob("r*.py"),
                ]
                if p.is_file()
            },
            "raw_sources": {
                k: v.get("sha256", v.get("raw_sha256"))
                for k, v in ledger.items()
                if isinstance(v, dict)
            },
            "private_identity_keys_committed": False,
        },
    )
    status(
        out,
        "BLOCKED",
        "FINALIZED_RESEARCH_RESULTS",
        quality_release="BLOCKED",
        research_model_complete=True,
        terminal_stop="GUARDIAN_WATCHDOG",
        background_job_running=False,
        report="docs/108_T09_R26_FINAL_AI_QUALITY_ACCELERATION.md",
    )
    print(
        json.dumps(
            {
                "research_model": manifest["candidate"],
                "fit": 401745,
                "release": "BLOCKED",
                "resource_attempts_cleaned": len(attempts),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)

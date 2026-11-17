"""Reconcile the R25 artifacts without opening any new evaluation partition."""

import argparse
import os
import subprocess
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold

from idps_ai.common import atomic_json, file_sha256
from r18_data import check, read
from r19_metrics import metrics_both
from r23_pilot import grouped_scores
from r24_eval import fp_cut, confusion
from r25_probe import SOURCE


def run(out):
    manifest = read(out / "dataset-manifest.json")
    experiment = read(out / "experiment.json")
    selection = read(out / "model-selection.json")
    verification = read(out / "verification.json")
    runtime = read(out / "runtime.json")
    with np.load(out / "publisher-r25-uri132.npz", allow_pickle=False) as d:
        data = {k: d[k] for k in d.files}
    with np.load(SOURCE / "publisher-r24-uri100.npz", allow_pickle=False) as d:
        old = {k: d[k] for k in ("fit_x", "fit_counts", "fit_cell_mass")}
    unique, inverse = np.unique(data["fit_x"][:, :100], axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    counts = np.zeros_like(old["fit_counts"])
    mass = np.zeros_like(old["fit_cell_mass"])
    np.add.at(counts, inverse, data["fit_counts"])
    np.add.at(mass, inverse, data["fit_cell_mass"])
    np.testing.assert_array_equal(unique, old["fit_x"])
    np.testing.assert_array_equal(counts, old["fit_counts"])
    np.testing.assert_allclose(mass, old["fit_cell_mass"], rtol=1e-12, atol=1e-12)
    check(int(counts.sum()) == 400000, "400k original-count reconciliation")
    x, y, groups, context = (data[k] for k in ("tune_x", "tune_y", "tune_groups", "tune_context"))
    fixed, component, budgets, transferred = {}, {}, {}, {}
    folds = list(GroupKFold(5).split(x, y, groups))
    with np.load(out / "tuning-scores.npz", allow_pickle=False) as scores:
        for name in scores.files:
            width = selection["models"][name]["width"]
            values = scores[name]
            c, s = grouped_scores(x[:, :width], y, values)
            cut = selection["thresholds"][name]
            fixed[name] = metrics_both(c, s, cut)
            flags = np.zeros(len(y), np.float32)
            records = experiment["arms"][name]["grouped_threshold_transfer_exposed_tuning"]["0.01"]["folds"]
            for (_, valid), record in zip(folds, records, strict=True):
                flags[valid] = values[valid] > record["cut"]
            fc, fs = grouped_scores(x[:, :width], y, flags)
            rates = metrics_both(fc, fs, 0.5)
            transferred[name] = {
                unit: {k: rates[unit][k] for k in ("recall", "precision", "fpr", "confusion_tn_fp_fn_tp")}
                for unit in ("original_request", "vector_balanced")
            }
            fixed[name]["by_method"] = {
                method: {"support_normal_anomalous": np.bincount(y[context[:, 0] == i], minlength=2).tolist(),
                         **confusion(y[context[:, 0] == i], values[context[:, 0] == i] > cut)}
                for i, method in enumerate(("GET", "POST", "OTHER"))
            }
            included = groups == 2780
            component[name] = {
                "ap": float(average_precision_score(y[included], values[included])),
                "score_min_p50_max_by_label": {
                    str(label): np.percentile(values[included & (y == label)], [0, 50, 100]).tolist()
                    for label in (0, 1)
                },
                "fixed_dual_cut_confusion": confusion(y[included], values[included] > cut),
            }
            budgets[name] = {
                str(n): {"allowed_fp": n, **confusion(y, values > fp_cut(y, values, n))}
                for n in (3, 11, 18, 21, 23)
            }
    resources = {}
    for directory in sorted(out.glob("resource-*")):
        if not (directory / "result.json").exists():
            continue
        result = read(directory / "result.json")
        preflight = read(directory / "preflight.json") if (directory / "preflight.json").exists() else {}
        status = read(directory / "status.json") if (directory / "status.json").exists() else {}
        worker = preflight.get("worker")
        journal = ""
        if worker:
            journal = subprocess.run(["journalctl", "--user", "-u", worker, "--no-pager"], capture_output=True, text=True, check=True).stdout
            (directory / "journal.txt").write_text(journal)
        resources[directory.name] = {
            "result": result,
            "result_sha256": file_sha256(directory / "result.json"),
            "temperature_at_admission_c": preflight.get("temperature_c"),
            "last_temperature_c": status.get("temperature_c"),
            "last_memory_bytes": status.get("memory_bytes"),
            "kernel_limits": preflight.get("limits"),
            "systemd_consumption": [line for line in journal.splitlines() if "Consumed " in line][-1:],
        }
        cgroup = preflight.get("limits", {}).get("path")
        if cgroup:
            absent = not (Path("/sys/fs/cgroup") / cgroup.lstrip("/")).exists()
            resources[directory.name]["kernel_cgroup_absent_now"] = absent
            check(absent, "Owned resource cgroup must be absent after cleanup")
        check(result.get("cleanup_verified"), "Every R25 scope, including failed builds, must clean up")
    required = ("resource-probe", "resource-data", "resource-experiment", "resource-verify", "resource-diagnosis", "resource-rust-build-final", "resource-runtime")
    check(all(resources[k]["result"]["reason"] == "COMPLETED" for k in required), "Required engineering evidence")
    services = {}
    for name in ("scorer", "receiver", "collector", "ri"):
        unit = f"idps-r22-local-{name}.service"
        properties = subprocess.run(["systemctl", "--user", "show", unit, "-p", "ActiveState", "-p", "MainPID"], capture_output=True, text=True, check=True).stdout
        services[unit] = dict(line.split("=", 1) for line in properties.splitlines())
        check(services[unit]["ActiveState"] == "active", "Existing Local service must stay active")
    artifact_names = ("dataset-manifest.json", "training-plan.json", "experiment.json", "model-selection.json", "verification.json", "diagnosis.json", "runtime.json", "swiglu-uri100-r25.onnx")
    result = {
        "task": "T09_R25",
        "run_id": out.name,
        "research_training": "COMPLETED",
        "engineering": "PASS_WITH_RECORDED_BUILD_AND_SUPERVISOR_RECOVERY",
        "quality_objective_90pct_recall_at_1pct_fpr": "BLOCKED",
        "final_model": False,
        "release_ready": False,
        "promotion": "REJECTED_GENERALIZATION_REGRESSION",
        "serving": "KEEP_RI_V2_AND_R20_SHADOW",
        "fit_originals": 400000,
        "fit_classes_normal_anomalous": counts.sum(axis=0).tolist(),
        "fit_uri100_vectors": len(old["fit_x"]),
        "fit_uri132_vectors": len(data["fit_x"]),
        "exact_parent_counts_and_loss_mass": "PASS",
        "new_canonical_train_admissions": 0,
        "native_train_dev": [0, 0],
        "native_acceptance": "PENDING_REVIEWED_TWO_CLASS_CAL_TEST",
        "fresh_independent_dual_class_source": "NOT_AVAILABLE_WITHIN_ALLOWED_ROLES",
        "tuning_fixed_dual_cut": fixed,
        "transferred_tuning_operating_rates": transferred,
        "matched_maximum_fp_budgets_tuning_diagnostic": budgets,
        "dominant_component_2780_scores": component,
        "resource_scopes": resources,
        "services": services,
        "logout_persistence_linger": subprocess.run(["loginctl", "show-user", "trung", "-p", "Linger"], capture_output=True, text=True, check=True).stdout.strip(),
        "background_job": "COMPLETED_NO_IDLE_WORKLOAD",
        "protected_roles_read": False,
        "http_requests_sent": 0,
        "sha256": {name: file_sha256(out / name) for name in artifact_names},
    }
    atomic_json(out / "acceptance.json", result)
    spec = selection["models"]["WARM_SWIGLU_URI100"]
    atomic_json(out / "model-manifest.json", {
        "version": "idps-r25-uri100-research-v1",
        "model": "WARM_SWIGLU_URI100",
        "parameters": 400256,
        "scope": "WAF_PUBLISHER_NORMAL_ANOMALOUS_DEVELOPMENT",
        "label_provenance": "publisher normal/anomalous; never ATTACK_VERIFIED",
        "model_sha256": spec["sha256"],
        "schema": runtime["schema"],
        "input_shape": [None, 100],
        "dtype": "float32",
        "preprocessing": "URI76 unchanged, then 24 bounded R23 structure counts divided by 31",
        "checkpoint": spec["checkpoint"],
        "dataset_sha256": read(SOURCE / "dataset-manifest.json")["data_sha256"],
        "comparison_dataset_sha256": manifest["dataset_sha256"],
        "calibration": "NONE_FOR_R25; independent CAL_FIT/CAL_OP pending",
        "development_cutoff_strict_greater": selection["thresholds"]["WARM_SWIGLU_URI100"],
        "research_only": True,
        "hybrid_allowed": False,
        "release_ready": False,
        "raw_target_rust_preprocessing": "PENDING",
        "onnx_tensor_rust_parity": runtime["state"],
    })


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)

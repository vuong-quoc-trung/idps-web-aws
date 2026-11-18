# isort: skip_file

"""Lock all research models and CAL thresholds before opening source2 holdout."""

import os

import numpy as np
from scipy.stats import beta

from common import PARENT, atomic_json, check, file_sha256, output_arg, read
from calibration import calibrate, role
from idps_ai.export.onnx import cpu_session
from r26_evaluate import profile_metrics
from r26_common import R25, R25_ONNX_SHA
from r21_quality import R20, R20_ONNX


def intervals(frame, scores, cutoff):
    predictions = scores > cutoff
    truth = frame["y"]
    groups = np.unique(frame["group"])
    rng = np.random.default_rng(2611)
    parts = []
    for group in groups:
        mask = frame["group"] == group
        y, pred = truth[mask], predictions[mask]
        parts.append(
            [
                np.count_nonzero((y == 0) & ~pred),
                np.count_nonzero((y == 0) & pred),
                np.count_nonzero((y == 1) & ~pred),
                np.count_nonzero((y == 1) & pred),
            ]
        )
    parts = np.asarray(parts)
    samples = parts[rng.integers(len(groups), size=(1000, len(groups)))].sum(axis=1)
    metrics = {
        "recall": samples[:, 3] / np.maximum(1, samples[:, 2] + samples[:, 3]),
        "fpr": samples[:, 1] / np.maximum(1, samples[:, 0] + samples[:, 1]),
        "precision": samples[:, 3] / np.maximum(1, samples[:, 3] + samples[:, 1]),
    }
    n = int(np.count_nonzero(truth == 0))
    fp = int(np.count_nonzero((truth == 0) & predictions))
    return {
        "research_component_bootstrap_95pct": {
            key: np.quantile(value, [0.025, 0.975]).tolist() for key, value in metrics.items()
        },
        "independence_limitation": "Previously exposed publisher FIT source; template closure groups are not independently verified native campaigns",
        "unadjusted_request_binomial_FPR_upper_95pct_diagnostic_only": float(
            beta.ppf(0.95, fp + 1, n - fp)
        )
        if fp < n
        else 1.0,
        "formal_T07_native_confidence": False,
    }


def run(out):
    check(not (out / "evaluation.json").exists(), "Evaluation already sealed")
    selection = read(out / "model-selection.json")
    models = [
        ("R20", R20 / "bundle/swiglu.onnx", R20_ONNX, 76),
        ("R25", R25 / "swiglu-uri100-r25.onnx", R25_ONNX_SHA, 100),
        (
            "R26A",
            PARENT / "bundle/swiglu.onnx",
            read(PARENT / "model-selection.json")["sha256"]["swiglu"],
            100,
        ),
        ("B16", out / "bundle/b16.onnx", selection["sha256"]["B16"], 100),
        ("B_FINAL", out / "bundle/b-final.onnx", selection["sha256"]["B_FINAL"], 100),
        ("LOGISTIC", out / "bundle/logistic.onnx", selection["sha256"]["LOGISTIC"], 100),
    ]
    specs, calibration = calibrate(models, out / "bundle")
    lock = {
        "selected_from_TUNING": selection["selected"],
        "model_selection_sha256": file_sha256(out / "model-selection.json"),
        "models": specs,
        "protocol_sha256": file_sha256(out / "protocol.json"),
        "metric_code_sha256": file_sha256(__file__),
        "calibration_code_sha256": file_sha256(
            __import__("pathlib").Path(__file__).with_name("calibration.py")
        ),
        "calibration": "Equal source mass, preserve within-source label prevalence, positive-slope Platt CAL_FIT, global maximum dual source CAL_OP FPR<=0.5%, strict >",
        "source2_RESEARCH_TEST_sha256": read(PARENT / "source2-recovery/manifest.json")["roles"][
            "RESEARCH_TEST"
        ]["sha256"],
        "old_NOTES_TEST_opened": False,
        "source2_global_role": "HISTORICAL_R13_FIT_RESEARCH_ONLY_NOT_PRISTINE_TEST",
        "native_release_allowed": False,
    }
    atomic_json(out / "evaluation-lock.json", lock)
    # This read happens only after immutable model/threshold choices are committed.
    frame = role("source2-recovery", "RESEARCH_TEST")
    metrics, archives = {}, {}
    for name, spec in specs.items():
        graph = out / "bundle" / spec["calibrated_file"]
        check(file_sha256(graph) == spec["calibrated_sha256"], "Frozen graph digest")
        scores = cpu_session(graph, 1).run(["score"], {"input": frame["x"][:, : spec["width"]]})[0]
        archives[name] = scores
        metrics[name] = profile_metrics(frame, scores, spec["width"], spec["cutoff"])
        metrics[name]["confidence"] = intervals(frame, scores, spec["cutoff"])
    np.savez_compressed(out / "source2-research-scores.npz", **archives)
    selected = metrics[selection["selected"]]["original_request"]
    atomic_json(
        out / "evaluation.json",
        {
            "models": metrics,
            "CAL_OP": calibration,
            "selected_before_scoring": selection["selected"],
            "target_point_estimate_met_on_this_research_cohort": selected["recall"] >= 0.9
            and selected["fpr"] <= 0.01,
            "evaluation_lock_sha256": file_sha256(out / "evaluation-lock.json"),
            "native_TEST": "MISSING",
            "native_release_ready": False,
            "old_NOTES_TEST_not_reopened": True,
            "no_post_test_model_or_threshold_adjustment": True,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

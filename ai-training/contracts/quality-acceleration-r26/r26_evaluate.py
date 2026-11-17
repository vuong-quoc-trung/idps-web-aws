"""Fit new-source CAL_FIT, freeze CAL_OP, then open the research holdout once."""

# isort: skip_file

import argparse
import os
import struct
from pathlib import Path

import numpy as np
import onnx
from scipy.stats import beta

from r26_common import R25, R25_ONNX_SHA, SEED, atomic_json, check, file_sha256, read
from idps_ai.export.onnx import cpu_session
from r19_metrics import metrics_both
from r20_calibration import fit, threshold
from r26_calibration import append_sigmoid
from r21_quality import R20, R20_ONNX
from r23_pilot import grouped_scores
from r26_train import export


def role(out, name, manifest):
    path = out / "notes" / f"{name.lower()}.npz"
    check(file_sha256(path) == manifest["roles"][name]["sha256"], "Calibration/research role pin")
    with np.load(path, allow_pickle=False) as z:
        return {name: z[name] for name in z.files}


def profile_metrics(frame, scores, width, cut):
    counts, values = grouped_scores(frame["x"][:, :width], frame["y"], scores)
    report = metrics_both(counts, values, cut)
    from idps_ai.features.request_time import schema

    columns = schema()["columns"]
    get = frame["x"][:, columns.index("method_GET")] == 1
    post = frame["x"][:, columns.index("method_POST")] == 1
    from r24_eval import confusion

    report["by_method"] = {
        name: {
            "normal_anomalous": np.bincount(frame["y"][selected], minlength=2).tolist(),
            **confusion(frame["y"][selected], scores[selected] > cut),
        }
        for name, selected in (("GET", get), ("POST", post), ("OTHER", ~(get | post)))
    }
    report["support"] = {
        "records": len(frame["y"]),
        "closure_groups": len(np.unique(frame["group"])),
        "normal_anomalous": np.bincount(frame["y"], minlength=2).tolist(),
        "score_coverage": 1.0,
    }
    anchors = []
    for group in np.unique(frame["group"]):
        candidates = np.flatnonzero((frame["group"] == group) & (frame["y"] == 0))
        if len(candidates):
            # Salted index roster is locked independently of all model outputs.
            import hashlib

            anchor = min(
                candidates,
                key=lambda i: hashlib.sha256(
                    f"{SEED}:{int(frame['coordinate'][i])}".encode()
                ).digest(),
            )
            anchors.append(anchor)
    mistakes = int(np.count_nonzero(scores[anchors] > cut))
    upper = (
        1.0
        if mistakes == len(anchors)
        else float(beta.ppf(0.95, mistakes + 1, len(anchors) - mistakes))
    )
    report["benign_template_anchor_diagnostic"] = {
        "anchors": len(anchors),
        "false_alerts": mistakes,
        "one_sided_95pct_binomial_upper": upper,
        "formal_T07_native_bound": False,
        "limitation": "Synthetic template clusters are not independently verified native exposure campaigns",
    }
    return report


def run(out):
    check(
        not (out / "evaluation.json").exists(),
        "Research evaluation already committed; do not rescore for selection",
    )
    selection = read(out / "model-selection.json")
    manifest = read(out / "notes/manifest.json")
    width = selection["width"]
    models = {
        "R20": (R20 / "bundle/swiglu.onnx", R20_ONNX, 76),
        "R25": (R25 / "swiglu-uri100-r25.onnx", R25_ONNX_SHA, 100),
        "R26_SWIGLU": (out / "bundle/swiglu.onnx", selection["sha256"]["swiglu"], width),
        "R26_LOGISTIC": (out / "bundle/logistic.onnx", selection["sha256"]["logistic"], width),
    }
    fit_frame = role(out, "CAL_FIT", manifest)
    op_frame = role(out, "CAL_OP", manifest)
    lock = {
        "selected_before_calibration": f"R26_{selection['selected'].upper()}",
        "selection_sha256": file_sha256(out / "model-selection.json"),
        "cal_fit_sha256": manifest["roles"]["CAL_FIT"]["sha256"],
        "cal_op_sha256": manifest["roles"]["CAL_OP"]["sha256"],
        "research_test_sha256": manifest["roles"]["RESEARCH_TEST"]["sha256"],
        "metric_code_sha256": file_sha256(__file__),
        "calibration_wrapper_sha256": file_sha256(Path(__file__).with_name("r26_calibration.py")),
        "calibration": "Fixed positive-slope Platt sigmoid on CAL_FIT only, per arm; no method/config search",
        "comparator": "strict > float32 threshold",
        "operating_point": "One global threshold per arm, max(request and vector CAL_OP cutoff at FPR <=0.5%); no TEST threshold selection",
        "research_scope": "Synthetic publisher labels; no native or production certification",
        "promotion_conditions": "T07 independent native roles, adjusted confidence, coverage, all required strata and quality gates",
        "models": {},
    }
    sessions, calibration_reports = {}, {}
    for name, (path, expected, inputs) in models.items():
        check(file_sha256(path) == expected, "Frozen raw model binding")
        session = cpu_session(path, 1)
        raw = session.run(["score"], {"input": fit_frame["x"][:, :inputs]})[0]
        counts, values = grouped_scores(fit_frame["x"][:, :inputs], fit_frame["y"], raw)
        calibration = fit("platt", values, counts)
        graph = append_sigmoid(calibration, onnx.load(path))
        dest = out / "bundle" / f"{name.lower()}-calibrated.onnx"
        export(dest, graph)
        deployed = cpu_session(dest, 1)
        op_scores = deployed.run(["score"], {"input": op_frame["x"][:, :inputs]})[0]
        oc, oscores = grouped_scores(op_frame["x"][:, :inputs], op_frame["y"], op_scores)
        cut = max(threshold(oc, oscores, target=0.005), threshold(oc, oscores, True, target=0.005))
        lock["models"][name] = {
            "raw_sha256": expected,
            "width": inputs,
            "calibration": calibration,
            "calibrated_file": dest.name,
            "calibrated_sha256": file_sha256(dest),
            "cutoff": cut,
            "cutoff_float32_le_hex": struct.pack("<f", cut).hex(),
        }
        sessions[name] = deployed
        calibration_reports[name] = profile_metrics(op_frame, op_scores, inputs, cut)
    atomic_json(out / "evaluation-lock.json", lock)
    # No model/config/threshold selection is allowed beyond this point.
    test_frame = role(out, "RESEARCH_TEST", manifest)
    output = {}
    score_archive = {}
    for name, session in sessions.items():
        spec = lock["models"][name]
        scores = session.run(["score"], {"input": test_frame["x"][:, : spec["width"]]})[0]
        score_archive[name] = scores
        output[name] = profile_metrics(test_frame, scores, spec["width"], spec["cutoff"])
    np.savez_compressed(out / "research-test-scores.npz", **score_archive)
    selected = lock["selected_before_calibration"]
    result = output[selected]["original_request"]
    atomic_json(
        out / "evaluation.json",
        {
            "selected_before_research_test": selected,
            "evaluation_lock_sha256": file_sha256(out / "evaluation-lock.json"),
            "CAL_OP": calibration_reports,
            "RESEARCH_TEST": output,
            "target_point_estimate_met": result["recall"] >= 0.9 and result["fpr"] <= 0.01,
            "native_acceptance": "BLOCKED_NO_REVIEWED_NATIVE_TWO_CLASS_COHORT",
            "final_release_ready": False,
            "source_independence": "New publisher/source revision, coarse/template-disjoint groups; synthetic generator/campaign independence unverified",
            "publisher_eval_test_or_old_locked_payloads_read": False,
            "RI_V2": "NOT_SCORED_NO_COMMON_207_FEATURE_NATIVE_OBSERVATION",
            "RULE_ONLY_HYBRID": "NOT_COMPARED_NO_COMMON_REQUEST_BOUND_RULE_ORACLE_CUTOFF_EVIDENCE",
            "protected_historical_roles": "UNCHANGED",
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    run(p.parse_args().out)

"""Two frozen benign lab campaigns for provisional GLU207 calibration and FPR study.

Reuses the existing AI-owned three-source collector. The calibration cohort and
threshold are sealed before any evaluation request is sent. No model is changed.
"""

import argparse
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from scipy.stats import beta

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json

AI_ROOT = Path(__file__).resolve().parents[1]
CAL_ROOT = AI_ROOT / ".artifacts/bc27_1104"
EVAL_ROOT = AI_ROOT / ".artifacts/be27_1104"
THRESHOLD = CAL_ROOT / "threshold-manifest.json"
_SPEC = importlib.util.spec_from_file_location(
    "idps_ai_prospective_benign", Path(__file__).with_name("prospective-benign-glu207.py")
)
if _SPEC is None or _SPEC.loader is None:
    raise PipelineError("Prospective lab collector is unavailable")
_BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BASE)
_BASE_PLAN_DATA = _BASE.plan_data


def manifest(role):
    if role not in ("calibration", "evaluation"):
        raise PipelineError("Unknown campaign role")
    items = [
        {"offset": 0, "kind": "csrf", "path": "/api/auth/csrf"},
        {"offset": 2, "kind": "login", "path": "/api/auth/login"},
        {"offset": 4, "kind": "csrf", "path": "/api/auth/csrf"},
        {"offset": 6, "kind": "me", "path": "/api/auth/me"},
    ]
    routes = ("majors", "training-programs", "faculties", "classes")
    if role == "evaluation":
        routes = ("classes", "faculties", "training-programs", "majors")
    create_at = 5 if role == "calibration" else 14
    words = (
        ("C# basics", "50% progress", "a+b", "học phần")
        if role == "calibration"
        else ("Python 3", "75% complete", "x&y", "lớp học")
    )
    for index in range(23):
        kind = (
            "create" if index == create_at else "created_get" if index == create_at + 1 else "page"
        )
        if kind == "create":
            path = "/api/faculties"
        elif kind == "created_get":
            path = "/api/faculties/{created_id}"
        else:
            query = {
                "page": str((3 if role == "calibration" else 7) + index % 3),
                "size": str((3 if role == "calibration" else 11) + index % 7),
            }
            if index in (3, 11, 17, 21):
                query["q"] = words[(3, 11, 17, 21).index(index)]
            path = "/api/" + routes[index % 4] + "?" + urlencode(query)
        items.append({"offset": 20 + index * 20, "kind": kind, "path": path})
    return items


def configure_base(role):
    original = _BASE_PLAN_DATA

    def plan_data():
        plan = original()
        plan["campaign_id"] = f"benign-{role}-20261104-01"
        plan["purpose"] = (
            "provisional_benign_calibration_no_quality_claim"
            if role == "calibration"
            else "prospective_benign_fpr_with_frozen_provisional_threshold"
        )
        plan["request_manifest"] = manifest(role)
        plan["orchestrator_sha256"] = file_sha256(__file__)
        plan["collector_sha256"] = file_sha256(_BASE.__file__)
        plan["role"] = role
        plan["threshold_selection_algorithm"] = (
            "For 27 oracle-verified benign scores, take the maximum float32 score "
            "and the next greater representable float32 value; alert iff score >= threshold. "
            "This yields zero in-sample alerts by construction and no 1% guarantee."
            if role == "calibration"
            else "No selection: apply frozen threshold-manifest exactly."
        )
        if role == "evaluation":
            if not THRESHOLD.exists():
                raise PipelineError("A frozen threshold manifest is required before evaluation")
            threshold = load_json(THRESHOLD)
            if threshold.get("status") != "PROVISIONAL_BENIGN_ONLY":
                raise PipelineError("Threshold status mismatch")
            plan["threshold_manifest_sha256"] = file_sha256(THRESHOLD)
            plan["threshold"] = threshold["threshold"]
            plan["fpr_budget"] = 0.01
        return plan

    _BASE.plan_data = plan_data


def validate_cohort(root):
    plan = load_json(root / "plan.json")
    report = load_json(root / "report.json")
    if (
        report["plan_sha256"] != file_sha256(root / "plan.json")
        or report["physical_requests"] != 27
        or report["three_source"] != 27
        or report["benign_verified_lab"] != 27
        or report["unknown"] != 0
        or report["scored"] != 27
        or report["unique_feature_views"] != 27
        or not report["onnx_native_parity_all"]
        or plan["orchestrator_sha256"] != file_sha256(__file__)
        or plan["collector_sha256"] != file_sha256(_BASE.__file__)
    ):
        raise PipelineError("Prospective cohort evidence gate failed")
    scores = np.asarray([r["score"] for r in report["per_request_private"]], np.float32)
    if (
        len(scores) != 27
        or [r["index"] for r in report["per_request_private"]] != list(range(27))
        or not np.isfinite(scores).all()
    ):
        raise PipelineError("Invalid frozen model scores")
    return plan, report, scores


def calibrate():
    plan, report, scores = validate_cohort(CAL_ROOT)
    if plan["role"] != "calibration":
        raise PipelineError("Wrong calibration plan")
    maximum = np.max(scores)
    threshold = float(np.nextafter(maximum, np.float32(np.inf)))
    if not np.isfinite(threshold) or np.any(scores >= threshold):
        raise PipelineError("Provisional threshold calculation failed")
    manifest_data = {
        "format_version": 1,
        "status": "PROVISIONAL_BENIGN_ONLY",
        "model_checkpoint_manifest_sha256": plan["checkpoint_manifest_sha256"],
        "onnx_sha256": plan["onnx_sha256"],
        "feature_spec_sha256": plan["feature_spec_sha256"],
        "calibration_plan_sha256": file_sha256(CAL_ROOT / "plan.json"),
        "calibration_report_sha256": file_sha256(CAL_ROOT / "report.json"),
        "calibration_campaign_id": plan["campaign_id"],
        "calibration_benign_lab": report["benign_verified_lab"],
        "calibration_unique_views": report["unique_feature_views"],
        "calibration_max_score": float(maximum),
        "algorithm": plan["threshold_selection_algorithm"],
        "score_direction": "higher_is_more_attack_like; alert_if_score_greater_or_equal",
        "threshold": threshold,
        "in_sample_false_positives_by_construction": 0,
        "fpr_budget": 0.01,
        "statistical_limit": "27 correlated benign requests from one lab cannot certify 1% FPR or attack recall; threshold is research-only.",
        "automatic_blocking": False,
        "formal_admitted": 0,
    }
    if THRESHOLD.exists():
        raise PipelineError("Refusing to overwrite a frozen threshold")
    atomic_json(THRESHOLD, manifest_data)
    print(json.dumps({"threshold": threshold, "threshold_sha256": file_sha256(THRESHOLD)}))


def exact_binomial_interval(x, n, confidence=0.95):
    if n == 0:
        return None
    alpha = 1 - confidence
    low = 0.0 if x == 0 else float(beta.ppf(alpha / 2, x, n - x + 1))
    high = 1.0 if x == n else float(beta.ppf(1 - alpha / 2, x + 1, n - x))
    return [low, high]


def evaluate():
    plan, report, scores = validate_cohort(EVAL_ROOT)
    if plan["role"] != "evaluation":
        raise PipelineError("Wrong evaluation plan")
    frozen = load_json(THRESHOLD)
    if plan["threshold_manifest_sha256"] != file_sha256(THRESHOLD):
        raise PipelineError("Frozen threshold was changed after evaluation plan")
    if (
        frozen["model_checkpoint_manifest_sha256"] != plan["checkpoint_manifest_sha256"]
        or frozen["onnx_sha256"] != plan["onnx_sha256"]
        or frozen["feature_spec_sha256"] != plan["feature_spec_sha256"]
        or frozen["threshold"] != plan["threshold"]
        or file_sha256(CAL_ROOT / "report.json") != frozen["calibration_report_sha256"]
    ):
        raise PipelineError("Threshold/model/calibration provenance mismatch")
    decisions = scores >= np.float32(frozen["threshold"])
    rows = report["per_request_private"]
    calibration_rows = load_json(CAL_ROOT / "report.json")["per_request_private"]
    exact_view_overlap = len(
        {r["view_sha256"] for r in rows}.intersection({r["view_sha256"] for r in calibration_rows})
    )
    if any(r["ground_truth_tier"] != "BENIGN_VERIFIED_LAB_WORKFLOW" for r in rows):
        raise PipelineError("Cannot compute FPR on unverified requests")
    groups = {}
    for name, indices in {
        "EARLY": [i for i, r in enumerate(rows) if r["phase"] == "EARLY"],
        "WARMING": [i for i, r in enumerate(rows) if r["phase"] == "WARMING"],
        "WARM": [i for i, r in enumerate(rows) if r["phase"] == "WARM"],
    }.items():
        count = len(indices)
        fp = int(np.sum(decisions[indices]))
        groups[name] = {
            "benign": count,
            "false_positives": fp,
            "observed_fpr": fp / count if count else None,
            "binomial_95_ci": exact_binomial_interval(fp, count),
            "prior_flow": sum(rows[i]["prior_flow"] for i in indices),
        }
    workflows = {}
    observer = load_json(EVAL_ROOT / "observer.json")
    for kind in sorted({r["kind"] for r in observer["requests"]}):
        indices = [i for i, r in enumerate(observer["requests"]) if r["kind"] == kind]
        workflows[kind] = {
            "benign": len(indices),
            "false_positives": int(np.sum(decisions[indices])),
        }
    fp = int(np.sum(decisions))
    result = {
        "status": "PROSPECTIVE_LAB_FPR_ESTIMATED_PROVISIONAL_THRESHOLD",
        "evaluation_plan_sha256": file_sha256(EVAL_ROOT / "plan.json"),
        "evaluation_capture_report_sha256": file_sha256(EVAL_ROOT / "report.json"),
        "calibration_plan_sha256": frozen["calibration_plan_sha256"],
        "calibration_report_sha256": frozen["calibration_report_sha256"],
        "threshold_manifest_sha256": file_sha256(THRESHOLD),
        "threshold": frozen["threshold"],
        "calibration_benign": frozen["calibration_benign_lab"],
        "calibration_campaigns": 1,
        "evaluation_benign": len(rows),
        "evaluation_campaigns": 1,
        "evaluation_unique_views": report["unique_feature_views"],
        "calibration_evaluation_exact_feature_view_overlap": exact_view_overlap,
        "physical_request_ids_disjoint": len(
            {r["request_id"] for r in observer["requests"]}.intersection(
                {r["request_id"] for r in load_json(CAL_ROOT / "observer.json")["requests"]}
            )
        )
        == 0,
        "false_positives": fp,
        "observed_fpr": fp / len(rows),
        "false_positives_per_10000": fp / len(rows) * 10000,
        "binomial_95_ci": exact_binomial_interval(fp, len(rows)),
        "binomial_ci_limit": "Descriptive exact-binomial interval assumes independent requests; one session/lab violates that assumption, so population FPR is not certified.",
        "by_phase": groups,
        "by_workflow": workflows,
        "unique_view_false_positives": fp,
        "unique_view_fpr": fp / report["unique_feature_views"],
        "score_min": float(np.min(scores)),
        "score_median": float(np.median(scores)),
        "score_p95": float(np.percentile(scores, 95)),
        "score_max": float(np.max(scores)),
        "prior_flow": report["prior_flow"],
        "onnx_forward_ms_p95": report["onnx_forward_ms_p95"],
        "attack_recall": None,
        "formal_admitted": 0,
        "production_ready": False,
        "same_environment_as_calibration": True,
        "threshold_changed_after_evaluation": False,
        "automatic_blocking": False,
    }
    if not result["physical_request_ids_disjoint"]:
        raise PipelineError("Calibration/evaluation request IDs overlap")
    atomic_json(EVAL_ROOT / "fpr-report.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "threshold",
                    "evaluation_benign",
                    "false_positives",
                    "observed_fpr",
                    "binomial_95_ci",
                    "by_phase",
                )
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "prepare-calibration",
            "run-calibration",
            "freeze-threshold",
            "prepare-evaluation",
            "run-evaluation",
            "evaluate",
        ),
    )
    args = parser.parse_args()
    if args.command.endswith("calibration") or args.command == "freeze-threshold":
        configure_base("calibration")
        root = CAL_ROOT
    else:
        configure_base("evaluation")
        root = EVAL_ROOT
    if args.command.startswith("prepare-"):
        _BASE.prepare(root)
    elif args.command.startswith("run-"):
        _BASE.run(root)
    elif args.command == "freeze-threshold":
        calibrate()
    else:
        evaluate()


if __name__ == "__main__":
    main()

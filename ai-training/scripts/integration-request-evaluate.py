#!/usr/bin/env python3
"""One candidate decision: WAF calibration/development plus exposed regression.

All thresholds freeze on role1 before role2 or DVWA scoring. No training occurs.
"""

import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.training.checkpoint import load_checkpoint

ART = AI_ROOT / ".artifacts"
WAF = ART / "request_intelligence_v2_20261104"
BASE_THRESHOLD = 0.8826237916946411


def score(net, x):
    return np.concatenate([net.predict(x[i : i + 256])[0] for i in range(0, len(x), 256)])


def metrics(labels, scores, threshold):
    flag = scores > threshold
    pos = labels == 1
    neg = labels == 0
    return {
        "publisher_anomalous": int(pos.sum()),
        "publisher_NORMAL": int(neg.sum()),
        "TP": int((flag & pos).sum()),
        "FN": int((~flag & pos).sum()),
        "FP": int((flag & neg).sum()),
        "TN": int((~flag & neg).sum()),
        "publisher_positive_fraction_flagged": float(flag[pos].mean()),
        "publisher_normal_fraction_flagged": float(flag[neg].mean()),
        "publisher_PR_AUC": float(average_precision_score(labels, scores)),
        "scope": "publisher labels, not independent Ground Truth",
    }


def evaluate(study, run, output):
    study, run, output = map(lambda p: Path(p).resolve(), [study, run, output])
    output.mkdir(mode=0o700, exist_ok=False)
    plan = load_json(study / "plan.json")
    candidate = load_checkpoint(run)
    if (
        candidate.model.steps != plan["updates"]
        or candidate.state["plan_sha256"] != plan["plan_sha256"]
    ):
        raise PipelineError("Candidate not final for frozen training plan")
    if file_sha256(WAF / "waf-rich-v2/rich-content.npz") != plan["dataset_original_sha256"]:
        raise PipelineError("Curated corpus changed")
    baseline = load_checkpoint(WAF / "run/model")
    if (
        file_sha256(baseline.path / "manifest.json")
        != "acdc0a2c9bff24fa0e4720dfcdd97e4a315e39fc625cf603e06eecc5c07a92fc"
    ):
        raise PipelineError("Frozen reference changed")
    with np.load(WAF / "waf-rich-v2/rich-content.npz", allow_pickle=False) as data:
        role = data["role"]
        y = data["label"]
        x = np.concatenate((data["numeric"], data["content"]), axis=1)
    start = time.monotonic()
    with threadpool_limits(limits=1):
        cal = (role == 1) & (y == 0)
        cal_scores = score(candidate.model, x[cal])
        threshold = float(np.quantile(cal_scores, 0.99, method="higher"))
        threshold_manifest = {
            "scope": "WAF role1 publisher-NORMAL p99 higher; strict greater than",
            "threshold": threshold,
            "normal_views": int(cal.sum()),
            "normal_flagged": int(np.sum(cal_scores > threshold)),
            "plan_sha256": plan["plan_sha256"],
            "checkpoint_sha256": file_sha256(candidate.path / "manifest.json"),
            "evaluation_scores_used": False,
            "created_at_unix": time.time(),
        }
        threshold_manifest["manifest_sha256"] = digest(threshold_manifest)
        atomic_json(output / "threshold.json", threshold_manifest)
        val = role == 2
        cand_scores = score(candidate.model, x[val])
        base_scores = score(baseline.model, x[val])
        development = {
            "candidate": metrics(y[val], cand_scores, threshold),
            "frozen_reference": metrics(y[val], base_scores, BASE_THRESHOLD),
        }
        train = np.load(study / "train.npy", mmap_mode="r", allow_pickle=False)
        labels = np.load(study / "labels.npy", allow_pickle=False)
        probe = np.random.default_rng(8201).choice(len(train), 2048, replace=False)
        fitting = {
            "candidate": metrics(labels[probe], score(candidate.model, train[probe]), threshold),
            "scope": "2048 fixed train diagnostic; not quality acceptance",
        }
        spec = importlib.util.spec_from_file_location(
            "p0_eval", AI_ROOT / "scripts/p0-request-evaluate.py"
        )
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        _, _, records = old.corpus(ART / "p0_dvwa_20261105_1520/capture-final")
        from idps_ai.mvp_inference import ResearchMVP

        encoder = ResearchMVP("request-v2", cpus=1)
        vectors = np.asarray([old.vector(encoder, r["http_request"])[0] for r in records])
        dvwa_scores = score(candidate.model, vectors)
        rows = [
            {
                "case_id": r["record_id"],
                "family": r["family"],
                "lab_intent": r["lab_intent"],
                "score": float(s),
                "flagged": bool(s > threshold),
                "status": "EXPOSED_REGRESSION_ONLY",
            }
            for r, s in zip(records, dvwa_scores, strict=True)
        ]
        dvwa = {
            "candidate": old.confusion(rows),
            "candidate_by_family": {
                f: old.confusion([r for r in rows if r["family"] == f])
                for f in sorted({r["family"] for r in rows})
            },
            "frozen_reference": load_json(
                ART / "p0_dvwa_20261105_1520/evaluation/evaluation-report.json"
            )["variants"]["full"]["lab_confusion"],
            "scope": "exposed DVWA, lab labels/review pending, no fitting or threshold selection",
        }
    b = development["frozen_reference"]
    c = development["candidate"]
    criteria = {
        "development_normal_budget": c["publisher_normal_fraction_flagged"]
        <= b["publisher_normal_fraction_flagged"] + 0.002,
        "development_positive_noninferiority": c["publisher_positive_fraction_flagged"]
        >= b["publisher_positive_fraction_flagged"] - 0.01,
        "DVWA_additional_attempts_ge4": dvwa["candidate"]["TP"]
        >= dvwa["frozen_reference"]["TP"] + 4,
        "DVWA_no_additional_benign_flags": dvwa["candidate"]["FP"]
        <= dvwa["frozen_reference"]["FP"],
    }
    chosen = "NUMERIC_MASK_CANDIDATE" if all(criteria.values()) else "FROZEN_REQUEST_V2"
    result = {
        "status": "COMPLETED_SINGLE_CANDIDATE_STUDY",
        "selection": chosen,
        "selection_checks": criteria,
        "selection_rule_precommitted": plan["selection"],
        "training_plan_sha256": plan["plan_sha256"],
        "candidate_checkpoint": str(candidate.path),
        "candidate_checkpoint_sha256": file_sha256(candidate.path / "manifest.json"),
        "candidate_threshold": threshold,
        "frozen_reference_threshold": BASE_THRESHOLD,
        "threshold_file_sha256": file_sha256(output / "threshold.json"),
        "development": development,
        "training_diagnostic": fitting,
        "DVWA_exposed_regression": dvwa,
        "new_independent_evaluation": False,
        "new_physical_requests": 0,
        "training_updates_in_evaluation": 0,
        "wall_seconds": time.monotonic() - start,
        "limitations": [
            "WAF weak publisher labels; near duplicates and source dependence remain",
            "DVWA used for exposed regression selection, never a blind generalization claim",
            "single seed bounded experiment; no production champion",
            "Neither full GLU contract nor GLU training performed",
        ],
    }
    result["report_sha256"] = digest(result)
    atomic_json(output / "evaluation-report.json", result)
    atomic_json(output / "dvwa-predictions.json", rows)
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    evaluate(a.study, a.run, a.output)

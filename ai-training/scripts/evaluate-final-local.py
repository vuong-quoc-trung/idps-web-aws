#!/usr/bin/env python3
"""Locked final publisher evaluation; one CAL fit before EVAL scoring, no updates."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.student_training import protected_near
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.deep import forward
from idps_ai.training.partial import partial_loss
from idps_ai.training.publisher_evaluation import fit_balanced_threshold, group_metrics, metrics

REPO = Path(__file__).resolve().parents[2]
FINAL = (
    REPO
    / "ai-training/.artifacts/final_local_training_20261110/final-local-publisher-200k-20261110-r1"
)
OLD = (
    REPO
    / "ai-training/.artifacts/student_publisher_pilot_20261110/student-publisher-anomaly-20261110-r1"
)
SOURCE = REPO / "ai-training/.artifacts/local_release_20261110/local-release200k-20261110-r1"
ORIGINAL = REPO / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"


def load(p):
    return json.loads(Path(p).read_text())


def model_fingerprint(m):
    return digest({k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in m.arrays().items()})


def checked_model(run, steps, n):
    p = load(run / "plan.json")
    c = dict(p)
    assert c.pop("fingerprint") == digest(c)
    for path, sha in p["code_hashes"].items():
        assert file_sha256(REPO / path) == sha
    for name, sha in p["data_files"].items():
        assert file_sha256(run / "data" / name) == sha
    done = load(run / "training-completion.json")
    ck = load_checkpoint(run / "model")
    assert not ck.used_previous and ck.model.steps == done["optimizer_updates"] == steps
    assert file_sha256(ck.path / "manifest.json") == done["checkpoint_manifest_sha256"]
    assert ck.model.layer_dims == [588, 64, 64, 64, 64, 8]
    assert sum(a.size for a in ck.model.parameters.values()) == 50696
    assert ck.state["epoch"] == 10 and ck.state["cursor"] == n
    assert ck.state["scheduler"] == {"kind": "constant", "learning_rate": 0.001, "step": steps}
    assert ck.state["plan_fingerprint"] == p["fingerprint"] == done["plan_fingerprint"]
    assert ck.state["dataset_fingerprint"] == p["dataset_fingerprint"]
    assert ck.state["split_fingerprint"] == p["split_fingerprint"]
    losses = ck.state["losses"]
    assert len(losses) == steps and sum(v["batch_rows"] for v in losses) == n * 10
    assert all(np.isfinite(v["loss"]) for v in losses)
    for a in ck.model.arrays().values():
        assert np.isfinite(a).all()
        a.setflags(write=False)
    return p, ck, model_fingerprint(ck.model)


def role(run, name):
    with np.load(run / "data" / (name.lower() + ".npz"), allow_pickle=False) as z:
        return {k: z[k].copy() for k in z.files}


def metadata(root):
    db = sqlite3.connect(f"file:{root}/materialized/index.sqlite?mode=ro", uri=True)
    result = {}
    for i, rj, mj in db.execute(
        "SELECT r.i,r.j,student.j FROM r JOIN student USING(i) JOIN accepted USING(i)"
    ):
        n, m = json.loads(rj), json.loads(mj)
        result[i] = {
            "view": n["view_key"],
            "raw": n["representation_key"],
            "groups": n["groups"],
            "method": n["method"],
            "body": m["body_observation"],
            "window": str(int(n["source_row"] >= 1048576)),
            "origin": "OLD_FRAME" if i < 100000 else "NEW_FRAME",
            "target": m["target"],
        }
    db.close()
    return result


def common_holdout_proof(new_cal, new_eval, old_train, meta, oldmeta):
    evidence = {}
    old_rows = [oldmeta[int(i)] for i in old_train["rows"]]
    keys = {
        k: {g for m in old_rows for g in m["groups"]} if k == "groups" else {m[k] for m in old_rows}
        for k in ["groups", "raw", "view"]
    }
    for name, d in [("CALIBRATION", new_cal), ("EVALUATION", new_eval)]:
        rows = [meta[int(i)] for i in d["rows"]]
        counts = {
            k: sum(bool(set(m[k]) & keys[k]) if k == "groups" else m[k] in keys[k] for m in rows)
            for k in keys
        }
        hits = 0
        for a in range(0, len(d["x"]), 64):
            hits += int(protected_near(d["x"][a : a + 64, 76:], old_train["x"][:, 76:]).sum())
        evidence[name] = {
            "raw_overlap": counts["raw"],
            "view_overlap": counts["view"],
            "template_overlap": counts["groups"],
            "content_near_overlap": hits,
        }
    return {
        "eligible_common_internal_holdout": not any(
            v for d in evidence.values() for v in d.values()
        ),
        "checks": evidence,
        "scope": "known request-representation/template/view/content-near relations only; physical/campaign/time independence unverified",
    }


def score(model, data):
    _, probabilities, cache = forward(model, data["x"])
    scores = (1 - probabilities[:, 0]).astype(np.float32)
    loss = partial_loss(
        cache[-1][1],
        data["y"],
        np.where(data["y"] == 0, 0, -1),
        model.objective["smoothing"],
        0.0,
        model.objective["binary_class_weights"],
    )[0]
    return scores, float(loss)


def probability_diagnostics(y, s):
    # Fixed bins, descriptive only. No recalibration or operating-point selection.
    bins = np.minimum((np.asarray(s) * 10).astype(int), 9)
    ece = 0.0
    for b in range(10):
        ix = bins == b
        if np.any(ix):
            ece += np.mean(ix) * abs(float(np.mean(s[ix]) - np.mean(y[ix])))
    return {
        "Brier": float(np.mean((s - y) ** 2)),
        "ECE_10_fixed_width_bins": float(ece),
        "scope": "posthoc descriptive publisher-score diagnostics; not a calibrated attack probability",
    }


def evaluate(output):
    assert not output.exists(), "Immutable new evaluation directory required"
    plan, final, fsha = checked_model(FINAL, 2490, 15890)
    oldplan, previous, osha = checked_model(OLD, 420, 2667)
    validation = load(FINAL / "validation.json")
    c = dict(validation)
    assert c.pop("fingerprint") == digest(c) and validation["state"] == "PASS"
    assert validation["dataset_fingerprint"] == plan["dataset_fingerprint"]
    assert validation["split_fingerprint"] == plan["split_fingerprint"]
    assert load(FINAL / "terminal.json")["state"] == "COMPLETED"
    assert load(FINAL / "attempts/train-01/thermal-report.json")["state"] == "COMPLETED"
    meta, oldmeta = metadata(SOURCE), metadata(ORIGINAL)
    assert file_sha256(SOURCE / "identity.key") == file_sha256(ORIGINAL / "identity.key")
    train, cal, ev = role(FINAL, "TRAIN"), role(FINAL, "CALIBRATION"), role(FINAL, "EVALUATION")
    assert not set(train["groups"]) & set(cal["groups"]) and not set(train["groups"]) & set(
        ev["groups"]
    )
    proof = common_holdout_proof(cal, ev, role(OLD, "TRAIN"), meta, oldmeta)
    output.mkdir(parents=True, mode=0o700)
    models = {"final": final.model}
    if proof["eligible_common_internal_holdout"]:
        models["previous_common_holdout_reference"] = previous.model

    def baseline(data):
        result = {
            "majority_prior": np.full(len(data["y"]), plan["majority_baseline"]["anomaly_prior"])
        }
        for k in ["window", "body"]:
            bins = plan["shortcut_baselines_TRAIN_only"][k]
            result["metadata_" + k] = np.array(
                [
                    bins[v][1] / sum(bins[v])
                    if (v := meta[int(i)][k]) in bins
                    else plan["majority_baseline"]["anomaly_prior"]
                    for i in data["rows"]
                ]
            )
        return result

    cal_scores, train_scores, losses = baseline(cal), baseline(train), {}
    for name, model in models.items():
        cal_scores[name], loss = score(model, cal)
        losses.setdefault(name, {})["CALIBRATION"] = loss
        train_scores[name], loss = score(model, train)
        losses[name]["TRAIN"] = loss
    thresholds = {name: fit_balanced_threshold(cal["y"], s) for name, s in cal_scores.items()}
    oldthreshold = load(OLD / "evaluation-v1/thresholds.json")["models"]["candidate"]["threshold"]
    atomic_json(
        output / "thresholds.json",
        {
            "models": thresholds,
            "fixed": 0.5,
            "comparator": ">",
            "source": "CALIBRATION_ONLY",
            "EVAL_labels_used": False,
            "previous_original_threshold": oldthreshold,
            "common_holdout_proof": proof,
        },
    )
    thresholdsha = file_sha256(output / "thresholds.json")
    eval_scores = baseline(ev)
    for name, model in models.items():
        eval_scores[name], loss = score(model, ev)
        losses[name]["EVALUATION"] = loss
    allmetrics, grouped, calibration = {}, {}, {}
    for name, d, scores in [
        ("TRAIN", train, train_scores),
        ("CALIBRATION", cal, cal_scores),
        ("EVALUATION", ev, eval_scores),
    ]:
        allmetrics[name], grouped[name], calibration[name] = {}, {}, {}
        for model, s in scores.items():
            points = {"fixed0.5": 0.5, "CAL_balanced": thresholds[model]["threshold"]}
            if model == "previous_common_holdout_reference":
                points["previous_original_operating_point"] = oldthreshold
            allmetrics[name][model] = {point: metrics(d["y"], s, t) for point, t in points.items()}
            grouped[name][model] = {
                point: group_metrics(d["y"], s, t, d["groups"]) for point, t in points.items()
            }
            calibration[name][model] = probability_diagnostics(d["y"], s)
    strata = {}
    for field in ["method", "body", "window", "origin"]:
        values = np.array([meta[int(i)][field] for i in ev["rows"]])
        strata[field] = {}
        for v in sorted(set(values)):
            ix = np.flatnonzero(values == v)
            strata[field][v] = {
                name: metrics(ev["y"][ix], s[ix], thresholds[name]["threshold"])
                for name, s in eval_scores.items()
                if name in models
            }
    primary = allmetrics["EVALUATION"]["final"]["CAL_balanced"]
    best_control_ap = max(
        allmetrics["EVALUATION"][m]["CAL_balanced"]["average_precision"]
        for m in ["majority_prior", "metadata_body", "metadata_window"]
    )
    acceptance = (
        primary["average_precision"] >= best_control_ap + 0.05
        and primary["balanced_accuracy"] >= 0.75
    )
    split = load(FINAL / "data/split.json")
    slot = {
        meta[v["row"]]["view"]: i
        for i, v in enumerate([v for v in split if v["role"] == "EVALUATION"])
    }
    views = {meta[v["row"]]["view"] for v in split if v["role"] == "EVALUATION"}
    aliases = [slot[m["view"]] for m in meta.values() if m["view"] in views]
    retained = metrics(
        ev["y"][aliases], eval_scores["final"][aliases], thresholds["final"]["threshold"]
    )
    assert thresholdsha == file_sha256(output / "thresholds.json")
    assert fsha == model_fingerprint(final.model) and osha == model_fingerprint(previous.model)
    report = {
        "release": "AI-IDPS-Local-v1.0-rc1",
        "evaluation": "COMPLETED",
        "run_id": FINAL.name,
        "checkpoint": str(final.path.relative_to(REPO)),
        "manifest_sha256": file_sha256(final.path / "manifest.json"),
        "dataset_fingerprint": plan["dataset_fingerprint"],
        "split_fingerprint": plan["split_fingerprint"],
        "training_updates": 2490,
        "parameters": 50696,
        "training_examples": 15890,
        "training_loss_final_batch": final.state["losses"][-1]["loss"],
        "full_objective_losses": losses,
        "common_holdout_comparison": proof,
        "previous_historical_metrics": load(OLD / "evaluation-v1/metrics.json")["metrics"][
            "EVALUATION"
        ]["candidate"],
        "thresholds": thresholds,
        "threshold_sha256": thresholdsha,
        "metrics": allmetrics,
        "group_metrics": grouped,
        "probability_diagnostics": calibration,
        "subgroups": strata,
        "retained_record_sensitivity": retained,
        "research_acceptance": {
            "state": "PASS" if acceptance else "FAIL",
            "required_AP_margin": 0.05,
            "required_balanced_accuracy": 0.75,
            "best_control_AP": best_control_ap,
            "actual_AP_margin": primary["average_precision"] - best_control_ap,
            "promotion": False,
        },
        "data_accounting": load(SOURCE / "release-accounting.json"),
        "source_exclusions": load(SOURCE / "materialized/summary.json")[
            "quarantine_reasons_overlapping"
        ],
        "limitations": [
            "SILVER publisher anomaly, not independently verified attack intent",
            "same exposed publisher source; physical/campaign/time lineage PARTIAL",
            "known-overlap checks do not establish independent cross-domain generalization",
            "Wilson intervals are nominal iid and exclude label noise/group selection",
            "family labels unavailable; no SQLi/XSS/command recall claim",
            "paired previous-model reference is authorized posttraining, not model selection",
            "publisher live contract UNSUPPORTED selected-headers/no-body projection; OFFLINE_ONLY",
        ],
        "no_optimizer_updates": True,
        "sealed_access": False,
    }
    report["fingerprint"] = digest(report)
    atomic_json(output / "evaluation.json", report)
    np.savez(output / "scores-private.npz", **eval_scores)
    print(
        json.dumps(
            {
                "evaluation": "COMPLETED",
                "research_acceptance": report["research_acceptance"],
                "primary": primary,
                "common_holdout": proof,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    with threadpool_limits(limits=1):
        evaluate(args.output.resolve())

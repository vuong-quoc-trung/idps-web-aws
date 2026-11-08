#!/usr/bin/env python3
"""One locked final-checkpoint comparison on exposed CAL/DEV, no model selection."""

import argparse
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, digest, file_sha256
from idps_ai.data.attack_intent import vector_hash
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.generalization import calibration_audit

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def binomial_interval(k, n):
    if not n:
        return None
    return [
        float(beta.ppf(0.025, k, n - k + 1)) if k else 0.0,
        float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0,
    ]


def metrics(y, s, t, weights=None):
    y = np.asarray(y)
    s = np.asarray(s)
    flag = s > t
    tp, fn, fp, tn = [
        int(v.sum()) for v in [flag & (y == 1), ~flag & (y == 1), flag & (y == 0), ~flag & (y == 0)]
    ]
    result = {
        "rows": len(y),
        "benign": tn + fp,
        "attack": tp + fn,
        "threshold": float(t),
        "comparator": ">",
        "TP": tp,
        "FN": fn,
        "FP": fp,
        "TN": tn,
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "average_precision": float(average_precision_score(y, s, sample_weight=weights))
        if len(set(y)) == 2
        else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "FPR": fp / (tn + fp) if tn + fp else None,
        "iid_binomial_95pct": {
            "recall": binomial_interval(tp, tp + fn),
            "FPR": binomial_interval(fp, fp + tn),
            "precision": binomial_interval(tp, tp + fp),
        },
    }
    if weights is not None:
        w = np.asarray(weights, np.float64)
        result["weighted"] = {
            name: float(w[num].sum() / w[den].sum()) if w[den].sum() else None
            for name, num, den in [
                ("recall", flag & (y == 1), y == 1),
                ("FPR", flag & (y == 0), y == 0),
                ("precision", flag & (y == 1), flag),
            ]
        }
    return result


def retention(y, families, flags):
    y = np.asarray(y)
    families = np.asarray(families)
    c = flags["challenger"]
    refs = [flags["frozen"], flags["calibration_only"]]
    family_counts = {
        f: [int(np.sum(p & (families == f) & (y == 1))) for p in [*refs, c]]
        for f in ["xss", "cmd_injection", "sqli", "path_traversal"]
    }
    checks = {
        "XSS_gain_at_least2": family_counts["xss"][2] - max(family_counts["xss"][:2]) >= 2,
        "command_gain_at_least2": family_counts["cmd_injection"][2]
        - max(family_counts["cmd_injection"][:2])
        >= 2,
        "no_new_benign_ID_vs_either_reference": all(not np.any(c & ~r & (y == 0)) for r in refs),
        "no_SQLi_TP_count_loss": family_counts["sqli"][2] >= max(family_counts["sqli"][:2]),
        "no_file_TP_count_loss": family_counts["path_traversal"][2]
        >= max(family_counts["path_traversal"][:2]),
    }
    return {
        "checks": checks,
        "family_detected_frozen_control_candidate": family_counts,
        "decision": "CASE_A_PROMISING_RESEARCH_CHALLENGER"
        if all(checks.values())
        else "CASE_B_NO_DEMONSTRATED_IMPROVEMENT",
    }


def selected(data, rows, canonical):
    ix = np.flatnonzero(data["eligible"] & data["paired_common_eligible"])
    seen = set()
    out = []
    for i in sorted(ix, key=lambda i: str(data["ids"][i])):
        assert rows[i]["eligible_for_research"] and rows[i]["intent"] in {
            "BENIGN_INTENT",
            "ATTACK_INTENT",
        }
        key = vector_hash(data["x"][i])
        if not canonical or key not in seen:
            out.append(int(i))
            seen.add(key)
    return np.array(out, np.int64)


def near_components(rows, runtime, x):
    pairs = module("materialize-request-v3").near_pairs(rows, runtime, x[:, 588:], use_body=True)
    roots = list(range(len(rows)))

    def root(i):
        while roots[i] != i:
            roots[i] = roots[roots[i]]
            i = roots[i]
        return i

    for a, b in pairs:
        roots[root(a)] = root(b)
    groups = [root(i) for i in range(len(rows))]
    counts = Counter(groups)
    return np.array([1 / counts[g] for g in groups]), len(counts), len(pairs)


def evaluate(run, output):
    assert not output.exists()
    completion = load(run / "completion.json")
    assert completion["status"] == "COMPLETED" and completion["steps"] == 60
    assert load(run / "supervisor-result.json")["status"] == "COMPLETED"
    assert load(run / "resource/resource-report.json")["status"] == "PASS"
    plan = load(run / "plan.json")
    assert plan["fingerprint"] == digest({k: v for k, v in plan.items() if k != "fingerprint"})
    assert file_sha256(__file__) == plan["evaluator_sha256"]
    cfg = load(ROOT / "ai-training/configs/research/request-v3-grounded-pilot-20261108.json")
    assert (
        cfg["fingerprint"] == plan["design_fingerprint"]
        and cfg["dataset_fingerprint"] == plan["dataset_fingerprint"]
    )
    release = ROOT / cfg["dataset_release"]
    manifest = load(release / "dataset-release.json")
    assert file_sha256(release / "dataset-release.json") == cfg["dataset_release_manifest_sha256"]
    for p, sha in manifest["files_sha256"].items():
        assert file_sha256(release / p) == sha
    candidate = load_checkpoint(run / "model")
    assert not candidate.used_previous and candidate.model.steps == 60
    assert file_sha256(candidate.path / "manifest.json") == completion["manifest_sha256"]
    frozen = ResearchMVP("request-v2", cpus=1)
    assert frozen.v2_manifest_sha == plan["frozen_manifest_sha256"]
    ledger = [json.loads(s) for s in (release / "records.jsonl").read_text().splitlines()]
    data = {}
    rows = {}
    masks = {}
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        with np.load(release / (role.lower() + ".npz"), allow_pickle=False) as z:
            data[role] = {k: z[k].copy() for k in z.files}
        rows[role] = [r for r in ledger if r["original_role"] == role]
        assert [r["sample_id"] for r in rows[role]] == list(data[role]["ids"])
        masks[role] = selected(data[role], rows[role], True)
    assert len(masks["CALIBRATION"]) == 13 and len(masks["DEVELOPMENT"]) == 90
    scores = {
        r: {
            "frozen": frozen.v2_model.predict(d["frozen_runtime"])[0],
            "challenger": candidate.model.predict(d["x"])[0],
        }
        for r, d in data.items()
    }
    for s in scores.values():
        s["calibration_only"] = s["frozen"]
    cal = masks["CALIBRATION"]
    ben = cal[data["CALIBRATION"]["binary_y"][cal] == 0]
    assert len(ben) == 11
    thresholds = {
        "frozen": frozen.v2_threshold,
        "calibration_only": float(scores["CALIBRATION"]["frozen"][ben].max()),
        "challenger": float(scores["CALIBRATION"]["challenger"][ben].max()),
    }
    # Persist threshold selection before inspecting any DEV metrics.
    output.mkdir(mode=0o700, parents=True)
    stability = {}
    for name, t in thresholds.items():
        s = scores["CALIBRATION"][name][ben]
        loo = [float(np.delete(s, i).max()) for i in range(len(s))]
        stability[name] = {
            "CAL_benign_count": 11,
            "threshold": t,
            "benign_score_min_max": [float(s.min()), float(s.max())],
            "leave_one_benign_out_max_range": [min(loo), max(loo)],
            "largest_vs_second_gap": float(np.sort(s)[-1] - np.sort(s)[-2]),
            "threshold_chosen_from_DEV": False,
            "leave_one_out_refits_not_used": True,
        }
    atomic_json(
        output / "thresholds.json",
        {
            "thresholds": thresholds,
            "strict_comparator": ">",
            "selected_from": "Canonical eligible CAL benign only; frozen deployed unchanged",
            "stability": stability,
            "model_selection": "Final60step checkpoint only",
        },
    )
    reports = {}
    for role in data:
        ix = masks[role]
        d = data[role]
        rr = rows[role]
        yy = d["binary_y"][ix]
        subrows = [rr[i] for i in ix]
        roots = module("materialize-request-v3").lineage_roots(rr)
        groups = np.array([roots[int(i)] for i in ix])
        group_sizes = Counter(groups)
        weights = np.array([1 / group_sizes[g] for g in groups])
        near_weights, near_groups, near_pairs = near_components(
            subrows, d["frozen_runtime"][ix], d["x"][ix]
        )
        views = {}
        for name, t in thresholds.items():
            s = scores[role][name][ix]
            p = s > t
            strata = {}
            for dimension, fn in [
                ("family", lambda r: r["family"]),
                ("method", lambda r: r["method"]),
                ("environment", lambda r: r["environment"]),
                (
                    "benign_media",
                    lambda r: (
                        (
                            "JSON"
                            if r["body_syntax_vector"][12]
                            else "FORM"
                            if r["body_syntax_vector"][11]
                            else "OTHER"
                        )
                        if r["intent"] == "BENIGN_INTENT"
                        else None
                    ),
                ),
                ("workflow", lambda r: r["workflow_group"]),
            ]:
                keys = [fn(r) for r in subrows]
                strata[dimension] = {}
                for key in sorted({k for k in keys if k is not None}):
                    j = np.array([i for i, k in enumerate(keys) if k == key])
                    strata[dimension][key] = metrics(yy[j], s[j], t)
            j = np.array(
                [
                    i
                    for i, r in enumerate(subrows)
                    if r["intent"] == "BENIGN_INTENT" and r["method"] == "POST"
                ],
                np.int64,
            )
            allix = selected(d, rr, False)
            views[name] = {
                "canonical": metrics(yy, s, t),
                "receipt_weighted_sensitivity": metrics(
                    d["binary_y"][allix], scores[role][name][allix], t
                ),
                "strata": strata,
                "benign_POST": metrics(yy[j], s[j], t) if len(j) else None,
                "lineage_equal_weight_sensitivity": metrics(yy, s, t, weights),
                "near_component_equal_weight_sensitivity": metrics(yy, s, t, near_weights),
                "lineage_component_confusions": [
                    {"group_ordinal": n, "metrics": metrics(yy[groups == g], s[groups == g], t)}
                    for n, g in enumerate(sorted(set(groups)))
                ],
                "probability_calibration_diagnostic": calibration_audit(yy, s),
            }
        reports[role] = {
            "canonical_rows": len(ix),
            "recorded_lineage_components": len(set(groups)),
            "cluster_interval": None
            if len(set(groups)) < 8
            else "NOT_ESTIMATED_IN_THIS_TINY_PILOT",
            "near_components": near_groups,
            "near_pairs": near_pairs,
            "arms": views,
        }
    ix = masks["DEVELOPMENT"]
    yy = data["DEVELOPMENT"]["binary_y"][ix]
    rr = [rows["DEVELOPMENT"][i] for i in ix]
    families = np.array([r["family"] for r in rr])
    flags = {k: scores["DEVELOPMENT"][k][ix] > t for k, t in thresholds.items()}
    decision = retention(yy, families, flags)
    paired = {}
    for ref in ["frozen", "calibration_only"]:
        c = flags["challenger"]
        b = flags[ref]
        paired[ref] = {
            "corrected_attack": int(np.sum(c & ~b & (yy == 1))),
            "lost_attack": int(np.sum(~c & b & (yy == 1))),
            "new_benign_FP": int(np.sum(c & ~b & (yy == 0))),
            "removed_benign_FP": int(np.sum(~c & b & (yy == 0))),
            "family_changes": {
                f: {
                    "corrected": int(np.sum(c & ~b & (families == f) & (yy == 1))),
                    "lost": int(np.sum(~c & b & (families == f) & (yy == 1))),
                }
                for f in ["xss", "cmd_injection", "sqli", "path_traversal"]
            },
        }
    # Posthoc inference-only sensitivity, not a trained matched control or retention arm.
    ablated = data["DEVELOPMENT"]["x"][ix].copy()
    ablated[:, 603:] = 0
    abscore = candidate.model.predict(ablated)[0]
    full = scores["DEVELOPMENT"]["challenger"][ix]
    syntax_sensitivity = {
        "scope": "Posthoc zero syntax-count/flag tail, state/media retained; possible off-manifold input, no threshold refit or quality claim",
        "mean_abs_score_change": float(np.mean(np.abs(full - abscore))),
        "threshold_crossings": int(
            np.sum((abscore > thresholds["challenger"]) != flags["challenger"])
        ),
        "by_family": {
            f: float(np.mean(np.abs(full[families == f] - abscore[families == f])))
            for f in sorted(set(families))
        },
    }
    final = {
        "run_id": run.name,
        "dataset_fingerprint": cfg["dataset_fingerprint"],
        "design_fingerprint": cfg["fingerprint"],
        "evaluator_sha256": file_sha256(__file__),
        "checkpoint_manifest_sha256": completion["manifest_sha256"],
        "thresholds": thresholds,
        "roles": reports,
        "retention": decision,
        "paired_DEV_changes": paired,
        "syntax_tail_sensitivity": syntax_sensitivity,
        "calibration_stability": stability,
        "RULE_AI_COMPLEMENTARITY": "NOT_MEASURED",
        "rule_reason": "Frozen derivative has no bound per-record Rule/Suricata alert evidence; no matching inferred",
        "uncertainty": "Exact binomial intervals shown as IID sensitivity only. DEV has4 recorded lineage components; independent-cluster CI unsupported. Conditional exposed lab evidence, not population guarantees.",
        "representation_attribution": "Weights and representation both changed. No matched588-input finetune was precommitted, so three-arm comparison cannot causally isolate46features.",
        "training_selection": "One final60step checkpoint, one run, no DEV threshold/checkpoint selection; inference diagnostics do not modify acceptance",
        "independent_human_review": "PENDING",
        "INDEPENDENT_QUALITY_CERTIFIED": False,
        "promotion": False,
        "sealed_access": False,
    }
    atomic_json(output / "evaluation.json", final)
    # Per-record scores/labels stay private. Public reporting uses aggregates only.
    np.savez(
        output / "scores-private.npz",
        **{r + "_" + k: v for r, s in scores.items() for k, v in s.items()},
    )
    atomic_json(
        output / "paired-private.json",
        [
            {
                "sample_id": r["sample_id"],
                "intent": r["intent"],
                "family": r["family"],
                "flags": {k: bool(flags[k][i]) for k in flags},
            }
            for i, r in enumerate(rr)
        ],
    )
    print(
        json.dumps(
            {
                "decision": decision,
                "DEV": {k: v["canonical"] for k, v in reports["DEVELOPMENT"]["arms"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        evaluate(a.run.resolve(), a.output.resolve())

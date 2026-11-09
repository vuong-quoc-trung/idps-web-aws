#!/usr/bin/env python3
"""Four fixed arms, final adapter only; exposed DEV/body, no selection/promotion."""

import argparse
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, file_sha256
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.frozen_body_adapter import load_adapter

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(p):
    return json.loads(Path(p).read_text())


def evaluate(run, output):
    assert not output.exists()
    t = module("frozen-backbone-request-v3")
    ev = module("evaluate-request-v3-pilot")
    p, f, _, cfg, xtrain, ytrain, groups = t.validate(run)
    assert (
        load(run / "completion.json")["status"] == "COMPLETED"
        and load(run / "supervisor-result.json")["status"] == "COMPLETED"
    )
    assert load(run / "resource/resource-report.json")["status"] == "PASS"
    ck = load_adapter(run / "model", f.model, p["fingerprint"])
    a = ck.model
    assert (
        a.steps == 60
        and not ck.used_previous
        and load(run / "completion.json")["manifest_sha256"]
        == file_sha256(ck.path / "manifest.json")
    )
    assert a.backbone_hashes == p["backbone_parameter_hashes"]
    a.assert_frozen()
    full = load_checkpoint(ROOT / p["full_v3_checkpoint"]["checkpoint"])
    assert (
        full.model.steps == 60
        and file_sha256(full.path / "manifest.json") == p["full_v3_checkpoint"]["manifest_sha256"]
    )
    assert (
        file_sha256(t.REFERENCE / "evaluation/thresholds.json") == p["reference_thresholds_sha256"]
    )
    data = {}
    rows = {}
    masks = {}
    release = ROOT / p["dataset_release"]
    ledger = [json.loads(s) for s in (release / "records.jsonl").read_text().splitlines()]
    for role in ["TRAIN", "CALIBRATION", "DEVELOPMENT"]:
        with np.load(release / (role.lower() + ".npz"), allow_pickle=False) as z:
            data[role] = {k: z[k].copy() for k in z.files}
        rows[role] = [r for r in ledger if r["original_role"] == role]
        assert [r["sample_id"] for r in rows[role]] == list(data[role]["ids"])
        masks[role] = ev.selected(data[role], rows[role], True)
    # Exposed body cohort is separately pinned; never TRAIN/CAL.
    assert file_sha256(t.BODY / "eligible-manifest.json") == p["body_cohort_manifest_sha256"]
    bm = load(t.BODY / "eligible-manifest.json")
    assert (
        file_sha256(t.BODY / "eligible-records.json") == bm["records_sha256"]
        and file_sha256(t.BODY / "features-private.npz") == bm["features_sha256"]
    )
    bodyrows = load(t.BODY / "eligible-records.json")
    assert all(r["role"] == "EVALUATION_ONLY" for r in bodyrows)
    with np.load(t.BODY / "features-private.npz", allow_pickle=False) as z:
        data["BODY_EXPOSED"] = {
            "x": z["x"].copy(),
            "frozen_runtime": z["frozen"].copy(),
            "binary_y": np.array([int(r["intent"] == "ATTACK_INTENT") for r in bodyrows]),
            "ids": z["ids"].copy(),
        }
    rows["BODY_EXPOSED"] = bodyrows
    masks["BODY_EXPOSED"] = np.arange(8)
    scores = {}
    parity = {}
    for role, d in data.items():
        base = f.model.predict(d["frozen_runtime"])[0]
        normal = a.predict(d["x"])[0]
        off = a.predict(d["x"], disable=True)[0]
        zero = np.all(d["x"][:, 603:] == 0, axis=1)
        assert off.tobytes() == base.tobytes(), "Disabled adapter not baseline exact"
        assert normal[zero].tobytes() == base[zero].tobytes(), (
            "Zero selected contribution score regression"
        )
        original = p["reference_thresholds"]["frozen"]
        assert np.array_equal(normal[zero] > original, base[zero] > original)
        getzero = np.array([r["method"] == "GET" for r in rows[role]]) & zero
        parity[role] = {
            "all_rows": len(base),
            "zero_selected_rows": int(zero.sum()),
            "legacy_GET_zero_rows": int(getzero.sum()),
            "zero_score_byte_exact": True,
            "adapter_disabled_all_rows_byte_exact": True,
            "fixed_original_threshold_flag_parity": True,
            "max_abs_zero_score_delta": float(np.max(np.abs(normal[zero] - base[zero])))
            if zero.any()
            else 0.0,
        }
        scores[role] = {
            "frozen": base,
            "calibration_only": base,
            "full_v3": full.model.predict(d["x"])[0],
            "adapter": normal,
            "adapter_disabled": off,
            "counts_only": a.predict(d["x"], feature_mode="counts_only")[0],
            "syntax_only": a.predict(d["x"], feature_mode="syntax_only")[0],
        }
    cal = masks["CALIBRATION"]
    ben = cal[data["CALIBRATION"]["binary_y"][cal] == 0]
    assert len(ben) == 11
    adapter_threshold = float(scores["CALIBRATION"]["adapter"][ben].max())
    thresholds = {
        "frozen": p["reference_thresholds"]["frozen"],
        "calibration_only": p["reference_thresholds"]["calibration_only"],
        "full_v3": p["reference_thresholds"]["challenger"],
        "adapter": adapter_threshold,
        "adapter_at_frozen_threshold": p["reference_thresholds"]["frozen"],
    }
    output.mkdir(parents=True, mode=0o700)
    cal_scores = scores["CALIBRATION"]["adapter"][ben]
    atomic_json(
        output / "thresholds.json",
        {
            "thresholds": thresholds,
            "comparator": ">",
            "new_threshold_fit_partition": "11canonicaleligibleCALbenign only",
            "new_threshold_leave_one_out_range": [
                min(float(np.delete(cal_scores, i).max()) for i in range(11)),
                max(float(np.delete(cal_scores, i).max()) for i in range(11)),
            ],
            "fixed_v2_point_secondary_not_selected": True,
            "DEV_or_BODY_fit_rows": 0,
        },
    )
    summaries = {}
    for role, d in data.items():
        ix = masks[role]
        yy = d["binary_y"][ix]
        rr = [rows[role][int(i)] for i in ix]
        group_roots = module("materialize-request-v3").lineage_roots(rows[role])
        group_ids = np.array([group_roots[int(i)] for i in ix])
        sizes = Counter(group_ids)
        group_w = np.array([1 / sizes[g] for g in group_ids])
        near_w, near_components, near_pairs = ev.near_components(
            rr, d["frozen_runtime"][ix], d["x"][ix]
        )
        arms = {}
        for name, threshold in thresholds.items():
            s = scores[role]["adapter" if name == "adapter_at_frozen_threshold" else name][ix]
            families = {}
            for family in ["xss", "cmd_injection", "sqli", "path_traversal"]:
                j = np.array(
                    [i for i, r in enumerate(rr) if r["family"] == family and yy[i] == 1], np.int64
                )
                families[family] = {
                    "attack_views": len(j),
                    "detected": int(np.sum(s[j] > threshold)),
                    "recall": float(np.mean(s[j] > threshold)) if len(j) else None,
                }
            post = np.array(
                [i for i, r in enumerate(rr) if r["method"] == "POST" and yy[i] == 0], np.int64
            )
            modes = (
                {
                    k: ev.metrics(yy, scores[role][k][ix], threshold)
                    for k in ["adapter_disabled", "counts_only", "syntax_only"]
                }
                if name.startswith("adapter")
                else None
            )
            allix = ev.selected(d, rows[role], False) if role != "BODY_EXPOSED" else ix
            base_score = scores[role]["adapter" if name == "adapter_at_frozen_threshold" else name]
            arms[name] = {
                "metrics": ev.metrics(yy, s, threshold),
                "families": families,
                "benign_POST": ev.metrics(yy[post], s[post], threshold) if len(post) else None,
                "receipt_sensitivity": ev.metrics(
                    d["binary_y"][allix], base_score[allix], threshold
                ),
                "lineage_equal_weight": ev.metrics(yy, s, threshold, group_w),
                "near_component_equal_weight": ev.metrics(yy, s, threshold, near_w),
                "workflow": {
                    w: ev.metrics(
                        yy[[r["workflow_group"] == w for r in rr]],
                        s[[r["workflow_group"] == w for r in rr]],
                        threshold,
                    )
                    for w in sorted({r["workflow_group"] for r in rr})
                },
                "method": {
                    method: ev.metrics(
                        yy[[r["method"] == method for r in rr]],
                        s[[r["method"] == method for r in rr]],
                        threshold,
                    )
                    for method in sorted({r["method"] for r in rr})
                },
                "adapter_ablations_at_same_threshold": modes,
            }
        summaries[role] = {
            "canonical_views": len(ix),
            "lineage_components": len(set(group_ids)),
            "near_components": near_components,
            "near_pairs": near_pairs,
            "arms": arms,
        }
    bsum = summaries["BODY_EXPOSED"]["arms"]["adapter"]["metrics"]
    devsum = summaries["DEVELOPMENT"]["arms"]["adapter"]["metrics"]
    decision = (
        "CASE_A_ADDITIVE_VALUE_WITH_PRESERVED_LEGACY"
        if bsum["TP"] >= 2 and bsum["FP"] == 0 and devsum["FP"] == 0
        else "CASE_B_NO_DEMONSTRATED_BENEFIT"
    )
    paired = {}
    for role in ["DEVELOPMENT", "BODY_EXPOSED"]:
        ix = masks[role]
        y = data[role]["binary_y"][ix]
        ap = scores[role]["adapter"][ix] > adapter_threshold
        paired[role] = {}
        for ref in ["frozen", "calibration_only", "full_v3"]:
            rp = scores[role][ref][ix] > thresholds[ref]
            paired[role][ref] = {
                "adapter_only_attack": int(np.sum(ap & ~rp & (y == 1))),
                "reference_only_attack": int(np.sum(~ap & rp & (y == 1))),
                "both_attack": int(np.sum(ap & rp & (y == 1))),
                "neither_attack": int(np.sum(~ap & ~rp & (y == 1))),
                "new_benign_FP": int(np.sum(ap & ~rp & (y == 0))),
                "removed_benign_FP": int(np.sum(~ap & rp & (y == 0))),
            }
    a.assert_frozen()
    final = {
        "run_id": run.name,
        "decision": decision,
        "feature_selection": "Schema tail31, label-free membership; experiment exploratory",
        "dataset_fingerprint": p["dataset_fingerprint"],
        "body_cohort_fingerprint": bm["dataset_fingerprint"],
        "plan_fingerprint": p["fingerprint"],
        "thresholds": thresholds,
        "parity": parity,
        "backbone_hashes_after": a.backbone_hashes,
        "backbone_hashes_identical": a.backbone_hashes == p["backbone_parameter_hashes"],
        "summaries": summaries,
        "paired": paired,
        "exposure": "OldDEV90andbody8alreadyexposed; not independent confirmation",
        "threshold_vs_function": "Zero-body score and original-threshold parity are exact. Predictions at newCALthreshold may differ due threshold only; secondary fixedpoint is not post-selected.",
        "uncertainty": "Exactbinomial intervals IID sensitivity only;4DEVlineage/3bodylineage groups, no independent group CI or FPR<=1%certification",
        "RULE_AI_COMPLEMENTARITY": "NOT_MEASURED",
        "INDEPENDENT_QUALITY_CERTIFIED": False,
        "PRODUCTION_PROMOTION": "NOT_AUTHORIZED",
        "no_threshold_changes_to_references": True,
        "new_requests": 0,
        "sealed_opened": False,
    }
    atomic_json(output / "evaluation.json", final)
    np.savez(
        output / "scores-private.npz",
        **{role + "_" + name: v for role, ss in scores.items() for name, v in ss.items()},
    )
    print(
        json.dumps(
            {
                "decision": decision,
                "thresholds": thresholds,
                "parity": parity,
                "DEV": {n: v["metrics"] for n, v in summaries["DEVELOPMENT"]["arms"].items()},
                "BODY": {n: v["metrics"] for n, v in summaries["BODY_EXPOSED"]["arms"].items()},
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

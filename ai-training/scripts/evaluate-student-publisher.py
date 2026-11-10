#!/usr/bin/env python3
"""Manual final420 checkpoint evaluation under the previously locked protocol."""

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from idps_ai.common import atomic_json, canonical_bytes, digest, file_sha256
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.deep import forward
from idps_ai.training.partial import partial_loss
from idps_ai.training.publisher_evaluation import fit_balanced_threshold, group_metrics, metrics
from idps_ai.training.student_publisher import order_for_epoch

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "ai-training/.artifacts/student_training_20261110/student-training-v1-100k-r2"
LEGACY = [
    (
        "ai-training/.artifacts/autonomous_http_intelligence_20261104/waf-content-v2/numeric-only.npz",
        True,
    ),
    (
        "ai-training/.artifacts/autonomous_content_intelligence_20261104/waf-rich-v1/rich-content.npz",
        True,
    ),
    ("ai-training/.artifacts/request_intelligence_v2_20261104/waf-rich-v2/rich-content.npz", False),
]


def load(p):
    return json.loads(Path(p).read_text())


def check_training(run):
    plan = load(run / "plan.json")
    p = dict(plan)
    assert p.pop("fingerprint") == digest(p)
    for name, sha in plan["code_hashes"].items():
        assert file_sha256(REPO / name) == sha
    done = load(run / "training-completion.json")
    assert done["state"] == "COMPLETED"
    assert load(run / "attempts/train/result.json")["state"] == "COMPLETED"
    assert load(run / "attempts/train/thermal-report.json")["state"] == "COMPLETED"
    ck = load_checkpoint(run / "model")
    m = ck.model
    s = ck.state
    assert (
        not ck.used_previous
        and m.steps == plan["planned_steps"] == done["optimizer_updates"] == 420
    )
    assert file_sha256(ck.path / "manifest.json") == done["checkpoint_manifest_sha256"]
    assert s["plan_fingerprint"] == plan["fingerprint"] == done["plan_fingerprint"]
    assert s["dataset_fingerprint"] == plan["dataset_fingerprint"] == done["dataset_fingerprint"]
    assert s["split_fingerprint"] == plan["split_fingerprint"]
    assert (
        m.layer_dims == [588, 64, 64, 64, 64, 8]
        and sum(v.size for v in m.parameters.values()) == 50696
    )
    assert (
        s["epoch"] == 10
        and s["cursor"] == 2667
        and s["scheduler"] == {"kind": "constant", "learning_rate": 0.001, "step": 420}
    )
    losses = load(run / "loss-history.json")
    assert losses == s["losses"] and len(losses) == 420
    assert [r["step"] for r in losses] == list(range(1, 421)) and sum(
        v["batch_rows"] for v in losses
    ) == 26670
    assert all(np.isfinite(v["loss"]) for v in losses)
    for epoch in range(10):
        part = [v for v in losses if v["epoch"] == epoch]
        assert len(part) == 42 and sum(v["batch_rows"] for v in part) == 2667
    for name, sha in plan["data_files"].items():
        assert file_sha256(run / "data" / name) == sha
    with np.load(run / "data/train.npz", allow_pickle=False) as z:
        groups = z["groups"]
    rng = np.random.default_rng(17)
    for _ in range(10):
        expected = order_for_epoch(rng, groups)
    assert np.array_equal(expected, ck.permutation) and rng.bit_generator.state == s["RNG"]
    initial = plan["initial_weights_sha"]
    final = digest({k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in m.parameters.items()})
    assert (
        final != initial
        and any(np.any(v) for v in m.m.values())
        and any(np.any(v) for v in m.v.values())
    )
    for v in m.arrays().values():
        assert np.isfinite(v).all()
        v.setflags(write=False)
    return plan, ck, losses, final


def source_metadata():
    rows = []
    reasons = Counter()
    waterfall = Counter()
    classes = Counter()
    eligible = {}
    for line in (SOURCE / "materialized/ledger.jsonl").open():
        m = json.loads(line)
        rows.append(m)
        why = set(m["reasons"])
        reasons.update(why)
        if m["source"] == "first-party":
            stage = "REFERENCE_ONLY_NO588_NOSEMANTIC_LABEL"
        elif not m["parsed"] or m["feature_ref"] is None:
            stage = "SOURCE_OR_FEATURE_INVALID"
        elif m["target"] is None:
            stage = "NO_PUBLISHER_TARGET"
        elif "PROTECTED_OR_CONFLICT_COMPONENT" in why:
            stage = "PROTECTED_OR_LABEL_CONFLICT_COMPONENT"
        elif "EXACT_REPRESENTATION_DUPLICATE" in why:
            stage = "EXACT_DUPLICATE_OUTSIDE_BLOCKED_COMPONENT"
        elif why:
            stage = "OTHER_EXCLUSION"
        else:
            stage = "ACCEPTED_SILVER"
        waterfall[stage] += 1
        if m["decision"] == "TRAINING_ELIGIBLE":
            assert stage == "ACCEPTED_SILVER"
            eligible[m["row"]] = m
            classes[str(m["target"])] += 1
    db = sqlite3.connect(f"file:{SOURCE}/materialized/index.sqlite?mode=ro", uri=True)
    methods = dict(
        db.execute("SELECT r.i,json_extract(r.j,'$.method') FROM r JOIN accepted USING(i)")
    )
    conflict_views = db.execute(
        "SELECT count(*) FROM (SELECT v FROM r WHERE v IS NOT NULL GROUP BY v,task HAVING min(y)!=max(y))"
    ).fetchone()[0]
    conflict_raw = db.execute(
        "SELECT count(*) FROM (SELECT raw FROM r WHERE raw IS NOT NULL GROUP BY raw,task HAVING min(y)!=max(y))"
    ).fetchone()[0]
    db.close()
    assert sum(waterfall.values()) == 100000 and len(eligible) == 3783
    return (
        rows,
        eligible,
        methods,
        {
            "exclusive_waterfall": dict(waterfall),
            "overlapping_reasons": dict(reasons),
            "accepted_publisher_classes": dict(classes),
            "mixed_label_view_keys": conflict_views,
            "mixed_label_representation_keys": conflict_raw,
        },
    )


def legacy_protection_diagnostic(rows):
    legacy_train = set()
    heldout = set()
    for filename, is_legacy in LEGACY:
        with np.load(REPO / filename, allow_pickle=False) as z:
            g = z["group"]
            role = z["role"]
            if is_legacy:
                legacy_train.update(v.decode() for v in g[role == 0])
            heldout.update(v.decode() for v in g[role != 0])
    key = (SOURCE / "identity.key").read_bytes()

    def opaque(value):
        return hmac.new(key, canonical_bytes(["safe-template", value]), hashlib.sha256).hexdigest()

    train_only = {opaque(v) for v in legacy_train - heldout}
    heldout_keys = {opaque(v) for v in heldout}
    by_component = {}
    marked = []
    with sqlite3.connect(f"file:{SOURCE}/materialized/index.sqlite?mode=ro", uri=True) as db:
        for i, raw in db.execute("SELECT i,j FROM r ORDER BY i"):
            record = json.loads(raw)
            g = set(record["groups"])
            m = rows[i]
            flags = by_component.setdefault(m["component"], {"heldout": False, "near": False})
            flags["heldout"] |= bool(g & heldout_keys)
            flags["near"] |= "PROTECTED_NEAR_COMMON_CONTRACT" in m["reasons"]
            if g & train_only:
                marked.append(i)
    q = [i for i in marked if rows[i]["decision"] != "TRAINING_ELIGIBLE"]
    no_direct_near = [i for i in q if "PROTECTED_NEAR_COMMON_CONTRACT" not in rows[i]["reasons"]]
    component_screen = [
        i for i in no_direct_near if not any(by_component[rows[i]["component"]].values())
    ]
    return {
        "legacy_TRAIN_only_template_keys_vs_all_known_CAL_DEV": len(train_only),
        "source_rows_matching": len(marked),
        "quarantined_matching": len(q),
        "quarantined_matching_without_direct_current_near": len(no_direct_near),
        "quarantined_matching_without_known_heldout_group_or_current_near_anywhere_in_component": len(
            component_screen
        ),
        "interpretation": "potential over-conservatism only, NOT newly admissible counts; protectedviews/routes, incompatiblelegacynear, exactconflicts/rawlineage still require qualification",
        "policy_unchanged": True,
        "source_of_conservatism": "student-data-pipeline.protected uses all_protected=True for both legacycorpora, including their TRAIN",
    }


def evaluate(run, output):
    assert not output.exists(), "New immutable evaluation directory required"
    began = time.monotonic()
    plan, ck, losses, weights_sha = check_training(run)
    model = ck.model
    output.mkdir(parents=True, mode=0o700)
    rows, eligible, methods, yield_report = source_metadata()
    yield_report["legacy_protection_diagnostic"] = legacy_protection_diagnostic(rows)
    split = load(run / "data/split.json")
    canonical_ids = {v["row"] for v in split}
    by_view = {eligible[v["row"]]["view_key"]: v for v in split}
    assert len(split) == 3751 and len(canonical_ids) == 3751
    aliases = []
    scope_records = Counter()
    alias_classes = Counter()
    for row, m in eligible.items():
        canonical = by_view[m["view_key"]]
        assert canonical["target"] == m["target"]
        scope_records[canonical["role"]] += 1
        if row != canonical["row"]:
            aliases.append(
                {
                    "row": row,
                    "canonical_row": canonical["row"],
                    "role": canonical["role"],
                    "label": m["target"],
                }
            )
            alias_classes[str(m["target"])] += 1
    assert len(aliases) == 32 and sum(scope_records.values()) == 3783
    atomic_json(output / "aliases-private.json", aliases)

    def read_role(role):
        with np.load(run / "data" / f"{role.lower()}.npz", allow_pickle=False) as z:
            return {k: z[k].copy() for k in z.files}

    def score(d):
        _, probabilities, cache = forward(model, d["x"])
        scores = (1 - probabilities[:, 0]).astype(np.float32)
        family = np.where(d["y"] == 0, 0, -1)
        objective = partial_loss(
            cache[-1][1],
            d["y"],
            family,
            model.objective["smoothing"],
            0.0,
            model.objective["binary_class_weights"],
        )[0]
        return scores, float(objective)

    def meta(row):
        m = eligible[int(row)]
        return {
            "window": str(int(m["source_row"] >= 1048576)),
            "body": m["body_observation"],
            "method": methods[int(row)],
        }

    def baselines(d):
        result = {
            "majority_prior": np.full(len(d["y"]), plan["majority_baseline"]["anomaly_prior"])
        }
        for key in ["window", "body"]:
            bins = plan["shortcut_baselines_TRAIN_only"][key]
            result["metadata_" + key] = np.array(
                [
                    bins[value][1] / sum(bins[value])
                    if (value := meta(row)[key]) in bins
                    else plan["majority_baseline"]["anomaly_prior"]
                    for row in d["rows"]
                ]
            )
        return result

    data = {r: read_role(r) for r in ["TRAIN", "CALIBRATION"]}
    scores = {}
    objectives = {}
    for role, d in data.items():
        neural, objective = score(d)
        scores[role] = {"candidate": neural, **baselines(d)}
        objectives[role] = objective
    # Lock every operating point from CAL only BEFORE EVALUATION tensor/model scores.
    thresholds = {
        name: fit_balanced_threshold(data["CALIBRATION"]["y"], s)
        for name, s in scores["CALIBRATION"].items()
    }
    atomic_json(
        output / "thresholds.json",
        {
            "models": thresholds,
            "fixed_threshold": 0.5,
            "comparator": ">",
            "source": "CALIBRATION_ONLY",
            "config_sha256": plan["config_sha256"],
            "plan_fingerprint": plan["fingerprint"],
            "evaluation_labels_used_for_threshold": False,
        },
    )
    threshold_sha = file_sha256(output / "thresholds.json")
    data["EVALUATION"] = read_role("EVALUATION")
    neural, objective = score(data["EVALUATION"])
    scores["EVALUATION"] = {"candidate": neural, **baselines(data["EVALUATION"])}
    objectives["EVALUATION"] = objective
    results = {}
    retained = {}
    grouped = {}
    by_stratum = {}
    for role, d in data.items():
        results[role] = {}
        retained[role] = {}
        grouped[role] = {}
        id_to_slot = {int(row): i for i, row in enumerate(d["rows"])}
        record_slots = [
            id_to_slot[by_view[m["view_key"]]["row"]]
            for m in eligible.values()
            if by_view[m["view_key"]]["role"] == role
        ]
        for name, scores_array in scores[role].items():
            results[role][name] = {}
            retained[role][name] = {}
            grouped[role][name] = {}
            for point, t in [
                ("fixed0.5", 0.5),
                ("calibrated_balanced", thresholds[name]["threshold"]),
            ]:
                results[role][name][point] = metrics(d["y"], scores_array, t)
                retained[role][name][point] = metrics(
                    d["y"][record_slots], scores_array[record_slots], t
                )
                grouped[role][name][point] = group_metrics(d["y"], scores_array, t, d["groups"])
        by_stratum[role] = {}
        for field in ["window", "body", "method"]:
            categories = np.array([meta(row)[field] for row in d["rows"]])
            by_stratum[role][field] = {}
            for value in sorted(set(categories)):
                ix = np.flatnonzero(categories == value)
                by_stratum[role][field][value] = metrics(
                    d["y"][ix], scores[role]["candidate"][ix], thresholds["candidate"]["threshold"]
                )
    np.savez(
        output / "scores-private.npz",
        **{role + "_" + name: s for role, models in scores.items() for name, s in models.items()},
    )
    epochs = [
        {
            "epoch": e,
            "updates": 42,
            "weighted_by_batch_rows_mean_logged_loss": float(
                np.average(
                    [v["loss"] for v in losses if v["epoch"] == e],
                    weights=[v["batch_rows"] for v in losses if v["epoch"] == e],
                )
            ),
        }
        for e in range(10)
    ]
    resource = []
    for line in (run / "attempts/train/thermal-samples.jsonl").open():
        resource.append(json.loads(line))
    report = {
        "schema_version": "STUDENT_PUBLISHER_EVALUATION-1",
        "run_id": run.name,
        "task": "publisher_anomaly",
        "dataset_fingerprint": plan["dataset_fingerprint"],
        "split_fingerprint": plan["split_fingerprint"],
        "plan_fingerprint": plan["fingerprint"],
        "checkpoint_manifest_sha256": file_sha256(ck.path / "manifest.json"),
        "checkpoint_path": str(ck.path),
        "training": {
            "state": "COMPLETED",
            "steps": 420,
            "planned_steps": 420,
            "epoch": 10,
            "parameters": 50696,
            "unique_gradient_views": 2667,
            "gradient_presentations": 26670,
            "first_batch_loss": losses[0]["loss"],
            "final_batch_loss": losses[-1]["loss"],
            "epoch_logged_loss": epochs,
            "final_objective_losses": objectives,
            "optimizer_state": "AdamW m/v finite nonzero step420",
            "sampler_RNG_order_epoch_cursor": "REPLAY_MATCH",
            "preflight_exact_resume": load(run / "actual-preflight.json"),
            "weights_sha256": weights_sha,
            "checkpoint_selection": "finalfixedbudgetonly",
        },
        "accounting": {
            "accepted_records": 3783,
            "canonical_views": 3751,
            "aliases": 32,
            "alias_classes": dict(alias_classes),
            "retained_records_by_role": dict(scope_records),
            "canonical_counts": plan["split_counts"],
            "alias_disposition": "preserved source records sharing exact588view with canonical representative; notlost/quarantined/reserved; never extra gradientweight",
        },
        "thresholds": thresholds,
        "threshold_file_sha256": threshold_sha,
        "metrics": results,
        "retained_record_metrics": retained,
        "group_weighted_metrics": grouped,
        "per_stratum": by_stratum,
        "per_source": {"source": "WAF", "metrics_same_as_aggregate": True},
        "data_yield": yield_report,
        "resources": {
            "background_supervisor_seconds": load(run / "attempts/train/result.json")["seconds"],
            "background_committed_new_updates": 418,
            "background_gradient_presentations": 26542,
            "peak_C": max(v["peak_temperature_C"] for v in resource),
            "max_memory_bytes": max(v["resources"].get("cgroup_memory_bytes", 0) for v in resource),
            "min_MemAvailable_bytes": min(v["resources"]["MemAvailable_bytes"] for v in resource),
            "quota_values": sorted(set(v["CPU_quota_percent_one_core"] for v in resource)),
            "paused_samples": sum(v["paused"] for v in resource),
            "OOM_events": False,
            "watchdog": "COMPLETED",
        },
        "limits": [
            "SILVERpublisherlabels, notverifiedattackintent",
            "internalexposedgroupedholdout,notindependentcross-domain",
            "unknowncampaign/time/globalrawlineagePARTIAL",
            "selectedtwo-windowpoolnotdeploymentprevalence",
            "teacherpretrainingoverlap2912sourceeligible,butcandidatefresh",
            "familygroundtruthunavailable",
            "WilsonCIisnominaliid;groupdependence/labelnoiseuncovered",
        ],
        "frozen_v2_numerical_comparison": "NOT_RUN_optionaldiagnosticomitted;notindependentunseensourcebaseline",
        "no_new_optimizer_updates": True,
        "promotion": False,
        "sealed_access": False,
        "elapsed_seconds": time.monotonic() - began,
    }
    assert (
        digest({k: hashlib.sha256(v.tobytes()).hexdigest() for k, v in model.parameters.items()})
        == weights_sha
    )
    assert threshold_sha == file_sha256(output / "thresholds.json")
    report["fingerprint"] = digest(report)
    atomic_json(output / "metrics.json", report)
    print(
        json.dumps(
            {
                "evaluation": "COMPLETED",
                "candidate_CAL": results["CALIBRATION"]["candidate"],
                "candidate_EVAL": results["EVALUATION"]["candidate"],
                "baselines_EVAL": {
                    name: r for name, r in results["EVALUATION"].items() if name != "candidate"
                },
                "accounting": report["accounting"],
                "yield": yield_report,
                "resources": report["resources"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    with threadpool_limits(limits=1):
        evaluate(a.run.resolve(), a.output.resolve())

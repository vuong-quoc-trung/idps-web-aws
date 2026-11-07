#!/usr/bin/env python3
"""Locked publisher/Oracle strata evaluation; prospective requires an explicit one-shot flag."""

import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits

from idps_ai.common import CLASSES, atomic_json, digest, file_sha256
from idps_ai.features.normalization_ablation import content
from idps_ai.features.request_preprocessing import bounded_spec
from idps_ai.mvp_inference import ResearchMVP
from idps_ai.training.checkpoint import load_checkpoint

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "ai-training/.artifacts"


def load(p):
    return json.loads(p.read_text())


def module(name):
    s = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def receipt(base):
    r = load(base / "receipt.json")
    h = load(base / "request-headers.json")
    rh = load(base / "response-headers.json")
    assert (
        file_sha256(base / "request-body.bin") == r["request_body_sha256"]
        and digest(h) == r["request_headers_sha256"]
    )
    assert (
        file_sha256(base / "response-body.bin") == r["response_sha256"]
        and digest(rh) == r["response_headers_sha256"]
    )
    return {
        "method": r["method"],
        "url": r["path"],
        "body": (base / "request-body.bin").read_text(),
        "headers": "\r\n".join(f"{k}: {v}" for k, v in h.items()),
    }


def locate(rid):
    choices = [ART / "final_training_unblock_20261107/security-calibration/receipts" / rid]
    for phase in [
        "training_unblock_20261107/campaign-capture-v2",
        "quality_lab_20261107/cohort-v3",
        "quality_lab_20261107/cohort-v4-juice",
    ]:
        choices.extend(ART / phase / env / "receipts" / rid for env in ["dvwa", "juice"])
    found = [p for p in choices if (p / "receipt.json").exists()]
    assert len(found) == 1
    return found[0]


def vectors(requests):
    pv = module("p0-request-evaluate")
    frozen = ResearchMVP("request-v2", cpus=1)
    a = []
    b = []
    for req in requests:
        original = pv.vector(frozen, req)[0]
        shared, separate = content(req)
        assert np.array_equal(shared, original[76:])
        a.append(original)
        b.append(np.concatenate([original[:76], separate]))
    return np.array(a, np.float32), np.array(b, np.float32)


def export(output):
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = ART / "final_training_unblock_20261107/dataset"
    metadata = load(source / "dataset-release.json")
    for role in ["train", "calibration"]:
        assert file_sha256(source / (role + ".npz")) == metadata["files_sha256"][role + ".npz"]
        with np.load(source / (role + ".npz"), allow_pickle=False) as d:
            y = d["y"].copy()
            ids = d["ids"].astype(str)
            groups = d["groups"].copy()
        a, b = vectors([receipt(locate(rid)) for rid in ids])
        np.savez(output / (role + ".npz"), control=a, challenger=b, y=y, ids=ids, groups=groups)
    pv = module("p0-request-evaluate")
    p0 = ART / "p0_dvwa_20261105_1520"
    _, _, rows = pv.corpus(p0 / "capture-final")
    a, b = vectors([r["http_request"] for r in rows])
    alerts = {
        r["request_id"]: bool(r["signature_ids"]) for r in load(p0 / "suricata/request-alerts.json")
    }
    y = np.array(
        [
            0
            if r["lab_intent"] == "benign"
            else CLASSES.index(r["family"])
            if r["lab_intent"] == "attack"
            else -1
            for r in rows
        ],
        np.int64,
    )
    np.savez(
        output / "p0-development.npz",
        control=a,
        challenger=b,
        y=y,
        ids=np.array([r["request_id"] for r in rows]),
        groups=np.array([r["family"] for r in rows]),
        rule=np.array([alerts[r["request_id"]] for r in rows]),
    )
    report = {
        "status": "PASS",
        "oracle_TRAIN_exposed": 49,
        "oracle_CAL": 12,
        "P0_exposed_DEVELOPMENT": 111,
        "Oracle_inputs_used_for_WAF_fitting": 0,
        "prospective_samples_labels_features_opened": False,
        "frozen_control_bitwise_parity": True,
        "label_tier": "Internal Oracle and collector intent, independent human review PENDING",
        "input_role_contract_sha256": file_sha256(source / "dataset-release.json"),
        "source_sha256": file_sha256(__file__),
        "files_sha256": {p.name: file_sha256(p) for p in output.glob("*.npz")},
    }
    atomic_json(output / "report.json", report)
    print(json.dumps(report, indent=2))


def counts(scores, y, threshold):
    known = y >= 0
    flag = scores > threshold
    positive = y > 0
    c = {
        k: int(v.sum())
        for k, v in {
            "TP": known & flag & positive,
            "FN": known & ~flag & positive,
            "FP": known & flag & ~positive,
            "TN": known & ~flag & ~positive,
        }.items()
    }
    c["unknown_excluded"] = int((~known).sum())
    for name, hit, n in [
        ("recall", c["TP"], c["TP"] + c["FN"]),
        ("normal_flag_fraction", c["FP"], c["FP"] + c["TN"]),
    ]:
        c[name] = hit / n if n else None
        c[name + "_descriptive_iid_interval"] = (
            None
            if not n
            else [
                0 if hit == 0 else float(beta.ppf(0.025, hit, n - hit + 1)),
                1 if hit == n else float(beta.ppf(0.975, hit + 1, n - hit)),
            ]
        )
    return c


def score(net, x):
    return np.concatenate([net.predict(x[i : i + 512])[0] for i in range(0, len(x), 512)])


def paired_group_effect(control, challenger, y, groups, tc, tt):
    _, inverse = np.unique(groups, return_inverse=True)
    n = int(inverse.max()) + 1
    values = np.zeros((n, 2, 4), np.float64)
    for arm, scores, threshold in [(0, control, tc), (1, challenger, tt)]:
        flag = scores > threshold
        positive = y > 0
        for j, mask in enumerate(
            [flag & positive, ~flag & positive, flag & ~positive, ~flag & ~positive]
        ):
            np.add.at(values[:, arm, j], inverse, mask.astype(float))

    def delta(total):
        tpr = total[:, 0] / np.maximum(total[:, 0] + total[:, 1], 1)
        fpr = total[:, 2] / np.maximum(total[:, 2] + total[:, 3], 1)
        return np.array([tpr[1] - tpr[0], fpr[1] - fpr[0]])

    observed = delta(values.sum(axis=0))
    rng = np.random.default_rng(20261107)
    sampled = np.stack([delta(values[rng.integers(0, n, n)].sum(axis=0)) for _ in range(1000)])
    return {
        "observed_anomaly_TPR_delta": float(observed[0]),
        "observed_normal_flag_delta": float(observed[1]),
        "group_bootstrap_95_percentiles": np.quantile(sampled, [0.025, 0.975], axis=0).tolist(),
        "groups": n,
        "resamples": 1000,
        "scope": "Paired observed-template bootstrap; publisher labels and unknown campaign/source independence prevent population quality certification",
    }


def evaluate(root, oracle, open_prospective):
    p = module("scaled-normalization-experiment").plan(root)
    assert load(root / "training-completion.json")["state"] == "COMPLETED"
    assert load(root / "status.json")["state"] == "COMPLETED"
    assert (
        load(
            module("scaled-normalization-experiment").resource_root(root) / "resource-report.json"
        )["status"]
        == "PASS"
    )
    nets = {arm: load_checkpoint(root / arm) for arm in ["control", "challenger"]}
    assert all(n.model.steps == 3072 for n in nets.values())
    frozen = ResearchMVP("request-v2", cpus=1)
    models = {"frozen": frozen.v2_model, **{k: n.model for k, n in nets.items()}}
    corpus = Path(p["corpus"])
    report = load(corpus / "corpus-report.json")
    assert report["dataset_fingerprint"] == p["dataset_fingerprint"]
    ometa = load(oracle / "report.json")
    for name, sha in ometa["files_sha256"].items():
        assert file_sha256(oracle / name) == sha
    thresholds = {}
    calibration_scores = {}
    with np.load(corpus / "calibration.npz", allow_pickle=False) as d:
        for name, net in models.items():
            x = d["challenger"] if name == "challenger" else d["control"]
            s = score(net, x)
            thresholds.setdefault(name, {})["publisher"] = (
                float(np.quantile(s[d["y"] == 0], 0.99, method="higher"))
                if name != "frozen"
                else frozen.v2_threshold
            )
    with np.load(oracle / "calibration.npz", allow_pickle=False) as d:
        for name, net in models.items():
            s = score(net, d["challenger"] if name == "challenger" else d["control"])
            thresholds[name]["Oracle"] = (
                float(s[d["y"] == 0].max()) if name != "frozen" else frozen.v2_threshold
            )
            calibration_scores[name] = counts(s, d["y"], thresholds[name]["Oracle"])
            for key in [
                "recall_descriptive_iid_interval",
                "normal_flag_fraction_descriptive_iid_interval",
            ]:
                calibration_scores[name].pop(key, None)
            calibration_scores[name]["interval_limit"] = (
                "Same calibration data selects threshold; no population FPR confidence bound from these counts."
            )
    lock = {
        "plan_sha256": p["plan_sha256"],
        "checkpoint_manifests": {k: file_sha256(v.path / "manifest.json") for k, v in nets.items()},
        "thresholds": thresholds,
        "evaluation_source_sha256": file_sha256(__file__),
        "Oracle_input_report_sha256": file_sha256(oracle / "report.json"),
        "protocol": p["evaluation_protocol"],
    }
    lock["fingerprint"] = digest(lock)
    target = root / "evaluation-lock.json"
    if target.exists():
        assert load(target) == lock, "Existing model/threshold/evaluation lock changed"
    else:
        atomic_json(target, lock)
    results = {
        "strata": {},
        "thresholds": thresholds,
        "Oracle_CAL_counts_selected_threshold_not_population_FPR": calibration_scores,
        "evaluation_lock_sha256": file_sha256(target),
        "publisher_labels_are_not_attack_ground_truth": True,
    }
    datasets = [
        ("publisher-development", corpus / "development.npz", "publisher"),
        ("Oracle-TRAIN-exposed", oracle / "train.npz", "Oracle"),
        ("P0-DEVELOPMENT-exposed", oracle / "p0-development.npz", "Oracle"),
    ]
    for label, path, tier in datasets:
        with np.load(path, allow_pickle=False) as d:
            outcome = {}
            paired_scores = {}
            for name, net in models.items():
                x = d["challenger"] if name == "challenger" else d["control"]
                t = time.perf_counter()
                s = score(net, x)
                elapsed = time.perf_counter() - t
                paired_scores[name] = s
                value = {
                    "counts": counts(s, d["y"], thresholds[name][tier]),
                    "inference_ms_per_row": 1000 * elapsed / len(x),
                    "scope": "exposed or publisher research; no independent population claim",
                }
                method_columns = {
                    key[7:]: i
                    for i, key in enumerate(bounded_spec()["columns"])
                    if key.startswith("method_")
                }
                value["by_method"] = {
                    method: counts(
                        s[d["control"][:, column] > 0.5],
                        d["y"][d["control"][:, column] > 0.5],
                        thresholds[name][tier],
                    )
                    for method, column in method_columns.items()
                    if np.any(d["control"][:, column] > 0.5)
                }
                if tier == "Oracle":
                    value["benign_workflow_flags"] = {
                        str(g): counts(
                            s[(d["groups"] == g) & (d["y"] == 0)],
                            d["y"][(d["groups"] == g) & (d["y"] == 0)],
                            thresholds[name][tier],
                        )
                        for g in np.unique(d["groups"][d["y"] == 0])
                    }
                    value["per_family"] = {
                        CLASSES[int(y)]: counts(
                            s[d["y"] == y], d["y"][d["y"] == y], thresholds[name][tier]
                        )
                        for y in np.unique(d["y"])
                        if y > 0
                    }
                    if "rule" in d.files:
                        value["AI_additional_attempt_flags_over_Suricata"] = int(
                            ((d["y"] > 0) & ~d["rule"] & (s > thresholds[name][tier])).sum()
                        )
                        value["rule_only"] = counts(d["rule"].astype(float), d["y"], 0.5)
                else:
                    value["publisher_PR_AUC"] = float(average_precision_score(d["y"], s))
                outcome[name] = value
            results["strata"][label] = outcome
            if tier == "publisher":
                results["publisher_paired_effect"] = paired_group_effect(
                    paired_scores["control"],
                    paired_scores["challenger"],
                    d["y"],
                    d["groups"],
                    thresholds["control"]["publisher"],
                    thresholds["challenger"]["publisher"],
                )
    # Bounded, predeclared exposed-development sensitivity, never model selection on prospective.
    sensitivity = {}
    pv = module("p0-request-evaluate")
    _, _, p0rows = pv.corpus(ART / "p0_dvwa_20261105_1520/capture-final")
    p0y = np.array(
        [
            0
            if r["lab_intent"] == "benign"
            else CLASSES.index(r["family"])
            if r["lab_intent"] == "attack"
            else -1
            for r in p0rows
        ]
    )
    for variant in ["headers_missing", "headers_long_fixed", "body_missing"]:
        requests = []
        for row in p0rows:
            req = dict(row["http_request"])
            if variant == "headers_missing":
                req["headers"] = None
            elif variant == "headers_long_fixed":
                req["headers"] = (req.get("headers") or "") + "\r\nUser-Agent: " + "Browser " * 100
            else:
                req["body"] = None
            requests.append(req)
        a, b = vectors(requests)
        sensitivity[variant] = {
            name: counts(
                score(net, b if name == "challenger" else a), p0y, thresholds[name]["Oracle"]
            )
            for name, net in models.items()
        }
    results["exposed_P0_sensitivity_no_threshold_retuning"] = sensitivity
    effect = results["publisher_paired_effect"]
    p0 = results["strata"]["P0-DEVELOPMENT-exposed"]
    extra_tp = p0["challenger"]["counts"]["TP"] - p0["control"]["counts"]["TP"]
    extra_fp = p0["challenger"]["counts"]["FP"] - p0["control"]["counts"]["FP"]
    point = (
        effect["observed_anomaly_TPR_delta"] >= 0.02
        and effect["observed_normal_flag_delta"] <= 0.002
        and extra_tp >= 4
        and extra_fp <= 0
    )
    intervals = effect["group_bootstrap_95_percentiles"]
    uncertainty = intervals[0][0] > 0 and intervals[1][1] <= 0.002
    results["research_decision_before_prospective"] = {
        "decision": "RETAIN_FOR_FURTHER_RESEARCH"
        if point and uncertainty
        else "REJECT_OR_INCONCLUSIVE_KEEP_FROZEN",
        "point_criteria_pass": point,
        "group_bootstrap_criteria_pass": uncertainty,
        "P0_extra_attempt_flags": extra_tp,
        "P0_extra_benign_flags": extra_fp,
        "automatic_promotion": False,
        "production_independent_quality_claim": False,
    }
    if open_prospective:
        marker = root / "PROSPECTIVE_OPENED_ONCE.json"
        assert not marker.exists(), "Prospective already consumed; no tuning/reopening"
        atomic_json(
            marker,
            {
                "authorized_command_explicit_flag": True,
                "evaluation_lock_sha256": file_sha256(target),
                "opened_at": time.time(),
            },
        )
        sealed = ART / "training_unblock_20261107/dataset-release-final-v2"
        seal = load(sealed / "prospective-seal.json")
        assert file_sha256(sealed / "prospective-manifest.json") == seal["manifest_sha256"]
        rows = load(sealed / "prospective-manifest.json")["records"]
        assert len(rows) == 12
        req = [receipt(Path(r["receipt_file"]).parent) for r in rows]
        a, b = vectors(req)
        y = np.array(
            [
                0
                if r["intent"] == "BENIGN"
                else CLASSES.index(r["family"])
                if r["intent"] == "ATTACK_ATTEMPT"
                else -1
                for r in rows
            ]
        )
        results["prospective_once"] = {
            name: counts(
                score(net, b if name == "challenger" else a), y, thresholds[name]["Oracle"]
            )
            for name, net in models.items()
        }
        results["prospective_limit"] = (
            "12same-application rows, review pending; cannot establish<=1%FPR or cross-domain generalization. No subsequent tuning."
        )
    else:
        results["prospective_opened"] = False
    atomic_json(
        root
        / ("evaluation-prospective-once.json" if open_prospective else "evaluation-exposed.json"),
        results,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["export", "evaluate"])
    p.add_argument("--output", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--oracle", type=Path)
    p.add_argument("--open-prospective", action="store_true")
    a = p.parse_args()
    with threadpool_limits(limits=1):
        if a.command == "export":
            export(a.output.resolve())
        else:
            evaluate(a.root.resolve(), a.oracle.resolve(), a.open_prospective)

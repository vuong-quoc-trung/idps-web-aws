#!/usr/bin/env python3
"""Once-only frozen-candidate cohorts. No optimizer, threshold fitting or promotion."""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.data.http_curation import require_development_source
from idps_ai.features.request_preprocessing import encode_request
from idps_ai.features.request_view import PROFILE, fingerprint
from idps_ai.request_inference import RequestInferencePipeline, fresh_lab_evaluation
from idps_ai.training.deep import AUTOENCODERS
from idps_ai.training.evaluation import latency_ms
from idps_ai.training.generalization import binary_metrics, calibration_audit
from idps_ai.training.request_training import selected_training
from idps_ai.training.resources import resource_envelope


def run(registry_path, real_data, lab, eve, output):
    # This research entry point must never consume the replacement sealed holdouts.
    for source in (Path(lab) / "observer.jsonl", Path(eve), Path(real_data) / "sample.parquet"):
        require_development_source(source)
    registry = load_json(registry_path)
    real_data = Path(real_data)
    lab = Path(lab)
    output = Path(output)
    if output.exists():
        raise PipelineError("Cohort evaluation output must be new; completed evidence is immutable")
    selection = Path(registry["selection"])
    if (
        file_sha256(selection) != registry["selection_sha256"]
        or load_json(selection)["test_quality_opened"] is not False
    ):
        raise PipelineError("Validation selection must be frozen before cohort scoring")
    source = load_json(real_data / "manifest.json")
    if (
        source["projection_sha256"] != fingerprint()
        or file_sha256(real_data / "sample.parquet") != source["files"]["sample.parquet"]
    ):
        raise PipelineError("Real HTTP sample/projection integrity mismatch")
    output.mkdir(mode=0o700, parents=True)
    # Keep full publisher sample primary, including duplicates and provenance anomalies.
    public = list(iter_rows(real_data / "sample.parquet"))
    if len(public) != source["sample_records"] or len(public) > 100000:
        raise PipelineError("Bounded sample count mismatch")
    y = np.array([r["label"] if r["label"] is not None else -1 for r in public])
    usable = np.array([r["numbers_json"] is not None for r in public])
    known = np.isin(y, [0, 1])
    keys = [r["natural_key"] for r in public]
    by_identity = defaultdict(set)
    for r in public:
        if r["label"] is not None:
            by_identity[r["natural_key"]].add(r["label"])
    first = set()
    unique = np.zeros(len(public), bool)
    for i, r in enumerate(public):
        if keys[i] not in first and len(by_identity[keys[i]]) == 1:
            unique[i] = True
        first.add(keys[i])
    numbers = [json.loads(r["numbers_json"]) if r["numbers_json"] else None for r in public]
    views = [
        {"profile": PROFILE, "implementation_sha256": fingerprint(), "numbers": n}
        if n is not None
        else None
        for n in numbers
    ]
    inputs = defaultdict(lambda: [0, 0])
    for i, n in enumerate(numbers):
        if n is not None and known[i]:
            inputs[digest(n)][y[i]] += 1
    public_result = {
        "source_manifest_sha256": file_sha256(real_data / "manifest.json"),
        "sample_records": len(public),
        "scorable": int(usable.sum()),
        "unknown_labels": int((~known).sum()),
        "request_weighted_primary": True,
        "raw70_mixed_label_view_groups": sum(a > 0 and b > 0 for a, b in inputs.values()),
        "minimum_label_disagreements_raw70_view": sum(min(v) for v in inputs.values()),
        "models": {},
        "no_training_or_threshold_tuning": True,
        "all_dates_including_outside_declared_window_retained": True,
    }
    groups = defaultdict(dict)
    for name, entry in registry["models"].items():
        groups[entry["dataset"]][name] = entry["bundle"]
    with resource_envelope(4, 16):
        for i, (dataset, bundles) in enumerate(groups.items()):
            fresh_lab_evaluation(
                dataset,
                eve,
                lab / "observer.jsonl",
                lab / "student-audit.log",
                lab / "access.log",
                bundles,
                output / f"lab-group{i}.json",
                4,
            )
        for name, entry in registry["models"].items():
            pipe = RequestInferencePipeline(entry["bundle"], 4)
            if (
                file_sha256(Path(entry["bundle"]) / "model_manifest.json")
                != entry["manifest_sha256"]
            ):
                raise PipelineError("Candidate bundle changed after selection freeze")
            score = np.full(len(public), -1, np.float32)
            idx = np.flatnonzero(usable)
            for start in range(0, len(idx), 512):
                selected = idx[start : start + 512]
                score[selected] = pipe.predict_views([views[i] for i in selected])
            # Missing projection is abstention/non-detection, not silently removed from full primary.
            np.savez_compressed(output / (name + "-scores.npz"), scores=score)
            x, *_ = selected_training(
                entry["dataset"], pipe.manifest["model_kind"], entry.get("config")
            )
            train = {digest(v.tolist()) for v in x}
            novel = np.array(
                [
                    n is not None and digest(encode_request(pipe.spec, n).tolist()) not in train
                    for n in numbers
                ]
            )
            byfamily = {}
            for family in sorted(
                {r["attack_family"] or "unknown_or_mixed" for r in public if r["label"] == 1}
            ):
                mask = np.array(
                    [
                        r["label"] == 1 and (r["attack_family"] or "unknown_or_mixed") == family
                        for r in public
                    ]
                )
                byfamily[family] = {
                    "requests": int(mask.sum()),
                    "binary_recall": float(np.mean(score[mask] >= pipe.manifest["threshold"])),
                }
            bycapec = {}
            for capec in sorted({c for r in public for c in r["published_capec"]}):
                mask = np.array([c in r["published_capec"] for r in public for c in [capec]])
                bycapec[capec] = {
                    "requests": int(mask.sum()),
                    "flagged": int(np.sum(score[mask] >= pipe.manifest["threshold"])),
                }
            dates = defaultdict(list)
            for i, r in enumerate(public):
                dates[
                    datetime.fromtimestamp(r["timestamp"], timezone.utc).strftime("%Y-%m-%d")
                    if r["timestamp"] is not None
                    else "MISSING"
                ].append(i)
            byday = {
                d: binary_metrics(
                    y[np.array(ii)][known[ii]],
                    score[np.array(ii)][known[ii]],
                    pipe.manifest["threshold"],
                )
                for d, ii in dates.items()
                if known[ii].any()
            }
            result = {
                "manifest_sha256": entry["manifest_sha256"],
                "threshold": pipe.manifest["threshold"],
                "full_publisher_sample": binary_metrics(
                    y[known], score[known], pipe.manifest["threshold"]
                ),
                "unambiguous_unique_observation_sensitivity": binary_metrics(
                    y[known & unique], score[known & unique], pipe.manifest["threshold"]
                ),
                "novel_model_input_sensitivity": binary_metrics(
                    y[known & novel], score[known & novel], pipe.manifest["threshold"]
                )
                if np.any(known & novel)
                else None,
                "novel_model_input_rows": int(np.sum(known & novel)),
                "binary_recall_by_mapped_family": byfamily,
                "binary_flags_by_CAPEC": bycapec,
                "by_actual_UTC_day": byday,
                "scores_sha256": file_sha256(output / (name + "-scores.npz")),
                "family_inference_enabled": False,
                "threshold_tuned_on_cohort": False,
            }
            if pipe.manifest["model_kind"] not in AUTOENCODERS and usable[known].all():
                result["probability_diagnostic"] = calibration_audit(y[known], score[known])
            public_result["models"][name] = result
            atomic_json(output / "public-results.json", public_result)
    result = {
        "format_version": 1,
        "status": "EXECUTED_NOT_PRODUCTION_ACCEPTANCE",
        "registry_sha256": file_sha256(registry_path),
        "selected_research_candidate_before_test": registry["selected_research_candidate"],
        "champion_selected": False,
        "formal_training": False,
        "test_quality_exposed_now": True,
        "original_final_lab_test_opened": False,
        "enforcement_actions": 0,
        "lab_group_files": [f"lab-group{i}.json" for i in range(len(groups))],
        "public_results": "public-results.json",
        "limits": [
            "Selected on originalvalidation only, never choose winner from these exposedcohorts",
            "Newlab is one later time/samefixture and runnerintent labels, not independent humanreview",
            "SRBH is one WordPress Internetenvironment with publisher signature-assisted annotations, duplicate/conflicting identities and metadata anomalies;0formaladmission",
            "URI-only model cannot observe body/header/sequence attacks; do not infer XSS from generic CAPEC242",
            "Full source sample primary keeps provenance anomalies; sensitivity subsets are supplemental",
            "No rawquery, body, header, clientIP, familylabel or CAPEC/SID enters model tensors",
        ],
    }
    atomic_json(output / "report.json", result)
    return result


def benchmark_latency(registry_path, output):
    if Path(output).exists():
        raise PipelineError("Latency evidence already exists; use a new experiment output")
    registry = load_json(registry_path)
    results = {}
    sample = "/api/catalog?hint=reference%20documentation&page=2"
    with resource_envelope(4, 16):
        for name, entry in registry["models"].items():
            pipe = RequestInferencePipeline(entry["bundle"], 4)
            from idps_ai.features.request_view import project_request

            view = project_request(sample)
            x = np.asarray([encode_request(pipe.spec, view["numbers"])], np.float32)
            results[name] = {
                "max_threads": 4,
                "warm_batch1_model_only": latency_ms(
                    lambda a: pipe.session.run(None, {"input": a}), x
                ),
                "warm_batch1_envelope_encoding_onnx": latency_ms(pipe.predict_views, [view]),
                "warm_batch1_uri_privacy_encoding_onnx": latency_ms(pipe.observe_uri, sample),
                "scope": "Isolated after all fitting and scorejobs;100repeats5warmups; excludes capture/Web/network/TLS, not throughputSLO",
            }
    atomic_json(output, results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--real-data")
    parser.add_argument("--lab")
    parser.add_argument("--eve")
    parser.add_argument("--output", required=True)
    parser.add_argument("--latency-only", action="store_true")
    args = parser.parse_args()
    if args.latency_only:
        benchmark_latency(args.registry, args.output)
    else:
        run(args.registry, args.real_data, args.lab, args.eve, args.output)

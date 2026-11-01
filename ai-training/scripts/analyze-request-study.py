#!/usr/bin/env python3
"""Validation-only source/family/calibration audit; never accepts test partitions."""

import argparse
import json
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.request_inference import RequestInferencePipeline
from idps_ai.training.generalization import binary_metrics, calibration_audit
from idps_ai.training.resources import resource_envelope


def analyze(study, raw_dataset, encoded_dataset, output):
    study = load_json(study)
    if study.get("status") != "PASS_TECHNICAL_ONLY":
        raise PipelineError("Only completed fixed studies may enter validation selection")
    if Path(output).exists():
        raise PipelineError("Validation selection evidence must be new")
    datasets = {
        "affine70": Path(raw_dataset),
        "security45": Path(encoded_dataset),
        "bounded76": Path(encoded_dataset),
    }
    results = {}
    with resource_envelope(4, 16):
        for name, entry in study["models"].items():
            data = datasets[entry["encoding"]]
            rows = [
                r
                for r in iter_rows(data / "requests.parquet")
                if r["split"] == "val" and r["label"] is not None
            ]
            pipe = RequestInferencePipeline(entry["bundle"], 4)
            from idps_ai.features.request_view import PROFILE, fingerprint

            scores = np.concatenate(
                [
                    pipe.predict_views(
                        [
                            {
                                "profile": PROFILE,
                                "implementation_sha256": fingerprint(),
                                "numbers": json.loads(r["numeric_json"]),
                            }
                            for r in rows[i : i + 512]
                        ]
                    )
                    for i in range(0, len(rows), 512)
                ]
            )
            y = np.array([r["label"] for r in rows])
            threshold = pipe.manifest["threshold"]
            families = {}
            campaigns = {}
            for family in sorted({r["attack_family"] for r in rows if r["label"] == 1}):
                mask = np.array([r["attack_family"] == family and r["label"] == 1 for r in rows])
                families[family] = {
                    "requests": int(mask.sum()),
                    "recall": float(np.mean(scores[mask] >= threshold)),
                }
            for group in sorted({r["group_key"] for r in rows if r["source_id"] == "student-lab"}):
                mask = np.array(
                    [r["group_key"] == group and r["source_id"] == "student-lab" for r in rows]
                )
                campaigns[group] = binary_metrics(y[mask], scores[mask], threshold)
            by_source = {}
            for source in sorted({r["source_id"] for r in rows}):
                mask = np.array([r["source_id"] == source for r in rows])
                by_source[source] = {
                    "metrics": binary_metrics(y[mask], scores[mask], threshold),
                    "calibration": calibration_audit(y[mask], scores[mask]),
                }
            macro = float(np.mean([v["recall"] for v in families.values()]))
            worst = max(v["metrics"]["fpr"] for v in by_source.values())
            results[name] = {
                "bundle_manifest_sha256": file_sha256(
                    Path(entry["bundle"]) / "model_manifest.json"
                ),
                "validation": binary_metrics(y, scores, threshold),
                "by_source": by_source,
                "payload_family_recall": families,
                "lab_campaigns": campaigns,
                "macrofamily_recall": macro,
                "worst_source_fpr": worst,
                "eligible_empirical_1pct_budget": worst <= 0.01,
                "probability_calibration": calibration_audit(y, scores),
                "threshold_changed": False,
            }
    eligible = [n for n, v in results.items() if v["eligible_empirical_1pct_budget"]]
    selected = (
        max(
            eligible,
            key=lambda n: (
                results[n]["macrofamily_recall"],
                results[n]["validation"]["pr_auc_average_precision"],
            ),
        )
        if eligible
        else None
    )
    result = {
        "format_version": 1,
        "scope": "Validationonly, no quality test data read",
        "models": results,
        "selected_research_candidate": selected,
        "champion_selected": False,
        "selection_rule": "worstsourceFPR<=1%; maximize macrofamilyrecall then AP",
        "test_quality_opened": False,
        "temperature_note": "A strictly monotonic binarytemperature transform preserves score ranking and cannot improve recall at a recalibrated identical FPR operatingpoint. Not applied as a detection fix.",
    }
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", required=True)
    p.add_argument("--raw-dataset", required=True)
    p.add_argument("--encoded-dataset", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(json.dumps(analyze(a.study, a.raw_dataset, a.encoded_dataset, a.output), sort_keys=True))

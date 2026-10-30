#!/usr/bin/env python3
"""Frozen request-profile benchmark on the previously unopened publisher test.

Full original test is primary. Novel-view metrics are only supplemental; coarse
request labels include attacks whose body/header/context is not observable here.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from idps_ai.common import atomic_json, digest, file_sha256, load_json
from idps_ai.data.dataset import iter_rows
from idps_ai.data.request_corpus import read_pkdd, verify_requests
from idps_ai.features.request_view import PROFILE
from idps_ai.request_inference import RequestInferencePipeline
from idps_ai.training.deep import AUTOENCODERS
from idps_ai.training.generalization import binary_metrics
from idps_ai.training.resources import resource_envelope


def run(dataset, source, identity_key, bundles, output):
    manifest = verify_requests(dataset)
    if file_sha256(source) != "f1b79ffbe51b271a55545fb4caf1f4edd97e3514a835ade64f875245a9bb4116":
        raise ValueError("Publisher test hash mismatch")
    rows = list(read_pkdd(source, Path(identity_key).read_bytes()))
    if not rows or len(rows) > 100_000:
        raise ValueError("Public test count outside bounded benchmark")
    y = np.array([r["label"] for r in rows], np.int64)
    views = [{"profile": PROFILE, "numbers": r["numbers"]} for r in rows]
    from idps_ai.features.request_view import fingerprint

    for v in views:
        v["implementation_sha256"] = fingerprint()
    training = [
        r
        for r in iter_rows(Path(dataset) / "requests.parquet")
        if r["split"] == "train" and r["label"] is not None
    ]
    results = {}
    for name, path in bundles.items():
        model = RequestInferencePipeline(path, 4)
        if model.manifest["dataset_sha256"] != manifest["dataset_sha256"]:
            raise ValueError("Public test training-data binding mismatch")
        if model.manifest["model_kind"] in AUTOENCODERS:
            keys = {r["feature_key"] for r in training if r["label"] == 0}
        else:
            keys = {r["feature_key"] for r in training if r["source_id"] == "student-lab"}
        novel = np.array([digest(r["numbers"]) not in keys for r in rows])
        scores = np.concatenate(
            [model.predict_views(views[i : i + 512]) for i in range(0, len(rows), 512)]
        )
        threshold = model.manifest["threshold"]
        results[name] = {
            "bundle_manifest_sha256": file_sha256(Path(path) / "model_manifest.json"),
            "full_publisher_test": binary_metrics(y, scores, threshold),
            "novel_view_subset": binary_metrics(y[novel], scores[novel], threshold),
            "novel_view_rows": int(novel.sum()),
            "matching_training_views": int((~novel).sum()),
            "threshold_tuned_on_public_test": False,
        }
    report = {
        "status": "BENCHMARK_EXECUTED_NOT_PRODUCTION_ACCEPTANCE",
        "requests": len(rows),
        "benign": int((y == 0).sum()),
        "anomalous": int((y == 1).sum()),
        "source_sha256": file_sha256(source),
        "dataset_sha256": manifest["dataset_sha256"],
        "models": results,
        "champion_selected": False,
        "limits": [
            "Flattened repository mirror, not native XML: Context/inContext/attackIntervall missing",
            "Publisher class is request-level; URI-only view cannot necessarily see body/header attacks",
            "No family label guessed, no test examples used in fitting, calibration or hyperparameter choice",
            "Novel-view subset supplements the full unfiltered test; view collision is not proof of identical raw payload",
            "This test is now exposed; future feature/HPO work needs a new sealed challenge",
        ],
    }
    atomic_json(output, report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["dataset", "source", "identity-key", "bundles", "output"]:
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    with resource_envelope(4, 16):
        print(
            json.dumps(
                run(a.dataset, a.source, a.identity_key, load_json(a.bundles), a.output),
                sort_keys=True,
            )
        )

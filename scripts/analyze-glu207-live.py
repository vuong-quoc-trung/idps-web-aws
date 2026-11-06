#!/usr/bin/env python3
"""One paired post-hoc flow-missingness probe, not independent evaluation."""

import hashlib
import json
from pathlib import Path

import numpy as np
from idps_ai.common import file_sha256
from idps_ai.data.dataset import iter_rows
from idps_ai.data.privacy import pseudonym
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import FeatureExtractor, transform

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local-dev/three-source"


def main():
    out = BASE / "glu-flow-diagnostic.json"
    if out.exists():
        raise RuntimeError("Preserve diagnostic; choose a new version")
    rid = json.loads((BASE / "flow-watermark-receipt.json").read_text())["request_id"]
    records = [
        json.loads(l)
        for l in (ROOT / ".local-dev/foundation/glu207/results.jsonl")
        .read_text()
        .splitlines()
    ]
    recorded = next(r for r in records if r["request_id"] == rid)
    directory = next(
        p.parent
        for p in (BASE / "glu-live-1").glob("snapshot-*/feature-proof.json")
        if json.loads(p.read_text())["request_id"] == rid
    )
    key = (BASE / "glu-live-1/pseudonym-key.bin").read_bytes()
    target = pseudonym(key, "request", rid)
    spec_path = (
        ROOT
        / "ai-training/.artifacts/scale_upgrade_20261030/prepared-v5/feature_spec.json"
    )
    assert (
        file_sha256(spec_path)
        == "3f7fe0a8c53d9aacadd5bc4e6070fb1a0f6de2b6a0f4bf208d686e83b5c1c580"
    )
    spec = json.loads(spec_path.read_text())
    extractor = FeatureExtractor(**spec["state_limits"])
    for row in iter_rows(directory / "fused/requests.parquet"):
        if row["request_key"] == target:
            break
        extractor.observe(row)
    actual = transform(spec, extractor.observe(row))
    assert (
        hashlib.sha256(actual.tobytes()).hexdigest()
        == recorded["glu"]["feature_sha256"]
    )
    other = FeatureExtractor(**spec["state_limits"])
    for before in iter_rows(directory / "fused/requests.parquet"):
        if before["request_key"] == target:
            break
        other.observe(before)
    masked_row = dict(
        row, flow_json=json.dumps({k: None for k in json.loads(row["flow_json"])})
    )
    masked = transform(spec, other.observe(masked_row))
    onnx = (
        ROOT
        / "ai-training/.artifacts/research_glu207_bounded_final_20261104/research-final.onnx"
    )
    assert (
        file_sha256(onnx)
        == "724692e045dc3a306f27926ef46bd114d8073b93b894812225dd9968c1cd2b14"
    )
    scores, _ = cpu_session(onnx, 1).run(None, {"input": np.stack([actual, masked])})
    assert abs(float(scores[0]) - recorded["glu"]["score"]) < 1e-6
    result = {
        "scope": "Exposed controlled probe, paired counterfactual only. Not an observed missing-flow request, not new evaluation or Ground Truth. No threshold selection.",
        "request_id": rid,
        "actual_score": float(scores[0]),
        "counterfactual_prior_flow_missing_score": float(scores[1]),
        "frozen_threshold": 0.5396780371665955,
        "changed_features": [
            n for n, a, b in zip(spec["columns"], actual, masked) if a != b
        ],
        "source_flow_observed": recorded["glu"]["flow_observed"],
        "rule_context_columns": [
            n for n in spec["columns"] if n.startswith("context_suricata_")
        ],
        "raw_training_dataset_changed": False,
    }
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Offline restored-weight checks and frozen ORT/request contract smoke, no fit."""

import importlib.util
import json
import os
from pathlib import Path

for variable in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[variable] = "1"

import numpy as np
from idps_ai.common import AI_ROOT, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import (
    FeatureExtractor,
    implementation_fingerprint,
    transform,
)
from idps_ai.mvp_inference import (
    GLU_ROOT,
    GLU_SPEC,
    GLU_THRESHOLD,
    ResearchMVP,
    validate_fused,
)
from idps_ai.training.checkpoint import validate_generation

ROOT = Path(__file__).resolve().parents[1]
fixtures = load_json(ROOT / "release/smoke-input.json")
expected = load_json(ROOT / "release/smoke-expected.json")
frozen = load_json(AI_ROOT / "RESEARCH_MVP_V1_0_FROZEN.json")
for name in ["glu207", "request_intelligence_v2"]:
    config = frozen["models"][name]
    for relative, sha in config["checkpoint_files_sha256"].items():
        if file_sha256(ROOT / relative) != sha:
            raise RuntimeError("Frozen checkpoint checksum mismatch")
    validate_generation(ROOT / config["checkpoint_path"])
spec = load_json(GLU_SPEC)
if spec["implementation_sha256"] != implementation_fingerprint():
    raise RuntimeError("Frozen encoder changed")
for path, checksum in [
    (GLU_ROOT / "research-final.onnx", frozen["models"]["glu207"]["onnx_sha256"]),
    (GLU_SPEC, frozen["models"]["glu207"]["feature_spec_sha256"]),
    (GLU_THRESHOLD, frozen["models"]["glu207"]["threshold_manifest_sha256"]),
]:
    if file_sha256(path) != checksum:
        raise RuntimeError("Frozen ONNX/spec/threshold mismatch")
session = cpu_session(GLU_ROOT / "research-final.onnx", 1)
extractor = FeatureExtractor(**spec["state_limits"])
request = ResearchMVP("request-v2", cpus=1)
seen = []
for row in fixtures:
    if row.get("http_request"):
        result = request.predict(row)["models"]["request_intelligence_v2"]
        reference = expected["request_intelligence_v2"][row["record_id"]]
        if result["score"] != reference:
            raise RuntimeError("Request native smoke score differs")
        seen.append(
            {
                "record_id": row["record_id"],
                "model": "request_intelligence_v2",
                "score": result["score"],
            }
        )
    if row.get("fused_request"):
        validate_fused(row["fused_request"])
        vector = transform(spec, extractor.observe(row["fused_request"]))
        score = float(session.run(None, {"input": vector[None, :]})[0][0])
        reference = expected["glu207"][row["record_id"]]
        if not np.isclose(score, reference, atol=1e-6, rtol=1e-5):
            raise RuntimeError("GLU ONNX smoke score differs")
        seen.append({"record_id": row["record_id"], "model": "glu207", "score": score})
report = {
    "status": "PASS_OFFLINE_TWO_MODEL_RESTORE",
    "observed": seen,
    "training_updates": 0,
    "network_calls": 0,
    "GLU_runtime": "frozen ONNX graph plus exact frozen preprocessor; optimizer state verified but not instantiated",
    "source_fixture": "pseudonymized derivative, technical smoke only; no quality claim",
}
study_root = AI_ROOT / ".artifacts/integration_candidate_20261105/study"
if (study_root / "plan.json").exists():
    module_spec = importlib.util.spec_from_file_location(
        "restored_study", AI_ROOT / "scripts/integration-request-study.py"
    )
    study = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(study)
    _, plan = study.read_plan(study_root)
    if file_sha256(study.DATASET) != plan["dataset_original_sha256"]:
        raise RuntimeError("Restored research tensor checksum mismatch")
    generations = list(study_root.parent.glob("*/checkpoints/step-*"))
    for generation in generations:
        validate_generation(generation)
    report["request_training_material"] = {
        "status": "RESTORED_HASHES_SOURCE_ENV_AND_GENERATIONS_VERIFIED",
        "plan_sha256": plan["plan_sha256"],
        "checkpoint_generations_checked": len(generations),
        "training_updates": 0,
        "new_exact_resume_test": False,
    }
state = ROOT / ".team-state"
state.mkdir(exist_ok=True, mode=0o700)
(state / "model-smoke-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))

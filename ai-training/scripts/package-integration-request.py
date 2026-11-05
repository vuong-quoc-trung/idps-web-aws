#!/usr/bin/env python3
"""Build portable shadow bundle from the precommitted one-candidate decision."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import onnx
from threadpoolctl import threadpool_limits

from idps_ai.common import AI_ROOT, PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.features.request_preprocessing import bounded_spec
from idps_ai.training.checkpoint import load_checkpoint


def package(study, run, evidence, output, research_only=False):
    study, run, evidence, output = [Path(p).resolve() for p in [study, run, evidence, output]]
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    decision = load_json(evidence / "evaluation-report.json")
    if decision["selection"] == "FROZEN_REQUEST_V2" and not research_only:
        selected = load_checkpoint(
            AI_ROOT / ".artifacts/request_intelligence_v2_20261104/run/model"
        )
        threshold = 0.8826237916946411
        version = "request-intelligence-v2-frozen-step3072"
        source_threshold = (
            AI_ROOT / ".artifacts/request_intelligence_v2_20261104/run/threshold-manifest.json"
        )
        resume = "INFERENCE_ONLY_FOR_SELECTED_FROZEN_REQUEST_V2; historical same-process roundtrip does not prove training interruption resume"
    else:
        selected = load_checkpoint(run)
        threshold = decision["candidate_threshold"]
        version = "request-intelligence-v2-numeric-mask-p025-step3072"
        source_threshold = evidence / "threshold.json"
        resume = "RESUME_EXACT prefix128 verified by three fresh processes; main run resumed across256/1024/3072; frozen3072 target terminal"
    shutil.copytree(
        AI_ROOT / "src/idps_ai",
        output / "python/idps_ai",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(selected.path, output / "checkpoint")
    shutil.copy2(AI_ROOT / "scripts/integration-request-infer.py", output / "infer.py")
    shutil.copy2(AI_ROOT / "requirements.txt", output / "requirements.lock.txt")
    shutil.copy2(source_threshold, output / "threshold-source.json")
    shutil.copy2(evidence / "evaluation-report.json", output / "evaluation-evidence.json")
    shutil.copy2(study / "plan.json", output / "new-training-plan-evidence.json")
    atomic_json(
        output / "feature-contract.json",
        {
            "features": 588,
            "numeric": bounded_spec(),
            "content": {
                "encoder": "rich_content_v2",
                "hashing": "char3–5 nonnegative512 L2float32",
            },
            "inference_augmentation": False,
            "frozen_encoder_unchanged": True,
            "availability_caveat": "Header/body absence may share tensors with empty content; rich and numeric privacy filtering differ; availability is descriptive.",
        },
    )
    graph = graph_for(selected.model)
    onnx.checker.check_model(graph)
    onnx.save(graph, output / "model.onnx")
    train = np.load(study / "train.npy", mmap_mode="r", allow_pickle=False)
    sample = np.asarray(
        train[np.random.default_rng(84).choice(len(train), 128, replace=False)], np.float32
    )
    with threadpool_limits(limits=1):
        native = selected.model.predict(sample)
        session = cpu_session(output / "model.onnx", 1)
        exported = session.run(None, {"input": sample})
    if not all(
        np.allclose(a, b, rtol=1e-5, atol=1e-6) for a, b in zip(native, exported, strict=True)
    ):
        raise PipelineError("Selected model ONNX parity failed")
    atomic_json(
        output / "onnx-parity.json",
        {
            "status": "PASS",
            "rows": len(sample),
            "scope": "technical train-sample parity, not evaluation",
            "score_max_abs_error": float(np.max(abs(native[0] - exported[0]))),
            "probability_max_abs_error": float(np.max(abs(native[1] - exported[1]))),
            "rtol": 1e-5,
            "atol": 1e-6,
        },
    )
    sample_requests = [
        {
            "record_id": "health",
            "schema_version": "integration-request-1",
            "http_request": {
                "method": "GET",
                "url": "/api/health",
                "headers": "Accept: application/json",
                "body": "",
            },
        },
        {
            "record_id": "search",
            "schema_version": "integration-request-1",
            "http_request": {
                "method": "GET",
                "url": "/catalog?q=C%2B%2B",
                "headers": None,
                "body": None,
            },
        },
        {
            "record_id": "json",
            "schema_version": "integration-request-1",
            "http_request": {
                "method": "POST",
                "url": "/api/search",
                "headers": "Content-Type: application/json",
                "body": '{"query":"example"}',
            },
        },
        {
            "record_id": "syntax-probe",
            "schema_version": "integration-request-1",
            "http_request": {
                "method": "GET",
                "url": "/catalog?q=%3Cscript%3Evoid(1)%3C%2Fscript%3E",
                "headers": "Accept: text/html",
                "body": "",
            },
        },
    ]
    with (output / "sample-input.jsonl").open("x") as stream:
        for row in sample_requests:
            stream.write(json.dumps(row) + "\n")
    (output / "README.md").write_text(f"""# Local request shadow integration bundle

Bundled model: {version}. Threshold: score > {threshold!r}.
Bundle role: {"UNSELECTED_RESEARCH_ARTIFACT; do not use as default demo model" if research_only else "SELECTED_SHADOW_DEMO"}.
Selection decision: {decision["selection"]}. The separately trained numeric-mask candidate did not automatically replace the frozen baseline.

Create a Python3.12 virtual environment and install `requirements.lock.txt` with standard pip, then:

    /path/to/venv/bin/python -I infer.py --input sample-input.jsonl --output NEW-output.jsonl

No repository checkout, existing .artifacts path, network service or training dataset is required for inference. A cold process verifies bundle checksums then loads once. For a local worker, import RequestPredictor from infer.py, construct it once with this bundle path, and call predict(record) sequentially. Do not create a process for each request in a sustained worker.

Input: JSONL, schema_version=integration-request-1 (research-mvp-1 accepted), opaque unique record_id, http_request{{method,url,headers,body}}. headers/body are strings or null; URLs/headers/body <=8192 chars. Output: per-request score, strict-greater research flag, model/encoder version, availability. combined_score=null and enforcement_actions=0. Invalid input rejects the batch atomically, leaves no output; existing output is never overwritten.

This is request-only shadow inference. No actor/session/response/flow/historical207 features are invented. Send allowed request observations after TLS termination through an integration-owned bounded queue, including rule-negative traffic. Own timeout/backpressure/restart and metrics in the integration branch. This CLI is a finite batch prototype, not a hardened HTTP server. Raw cookies/credentials remain private, and must not enter logs or public outputs. Hash features are not anonymization guarantees.

The source publisher NORMAL/ANOMALOUS labels are not verified attack Ground Truth. Scores are rankings, not calibrated attack probabilities. Domain shift and known XSS/command misses persist; no production Recall/FPR or AI-only blocking is authorized. GLU207 remains a separate frozen baseline requiring its complete three-source post-response contract.

Training status for the selected model: {resume}. The new augmentation run has its own checkpoint, plan and exact-resume evidence outside this inference bundle; do not resume the selected baseline using the new trainer. Restoring the new research run requires the separate recovery kit and hashed curated train material. Same-version CPU arithmetic is required for exact resume; cross-hardware bitwise equality is not promised.

Files: native checkpoint (parameters/Adam metadata), original encoder Python sources, fixed feature contract, original threshold provenance, optional ONNX tensor graph and parity evidence, dependencies, evaluation decision and sample input. ONNX takes preprocessed float32[N,588]; infer.py additionally performs preprocessing. Manifest checksums detect accidental corruption, not malicious re-signing.
""")
    files = {str(p.relative_to(output)): file_sha256(p) for p in output.rglob("*") if p.is_file()}
    manifest = {
        "format_version": 1,
        "model_version": version,
        "selection": decision["selection"],
        "bundle_role": "UNSELECTED_RESEARCH" if research_only else "SELECTED_SHADOW_DEMO",
        "checkpoint_source_sha256": file_sha256(selected.path / "manifest.json"),
        "threshold": threshold,
        "score_rule": "score > threshold",
        "features": 588,
        "parameters": 50696,
        "shadow_only": True,
        "enforcement_actions": 0,
        "resume_status": resume,
        "files_sha256": files,
    }
    manifest["manifest_sha256"] = digest(manifest)
    atomic_json(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "bundle": str(output),
                "selected_model": version,
                "files": len(files),
                "manifest_sha256": file_sha256(output / "manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--research-only", action="store_true")
    a = p.parse_args()
    package(a.study, a.run, a.evidence, a.output, a.research_only)

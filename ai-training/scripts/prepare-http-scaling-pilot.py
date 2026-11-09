#!/usr/bin/env python3
"""Create a fresh private lock/key for the fixed10K pilot; never overwrite controls.

Requires authorized local source artifacts. Reuse a privately retained key to
reproduce opaque identifiers. Does not ingest, score, train or contact a server.
Run under integration-guard, then use scale-http-admission.py on a fresh output.
Historical r2 used the preserved private preparation snapshot, not this helper.
"""

import argparse
import os
from pathlib import Path

from idps_ai.common import PipelineError, atomic_json, digest, file_sha256, load_json
from idps_ai.data.http_curation import require_development_source

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = ROOT / ".local-dev/data-scaling-20261109"


def prepare(existing_key=None):
    if CONTROLS.exists():
        raise PipelineError(
            "Controls already exist; preserve historical lock/key, do not overwrite"
        )
    policy = ROOT / "ai-training/configs/research/http-scaling-admission-20261109.json"
    waf = ROOT / "ai-training/.artifacts/autonomous_research_20261104/waf_v2/train.parquet"
    oracle = ROOT / "ai-training/.artifacts/request_v3_acquisition_final_20261108/release-v2"
    for p in (waf, oracle):
        require_development_source(p)
        if p.is_symlink():
            raise PipelineError("Pilot source symlinks forbidden")
    expected = "3e1f8bc6e3acfccf87218fc9e5272ff2218e808d7686c6ce461335c00a7a3fd6"
    if file_sha256(waf) != expected:
        raise PipelineError("Fixed WAF source checksum mismatch")
    manifest = load_json(oracle / "materialization-report.json")
    if manifest["dataset_fingerprint"] != (
        "f6aa5b60b0c7d0291dfa123fe82a8e0870bb9fbacd36ac6eb27f3d6e9dfae22f"
    ):
        raise PipelineError("Fixed Oracle release mismatch")
    for name, sha in manifest["files_sha256"].items():
        if file_sha256(oracle / name) != sha:
            raise PipelineError("Oracle derivative checksum mismatch")
    key = Path(existing_key).read_bytes() if existing_key else os.urandom(32)
    if len(key) != 32:
        raise PipelineError("Private admission key must be exactly32bytes")
    code = [
        "ai-training/scripts/scale-http-admission.py",
        "ai-training/src/idps_ai/data/scaling_admission.py",
        "ai-training/src/idps_ai/features/request_v3.py",
        "ai-training/src/idps_ai/features/body_syntax_v1.py",
        "ai-training/src/idps_ai/features/rich_content_v2.py",
        "ai-training/src/idps_ai/features/rich_content.py",
        "ai-training/src/idps_ai/features/request_preprocessing.py",
        "ai-training/src/idps_ai/features/request_view.py",
        "ai-training/scripts/prepare-http-scaling-pilot.py",
    ]
    CONTROLS.mkdir(parents=True, mode=0o700)
    keypath = CONTROLS / "identity.key"
    # Exclusive0600 write; refuse races and never print private key material.
    with keypath.open("xb") as out:
        keypath.chmod(0o600)
        out.write(key)
        out.flush()
        os.fsync(out.fileno())
    lock = {
        "schema": "http-scale-pilot-lock-1",
        "policy_sha256": file_sha256(policy),
        "code_sha256": {p: file_sha256(ROOT / p) for p in code},
        "key_fingerprint": file_sha256(keypath),
        "source_sha256": {
            "waf_train": expected,
            "oracle_manifest": file_sha256(oracle / "materialization-report.json"),
        },
        "candidate_positions": 10000,
        "first_process_stop": 2500,
        "resume_to": 10000,
        "scope": "fresh reproduction only; preserve historical runs; no scores/training/sealed",
    }
    lock["fingerprint"] = digest(lock)
    atomic_json(CONTROLS / "pilot-lock.json", lock)
    print("PRIVATE_PILOT_LOCK_CREATED; no requests ingested or training started")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--existing-key", type=Path, help="Authorized local private key; never a chat token"
    )
    args = p.parse_args()
    prepare(args.existing_key)

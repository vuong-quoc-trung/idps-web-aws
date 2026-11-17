"""Stage and verify the R21 handoff as a relocatable inference bundle."""

import argparse
import os
import shutil
from pathlib import Path

from evidence import read, require

from idps_ai.common import REPO_ROOT, atomic_json, file_sha256
from idps_ai.features.request_time import schema

HANDOFF = REPO_ROOT / "ai-training/contracts/development-bulk-v1/r21-shadow-handoff.json"
ONNX = "1a709dcf1ccfa880c3b4b55b77c0699ac10c27fd4ecdd2839bedeb99e1987525"
CHECKPOINT = "0ed456322141181d93b068e2555285f6455e6cad45c9c4856f1bb01b0bd296c0"
SCOPE = "4969c162ccf1dcfb10c56c6a9f9f16b45b01475e32c6938ec3e194a9396a57b0"
RUST = "72f830f324987e56848efed6a954e4980b0d266e116aedd1272bf1be1bae78e4"


def verify(root):
    paths = {
        name: root / name
        for name in (
            "swiglu.onnx",
            "model-scope.json",
            "checkpoint-manifest.json",
            "deployment.json",
        )
    }
    for name, sha in (
        ("swiglu.onnx", ONNX),
        ("model-scope.json", SCOPE),
        ("checkpoint-manifest.json", CHECKPOINT),
    ):
        path = paths[name]
        require(
            path.is_file() and not path.is_symlink() and file_sha256(path) == sha,
            f"Invalid bundle member {name}",
        )
    scope = read(paths["model-scope.json"])
    handoff = read(HANDOFF)
    candidate = handoff["candidate"]
    require(
        candidate["onnx"]["sha256"] == ONNX
        and candidate["checkpoint"]["sha256"] == CHECKPOINT
        and candidate["manifest"]["sha256"] == SCOPE
        and handoff["hybrid_allowed"] is False
        and handoff["release_ready"] is False
        and scope["research_only"] is True
        and scope["hybrid_allowed"] is False
        and scope["native_source_mask"] is None
        and scope["scope"] == candidate["scope"]
        and scope["schema"] == schema()
        and scope["models"]["swiglu"] == ONNX
        and scope["tuning_calibration"]["method"] == "isotonic"
        and scope["tuning_calibration"]["comparator"] == candidate["threshold"]["comparator"]
        and scope["tuning_calibration"]["threshold"] == candidate["threshold"]["value"],
        "Inconsistent shadow manifest, schema or calibration",
    )
    config = {
        "schema_version": "idps-local-shadow-r22-v1",
        "serving_model": handoff["serving_model"],
        "shadow": {"slot": "swiglu", "mode": "research_shadow", "hybrid_allowed": False},
        "pins": {
            "swiglu.onnx": ONNX,
            "model-scope.json": SCOPE,
            "checkpoint-manifest.json": CHECKPOINT,
        },
        "rollback": "DISABLE_SHADOW_KEEP_RI_V2",
    }
    require(
        not paths["deployment.json"].is_symlink() and read(paths["deployment.json"]) == config,
        "Wrong local shadow deployment config",
    )
    return scope


def stage(target):
    handoff = read(HANDOFF)
    target.mkdir(mode=0o700)
    for key, name, pin in (
        ("onnx", "swiglu.onnx", ONNX),
        ("manifest", "model-scope.json", SCOPE),
        ("checkpoint", "checkpoint-manifest.json", CHECKPOINT),
    ):
        source = REPO_ROOT / handoff["candidate"][key]["path"]
        require(
            handoff["candidate"][key]["sha256"] == pin
            and not source.is_symlink()
            and file_sha256(source) == pin,
            f"Wrong handoff digest for {key}",
        )
        shutil.copyfile(source, target / name)
    atomic_json(
        target / "deployment.json",
        {
            "schema_version": "idps-local-shadow-r22-v1",
            "serving_model": handoff["serving_model"],
            "shadow": {"slot": "swiglu", "mode": "research_shadow", "hybrid_allowed": False},
            "pins": {
                "swiglu.onnx": ONNX,
                "model-scope.json": SCOPE,
                "checkpoint-manifest.json": CHECKPOINT,
            },
            "rollback": "DISABLE_SHADOW_KEEP_RI_V2",
        },
    )
    return verify(target)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    (stage if args.action == "stage" else verify)(args.directory)

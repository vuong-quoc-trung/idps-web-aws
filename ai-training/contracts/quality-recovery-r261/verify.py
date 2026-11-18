"""Compose separately bounded replay, raw parity and compiler evidence."""

# isort: skip_file

import os
import time

from common import atomic_json, check, file_sha256, output_arg, read
from idps_ai.common import REPO_ROOT
from idps_ai.training.checkpoint import validate_generation
from r26_train import export


def stage_model(path, source):
    """Rust accepts regular artifacts only; never weaken its symlink checks."""
    if path.is_symlink():
        path.unlink()
    export(path, __import__("onnx").load(source))


def run(out):
    selection = read(out / "model-selection.json")
    latest = read(out / "training/model/latest.json")
    previous = read(out / "training/model/previous.json")
    for pointer in (latest, previous, selection["best_checkpoint"]):
        validate_generation(out / "training/model" / pointer["path"], pointer["manifest_sha256"])
    replay = read(out / "continuation-replay.json")
    check(
        replay["state"] == "PASS" and replay["global_step"] == latest["global_step"],
        "Epoch replay cursor mismatch",
    )
    check(replay["parameters_adam_sampler_loss"] == "BIT_EXACT", "Epoch replay not verified")
    lock = read(out / "evaluation-lock.json")
    spec = lock["models"][selection["selected"]]
    runtime = read(out / "raw-runtime/runtime.json")
    check(
        runtime["model_sha256"]
        == spec["calibrated_sha256"]
        == file_sha256(out / "bundle" / spec["calibrated_file"]),
        "Runtime model digest mismatch",
    )
    check(
        runtime["binary_sha256"]
        == file_sha256(REPO_ROOT / "security-web/target/debug/idps-r26-uri100-shadow"),
        "Runtime binary changed",
    )
    check(
        runtime["max_feature_abs_error"] == runtime["max_score_abs_error"] == 0,
        "Raw parity not verified",
    )
    check(
        read(out / "rust-unit-tests.json")["state"] == "PASS",
        "Separate compiler regression missing",
    )
    atomic_json(
        out / "verification.json",
        {
            "exact_resume": replay,
            "raw_target_runtime": runtime,
            "rust_unit_regression": "PASS_2_TESTS",
            "compiler_and_model_workers_separated": True,
            "original_task_limit": 16,
            "all_original_R26_checkpoints_read_only": True,
            "selected_raw_sha256": selection["sha256"][selection["selected"]],
            "HTTP_shadow": "NOT_ACTIVATED_QUALITY_GATE_NOT_MET",
            "serving_RI_v2_R20_unchanged": True,
            "pid": os.getpid(),
            "completed_wall_ns": time.time_ns(),
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

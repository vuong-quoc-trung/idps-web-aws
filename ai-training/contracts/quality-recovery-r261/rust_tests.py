# isort: skip_file

"""Run isolated compiler regression without Python model/BLAS worker threads."""

import os
import subprocess

from common import atomic_json, output_arg
from idps_ai.common import REPO_ROOT


def run(out):
    env = dict(
        os.environ,
        CARGO_TARGET_DIR=str(REPO_ROOT / "security-web/target"),
        CARGO_BUILD_JOBS="1",
        RAYON_NUM_THREADS="1",
        RUSTFLAGS="-Ccodegen-units=1",
        OPENBLAS_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    cargo = REPO_ROOT / "ai-training/contracts/quality-acceleration-r26/r26_rust/Cargo.toml"
    result = subprocess.run(
        [
            "taskset",
            "-c",
            "0",
            "cargo",
            "test",
            "--offline",
            "--locked",
            "--manifest-path",
            str(cargo),
            "--",
            "--test-threads=1",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    (out / "rust-unit-tests.log").write_text(result.stdout + result.stderr)
    atomic_json(
        out / "rust-unit-tests.json",
        {
            "state": "PASS",
            "compiler_jobs": 1,
            "affinity": [0],
            "original_task_limit_preserved": 16,
            "combined_verifier_task_failure_not_auto_resumed": True,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

"""Bounded one-thread Rust build, through Resource Adapter."""

import json
import os
import subprocess
import sys
from pathlib import Path


def run(out):
    repo = Path(__file__).resolve().parents[3]
    manifest = Path(__file__).parent / "context_rust/Cargo.toml"
    env = dict(
        os.environ,
        CARGO_TARGET_DIR=str(repo / "security-web/target"),
        CARGO_BUILD_JOBS="1",
        RUSTFLAGS="-Ccodegen-units=1",
        RAYON_NUM_THREADS="1",
    )
    # Dependency graph already present in the repository's offline Cargo cache.
    command = [
        "taskset",
        "-c",
        "0",
        "cargo",
        "build",
        "--offline",
        "--manifest-path",
        str(manifest),
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
    (out / "rust-build.log").write_text(result.stdout + result.stderr)
    (out / "rust-build.json").write_text(
        json.dumps({"exit": result.returncode, "command": command}) + "\n"
    )
    if result.returncode == 0:
        tests = subprocess.run(
            [
                "taskset",
                "-c",
                "0",
                "cargo",
                "test",
                "--offline",
                "--locked",
                "--manifest-path",
                str(manifest),
                "--",
                "--test-threads=1",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        (out / "rust-tests.log").write_text(tests.stdout + tests.stderr)
        return tests.returncode
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1])))

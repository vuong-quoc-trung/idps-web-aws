"""Verify effective BLAS threads and cgroup limits through the final Adapter."""

# isort: skip_file

import os
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_info

from common import atomic_json, check, output_arg, read
from idps_ai.training.checkpoint import load_checkpoint
from r18_train import WeightedSwiGLU


def run(out):
    attempt = Path(os.environ["IDPS_RESOURCE_ATTEMPT"])
    proof = read(attempt / "preflight.json")
    check(proof["limits"]["cpu.max"] == "400000 100000", "Final allocation kernel quota mismatch")
    check(
        os.environ["OPENBLAS_NUM_THREADS"] == "4",
        "Start barrier silently replaced reviewed threads",
    )
    pools = threadpool_info()
    check(
        all(p["num_threads"] == 4 for p in pools if p["user_api"] == "blas"),
        "Effective BLAS pool not four threads",
    )
    root = out / "training/model"
    selected = read(root / "best.json")
    saved = load_checkpoint(root / selected["path"])
    model = WeightedSwiGLU.from_arrays(saved.model.metadata(), saved.model.arrays())
    x = np.random.default_rng(2611).random((2048, 100), dtype=np.float32)
    y = np.arange(2048, dtype=np.int8) % 2
    model.train_original_batch(x, y, np.ones(2048), 0.0001)
    began = time.perf_counter()
    for _ in range(8):
        model.train_original_batch(x, y, np.ones(2048), 0.0001)
    elapsed = time.perf_counter() - began
    atomic_json(
        out / "final-allocation.json",
        {
            "state": "PASS",
            "kernel_limits": proof["limits"],
            "BLAS_environment": {
                name: os.environ[name]
                for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
            },
            "actual_thread_pools": pools,
            "scratch_update_seconds": elapsed,
            "scratch_updates": 8,
            "scratch_parameters_discarded": True,
            "production_checkpoint_modified": False,
            "earlier_continuation_actual_threads": read(out / "continuation-plan.json")["threads"],
            "root_cause_fixed": "Legacy start barrier hardcoded thread env=1 regardless of parent env or reviewed quota",
            "completed_training_not_repeated": True,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

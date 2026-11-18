# isort: skip_file

"""Bounded BLAS scaling on the exact checkpoint architecture, no data fitting."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from common import HERE, PARENT, atomic_json


def worker(threads):
    import numpy as np
    from r18_train import WeightedSwiGLU
    from idps_ai.training.checkpoint import load_checkpoint

    saved = load_checkpoint(PARENT / "augmentation-b/training/model")
    model = WeightedSwiGLU.from_arrays(saved.model.metadata(), saved.model.arrays())
    random = np.random.default_rng(2601)
    x = random.random((2048, 100), dtype=np.float32)
    y = np.arange(len(x), dtype=np.int8) % 2
    weights = np.ones(len(x), np.float64)
    model.train_original_batch(x, y, weights, 0.0001)
    began = time.perf_counter()
    for _ in range(8):
        model.train_original_batch(x, y, weights, 0.0001)
    print(
        json.dumps(
            {
                "threads": threads,
                "steps": 8,
                "seconds": time.perf_counter() - began,
                "checkpoint_model_width": 100,
                "params": sum(v.size for v in model.parameters.values()),
            }
        )
    )


def run(out):
    results = []
    for threads in (1, 2, 4):
        env = dict(
            os.environ,
            OPENBLAS_NUM_THREADS=str(threads),
            OMP_NUM_THREADS=str(threads),
            MKL_NUM_THREADS=str(threads),
        )
        result = subprocess.run(
            [sys.executable, "-B", str(HERE / "benchmark.py"), str(out), "--threads", str(threads)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        record = json.loads(result.stdout)
        record["useful_steps_per_second"] = 8 / record["seconds"]
        results.append(record)
    selected = min(results, key=lambda record: (record["seconds"], record["threads"]))
    atomic_json(
        out / "compute-benchmark.json",
        {
            "arms": results,
            "selected_threads": selected["threads"],
            "selection": "Minimum actual 8-update time, synthetic fixture only, no model selection or new training run",
            "fit_batch_unchanged": 2048,
            "max_tested_cpu_cores": 4,
            "configured_memory_gib": 4,
            "parameter_updates_discarded": True,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--threads", type=int)
    args = parser.parse_args()
    if args.threads:
        worker(args.threads)
    else:
        run(args.out)

#!/usr/bin/env python3
"""Matched calibration budgets and batch1 CPU thread sweep on development val."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.export.onnx import cpu_session
from idps_ai.training.evaluation import threshold_at_fpr
from idps_ai.training.generalization import binary_metrics
from idps_ai.training.protocol import validation_groups
from idps_ai.training.resources import cgroup_readback, resource_envelope


def run(dataset, bundles, output, threads=(1, 2, 4, 8), repeats=100):
    manifest = verify_dataset(dataset, "prepared")
    calibration, selection = [], []
    if manifest.get("rows", {}).get("calibration"):
        for row in iter_rows(Path(dataset) / "features.parquet"):
            if row["split"] == "calibration":
                calibration.append(row)
            elif row["split"] == "val":
                selection.append(row)
    else:
        rows = [r for r in iter_rows(Path(dataset) / "features.parquet") if r["split"] == "val"]
        protocol = validation_groups(dataset)
        calibration = [rows[i] for i in protocol["calibration_indices"]]
        selection = [rows[i] for i in protocol["selection_indices"]]
    cx, vx = (np.array([r["x"] for r in rs], np.float32) for rs in (calibration, selection))
    cy, vy = (np.array([r["label"] for r in rs], np.int64) for rs in (calibration, selection))
    result = {
        "dataset_sha256": manifest["dataset_sha256"],
        "calibration_rows": len(cy),
        "selection_rows": len(vy),
        "test_quality_opened": False,
        "models": {},
        "cgroup": cgroup_readback(),
        "scope": "Development only; equal empirical calibration FPR budgets; CPU batch1 model-only thread sweep, no throughput/SLO claim",
    }
    for name, path in bundles.items():
        path = Path(path)
        card = load_json(path / "model_manifest.json")
        if (
            card["dataset_sha256"] != manifest["dataset_sha256"]
            or file_sha256(path / "model.onnx") != card["files"]["model.onnx"]
        ):
            raise PipelineError("Operating-point comparison candidate/dataset mismatch")
        session = cpu_session(path / "model.onnx", 1)

        def scores(x, session):
            return np.concatenate(
                [session.run(None, {"input": x[i : i + 512]})[0] for i in range(0, len(x), 512)]
            )

        cs, vs = scores(cx, session), scores(vx, session)
        operating = {}
        for budget in (0.001, 0.005, 0.01):
            calibration_result = threshold_at_fpr(cy, cs, budget)
            calibration_result["fit_partition"] = "calibration_campaign_groups"
            operating[str(budget)] = {
                "calibration": calibration_result,
                "selection": binary_metrics(vy, vs, calibration_result["threshold"]),
            }
        baseline = session.run(None, {"input": vx[: min(16, len(vx))]})
        del session
        latency = {}
        for count in threads:
            session = cpu_session(path / "model.onnx", count)
            for a, b in zip(baseline, session.run(None, {"input": vx[: min(16, len(vx))]})):
                np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6)
            for i in range(10):
                session.run(None, {"input": vx[i % len(vx) : i % len(vx) + 1]})
            times = []
            for i in range(repeats):
                sample = vx[i % len(vx) : i % len(vx) + 1]
                start = time.perf_counter_ns()
                session.run(None, {"input": sample})
                times.append((time.perf_counter_ns() - start) / 1e6)
            latency[str(count)] = dict(
                zip(("p50", "p95", "p99"), map(float, np.percentile(times, [50, 95, 99])))
            )
            del session
        result["models"][name] = {
            "bundle_manifest_sha256": file_sha256(path / "model_manifest.json"),
            "operating_points": operating,
            "threads_batch1_latency_ms": latency,
            "lowest_measured_p95_threads": int(min(latency, key=lambda k: latency[k]["p95"])),
        }
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--bundles", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--thread-counts", type=int, nargs="+", choices=(1, 2, 4, 8), default=[1, 2, 4, 8]
    )
    parser.add_argument("--repeats", type=int, choices=range(20, 501), default=100)
    args = parser.parse_args()
    with resource_envelope(8, 16):
        print(
            json.dumps(
                run(
                    args.dataset,
                    load_json(args.bundles),
                    args.output,
                    args.thread_counts,
                    args.repeats,
                ),
                sort_keys=True,
            )
        )

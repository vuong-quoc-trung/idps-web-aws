# isort: skip_file

"""Read-only B16 integrity, matched TUNING and exact numerical resume audit."""

import os
import time

import numpy as np

from common import HERE, PARENT, atomic_json, check, file_sha256, output_arg, read
from idps_ai.common import digest
from idps_ai.export.onnx import cpu_session, graph_for
from idps_ai.training.checkpoint import load_checkpoint, validate_generation
from r16_train import batched_predict
from r18_train import WeightedSwiGLU
from r26_learning import assessment, epoch, make_training
from r26_recovery_pilot import data
from r26_train import export


def run(out):
    began = time.monotonic()
    source = PARENT / "augmentation-b"
    plan = read(source / "training-plan.json")
    for name, key in (
        ("r26_recovery_train.py", "code_sha256"),
        ("r26_learning.py", "learning_sha256"),
        ("r26_recovery_pilot.py", "adapter_sha256"),
    ):
        check(
            file_sha256(HERE.parent / "quality-acceleration-r26" / name) == plan[key],
            "Original B code binding",
        )
    train, tune = data(PARENT, False)
    x, y, weights, reports = make_training(train, 100)
    pointers = {}
    root = source / "training/model"
    for name in ("best", "latest", "previous"):
        pointer = read(root / f"{name}.json")
        validate_generation(root / pointer["path"], pointer["manifest_sha256"])
        pointers[name] = pointer
    latest = load_checkpoint(root)
    previous = load_checkpoint(root / pointers["previous"]["path"])
    check(
        not latest.used_previous and latest.state["binding"] == digest(plan), "Checkpoint binding"
    )
    check(
        latest.state["epoch"] == latest.state["best_epoch"] == 16 and latest.model.steps == 400,
        "Expected committed B16",
    )
    check(
        latest.permutation.shape == (len(y),)
        and np.array_equal(np.sort(latest.permutation), np.arange(len(y))),
        "Sampler coverage",
    )
    check(
        all(np.isfinite(v).all() for v in latest.model.arrays().values()),
        "Checkpoint contains nonfinite values",
    )
    model = WeightedSwiGLU.from_arrays(previous.model.metadata(), previous.model.arrays())
    # Reproduce the old numerical environment for the integrity proof only.
    # A separately declared continuation may use the benchmark-selected thread count.
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1):
        permutation, loss = epoch(model, x, y, weights, previous.state["epoch"], plan["schedule"])
    exact = loss == latest.state["last_loss"] and model.steps == latest.model.steps
    exact &= np.array_equal(permutation, latest.permutation)
    exact &= all(
        np.array_equal(v, latest.model.arrays()[name]) for name, v in model.arrays().items()
    )
    check(exact, "Exact B15-to-B16 replay failed")
    graph = out / "bundle/b16.onnx"
    graph.parent.mkdir(exist_ok=True)
    export(graph, graph_for(latest.model))
    session = cpu_session(graph, 1)
    baseline = cpu_session(PARENT / "bundle/swiglu.onnx", 1)
    b = assessment(lambda a: session.run(["score"], {"input": a})[0], tune, 100)
    a = assessment(lambda a: baseline.run(["score"], {"input": a})[0], tune, 100)
    batch = np.concatenate([frame["x"][:, :100] for frame in tune.values()])
    expected = batched_predict(latest.model, batch)
    actual = session.run(["score"], {"input": batch})[0]
    np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=1e-5)
    gain = b["selection_rank"][0] - a["selection_rank"][0]
    deltas = {
        name: b["sources"][name]["URI_ONLY"]["original_request"]["recall"]
        - a["sources"][name]["URI_ONLY"]["original_request"]["recall"]
        for name in ("WAF", "NOTES_SYNTHETIC")
    }
    allowed = gain >= 0.05 and min(deltas.values()) >= -0.02
    atomic_json(
        out / "checkpoint-audit.json",
        {
            "original_plan_sha256": file_sha256(source / "training-plan.json"),
            "binding": digest(plan),
            "pointers": pointers,
            "epoch": 16,
            "step": 400,
            "parameters": sum(v.size for v in latest.model.parameters.values()),
            "originals": sum(r["originals"] for r in reports),
            "sources": reports,
            "exact_epoch_replay": {
                "from": 15,
                "to": 16,
                "parameters_adam_sampler_loss": "BIT_EXACT",
                "threads": 1,
            },
            "numpy_onnx_max_abs": float(np.max(np.abs(expected - actual))),
            "onnx_sha256": file_sha256(graph),
            "matched_TUNING": {"R26A": a, "B16": b},
            "macro_recall_gain": gain,
            "old_source_recall_deltas": deltas,
            "continuation_justified_by_TUNING_only": allowed,
            "calibration_or_test_used_to_choose_continuation": False,
            "old_notes_TEST_reopened": False,
            "pid": os.getpid(),
            "seconds": time.monotonic() - began,
            "source_original_checkpoint_modified": False,
        },
    )


if __name__ == "__main__":
    os.umask(0o077)
    run(output_arg())

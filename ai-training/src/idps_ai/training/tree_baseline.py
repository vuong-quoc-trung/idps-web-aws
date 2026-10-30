"""Bounded classical tabular reference, not an automatically deployed champion."""

import time
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, atomic_json
from idps_ai.data.dataset import verify_dataset
from idps_ai.data.snapshot import new_destination
from idps_ai.training.evaluation import latency_ms
from idps_ai.training.protocol import evaluate_independent, validation_groups
from idps_ai.training.resources import resource_envelope
from idps_ai.training.runner import load_arrays


def benchmark_tree(dataset, output, max_threads=8, max_iterations=32):
    from sklearn.ensemble import HistGradientBoostingClassifier

    if not 1 <= max_iterations <= 64:
        raise PipelineError("Tree benchmark is capped at64iterations; no hidden HPO")
    dataset = Path(dataset).resolve()
    output = new_destination(output)
    metadata = verify_dataset(dataset, "prepared")
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise PipelineError("Benchmark cache must remain outside the source dataset")
    output.mkdir(mode=0o700)
    started = time.monotonic()
    with resource_envelope(max_threads, 16) as (guard, resources):
        arrays = load_arrays(dataset, output, "mlp", metadata["feature_count"], 16 * 1024**3)
        model = HistGradientBoostingClassifier(
            learning_rate=0.08,
            max_iter=1,
            max_leaf_nodes=15,
            min_samples_leaf=32,
            l2_regularization=1.0,
            max_bins=63,
            early_stopping=False,
            warm_start=True,
            random_state=17,
        )
        for end in range(1, max_iterations + 1, 4):
            if guard.check() or guard.thermal_limit_reached or time.monotonic() - started > 300:
                raise PipelineError(
                    "Tree benchmark stopped by resource/thermal/duration guard; no result certified"
                )
            model.max_iter = min(end + 3, max_iterations)
            model.fit(arrays["train"][0], arrays["train"][1])
        probabilities = model.predict_proba(arrays["val"][0]).astype(np.float32)
        if not np.array_equal(model.classes_, np.arange(8)):
            raise PipelineError("Tree reference training needs all eight classes")
        report = {
            "format_version": 1,
            "model": "HistGradientBoostingClassifier",
            "iterations": model.n_iter_,
            "dataset_sha256": metadata["dataset_sha256"],
            "training_rows": len(arrays["train"][1]),
            "evaluation": evaluate_independent(
                arrays["val"][1], 1 - probabilities[:, 0], probabilities, validation_groups(dataset)
            ),
            "latency_ms": latency_ms(model.predict_proba, arrays["val"][0][:1], repeats=50),
            "latency_scope": "warm batch1 sklearn model only; not ONNX or full preprocessing",
            "parameters": {
                k: model.get_params()[k]
                for k in (
                    "learning_rate",
                    "max_leaf_nodes",
                    "min_samples_leaf",
                    "l2_regularization",
                    "max_bins",
                    "early_stopping",
                    "random_state",
                )
            },
            "deployment_bundle_created": False,
            "champion_selected": False,
            "limits": [
                "Fixed CPU tree reference, not architecture-only ablation against neural two-epoch runs.",
                "No pickle/model serialization or new inference dependency; serving acceptance remains separate.",
            ],
        }
        guard.check()
        resources.update(guard.metrics())
    report.update(wall_seconds=time.monotonic() - started, resources=resources)
    atomic_json(output / "report.json", report)
    return report

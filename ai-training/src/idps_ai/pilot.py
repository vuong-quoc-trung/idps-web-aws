"""Five-epoch real-corpus pipeline acceptance; selection uses validation only."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from idps_ai.common import AI_ROOT, CLASSES, PipelineError, atomic_json, file_sha256, load_json
from idps_ai.data.capacity import validate_training_report
from idps_ai.data.dataset import iter_rows, verify_dataset
from idps_ai.data.privacy import request_numbers
from idps_ai.data.snapshot import new_destination
from idps_ai.features.pipeline import FeatureExtractor, transform
from idps_ai.training.checkpoint import load_checkpoint
from idps_ai.training.deep import AUTOENCODERS
from idps_ai.training.evaluation import evaluate
from idps_ai.training.runner import predict_batches


def validation_diagnostics(dataset, model, threshold, selection_only=False):
    """Fixed-threshold missing-source sensitivity; never refits on test labels."""
    spec = load_json(Path(dataset) / "feature_spec.json")
    rows = [r for r in iter_rows(Path(dataset) / "requests.parquet") if r["split"] == "val"]
    selected_keys = None
    if selection_only:
        from idps_ai.training.protocol import validation_groups

        protocol = validation_groups(dataset)
        known = [r for r in rows if r["label"] is not None]
        selected_keys = {known[i]["request_key"] for i in protocol["selection_indices"]}
    result = {
        "partition": "val_selection_groups" if selection_only else "val",
        "scope": "inference-only missing-input sensitivity; not ablation retraining",
        "fixed_threshold": threshold,
    }
    for scenario in (
        "available_inputs",
        "without_query",
        "without_flow",
        "without_actor",
        "without_response",
    ):
        extractor, vectors, labels, identities, cases = (
            FeatureExtractor(**spec["state_limits"]),
            [],
            [],
            [],
            [],
        )
        for original in rows:
            row = dict(original)
            if scenario == "without_query":
                row["numeric_json"] = json.dumps(request_numbers(row["uri_path"], None))
            elif scenario == "without_flow":
                row["flow_json"] = "{}"
            elif scenario == "without_actor":
                row.update(user_key=None, session_key=None, role="UNKNOWN")
            elif scenario == "without_response":
                row.update(status_code=None, response_bytes=None, latency_ms=None)
            vector = transform(spec, extractor.observe(row))
            if (
                row["label"] is None
                or selected_keys is not None
                and row["request_key"] not in selected_keys
            ):
                continue
            vectors.append(vector)
            labels.append(CLASSES.index(row["attack_family"]))
            identities.append(row["request_key"])
            cases.append(original)
        scores, probabilities = predict_batches(model, np.asarray(vectors, np.float32))
        metrics = evaluate(np.asarray(labels), scores, threshold, probabilities)
        predicted = scores >= threshold
        benign_errors = np.asarray(
            [r["label"] == 0 and (r["status_code"] or 0) >= 400 for r in cases]
        )
        metrics["benign_http_error_cases"] = {
            "count": int(benign_errors.sum()),
            "flagged": int((benign_errors & predicted).sum()),
        }
        if scenario == "available_inputs":
            source = Path(dataset).parent / "validation-rule-facts.json"
            if source.is_file():
                facts = load_json(source)
                if (
                    facts["dataset_sha256"] != verify_dataset(dataset)["dataset_sha256"]
                    or facts["partition"] != "val"
                ):
                    raise PipelineError("Rule comparison dataset/partition mismatch")
                index = {r["request_key"]: r for r in facts["facts"]}
                if selected_keys is not None:
                    index = {k: v for k, v in index.items() if k in selected_keys}
                if set(index) != set(identities):
                    raise PipelineError(
                        "Rule comparison does not cover validation identities exactly"
                    )
                fusion = {}
                for name in ("all_rules", "web_rules"):
                    combined = predicted | np.asarray([index[rid][name] for rid in identities])
                    metric = evaluate(np.asarray(labels), combined.astype(np.float32), 0.5)
                    tn, fp = metric["confusion_matrix"][0]
                    metric["empirical_fpr"] = fp / max(tn + fp, 1)
                    metric["meets_1pct_false_alert_budget"] = metric["empirical_fpr"] <= 0.01
                    fusion[name] = metric
                result["rule_or_ai"] = fusion
        result[scenario] = metrics
    return result


def run_pilot(
    dataset,
    readiness,
    output,
    max_threads=8,
    include_weighted_residual=False,
    candidate_set="baseline",
):
    validate_training_report(readiness, dataset)
    metadata = verify_dataset(dataset, "prepared")
    output = new_destination(output)
    output.mkdir(mode=0o700)
    started = time.time()
    scale = candidate_set == "scale"
    target_epochs, first_epochs = (2, 1) if scale else (5, 2)
    report = {
        "format_version": 1,
        "purpose": "two epoch technical main-model challenger"
        if scale
        else "five epoch offline lab pilot, not formal champion training",
        "started_at_unix": started,
        "dataset_sha256": metadata["dataset_sha256"],
        "readiness_report_sha256": file_sha256(readiness),
        "models": {},
        "metric_partition": "val_selection_groups" if scale else "val",
        "validation_during_training": False if scale else True,
        "calibration_partition": "val_calibration_groups" if scale else "val",
        "test_metrics_computed": False,
        "production_ready": False,
        "champion_selected": False,
    }
    environment = os.environ | {"PYTHONPATH": str(AI_ROOT / "src")}

    def worker(arguments, name):
        with (
            (output / (name + ".stdout.log")).open("w") as stdout,
            (output / (name + ".stderr.log")).open("w") as stderr,
        ):
            result = subprocess.run(
                [sys.executable, "-m", "idps_ai", *arguments],
                env=environment,
                stdout=stdout,
                stderr=stderr,
                timeout=600,
            )
        if result.returncode:
            raise PipelineError("Pilot worker failed; inspect its private logs")
        return load_json(output / (name + ".stdout.log"))

    candidates = [
        ("mlp", "train_config.yaml"),
        ("autoencoder", "anomaly_config.yaml"),
        ("residual", "residual_config.yaml"),
    ]
    if candidate_set == "expanded":
        candidates = [
            ("residual", "residual_config.yaml"),
            ("deep_mlp", "deep_mlp_config.yaml"),
            ("denoising_autoencoder", "denoising_config.yaml"),
            ("gated_residual", "gated_residual_config.yaml"),
        ]
    elif scale:
        candidates = [
            ("residual", "residual_config.yaml"),
            ("deep_mlp", "deep_mlp_config.yaml"),
            ("gated_residual", "gated_residual_config.yaml"),
            ("residual_glu", "scale_pilot_config.yaml"),
        ]
    elif candidate_set != "baseline":
        raise PipelineError("Unsupported pilot candidate set")
    if include_weighted_residual:
        candidates.append(("weighted_residual", "weighted_residual_config.yaml"))
    for kind, config in candidates:
        config_path = AI_ROOT / "configs" / config
        if scale:
            effective = yaml.safe_load(config_path.read_text())
            effective["training"].update(
                batch_size=128,
                learning_rate=0.0003,
                scheduler="warmup_cosine",
                warmup_steps=30,
                total_steps=1000,
                min_lr_ratio=0.05,
                early_stopping_patience=0,
                validation_during_training=False,
            )
            config_path = output / (kind + "-effective-config.yaml")
            config_path.write_text(yaml.safe_dump(effective))
        run, reference = output / (kind + "-resumed"), output / (kind + "-continuous")
        shared = [
            "train",
            "--dataset",
            str(dataset),
            "--config",
            str(config_path),
            "--readiness-report",
            str(readiness),
            "--max-threads",
            str(max_threads),
            "--memory-limit-gib",
            "16",
            "--max-duration-minutes",
            "8" if scale else "150",
        ]
        first = worker(
            [*shared, "--run-dir", str(run), "--epochs", str(first_epochs)], kind + "-first"
        )
        resumed = worker(
            [
                *shared,
                "--run-dir",
                str(run),
                "--resume-from",
                str(run),
                "--epochs",
                str(target_epochs),
            ],
            kind + "-resume",
        )
        continuous = worker(
            [*shared, "--run-dir", str(reference), "--epochs", str(target_epochs)],
            kind + "-reference",
        )
        a, b = load_checkpoint(run), load_checkpoint(reference)
        exact = (
            first["process_id"] != resumed["process_id"]
            and all(
                a.state[k] == b.state[k]
                for k in (
                    "global_step",
                    "epoch",
                    "cursor",
                    "numpy_rng",
                    "python_rng",
                    "scheduler",
                    "patience",
                    "best_metric",
                    "history",
                )
            )
            and np.array_equal(a.permutation, b.permutation)
            and all(np.array_equal(v, b.model.arrays()[k]) for k, v in a.model.arrays().items())
        )
        if not exact or resumed["epoch"] != target_epochs:
            raise PipelineError(
                "Pilot resume differs from continuous reference or did not reach requested pilot epochs"
            )
        bundle = worker(
            [
                "export",
                "--dataset",
                str(dataset),
                "--checkpoint",
                str(run),
                "--output",
                str(output / (kind + "-bundle")),
                "--max-threads",
                str(max_threads),
                "--validation-only",
                *(["--independent-validation"] if scale else []),
            ],
            kind + "-export",
        )
        report["models"][kind] = {
            "config_sha256": resumed["config_sha256"],
            "parameter_count": sum(v.size for v in a.model.parameters.values()),
            "class_weights": a.model.class_weights.tolist()
            if a.model.class_weights is not None
            else None,
            "exact_resume": exact,
            "epoch": resumed["epoch"],
            "global_step": resumed["global_step"],
            "training_rows": a.state["shard"]["row_count"],
            "benign_only_training": kind in AUTOENCODERS,
            "sessions": [first, resumed],
            "continuous_reference_session": continuous,
            "checkpoint_manifest_sha256": resumed["checkpoint_manifest_sha256"],
            "onnx_sha256": bundle["files"]["model.onnx"],
            "onnx_parity": bundle["parity"],
            "threshold": bundle["threshold"],
            "calibration": bundle["calibration"],
            "validation_evaluation": load_json(output / (kind + "-bundle/evaluation.json")),
            "validation_diagnostics": validation_diagnostics(
                dataset, a.model, bundle["threshold"], selection_only=scale
            ),
            "independent_validation": load_json(
                output / (kind + "-bundle/independent_validation.json")
            )
            if scale
            else None,
        }
        atomic_json(output / "pilot-progress.json", {"completed_models": list(report["models"])})
    report["ended_at_unix"] = time.time()
    report["wall_seconds"] = report["ended_at_unix"] - started
    report["optimizer_seconds"] = sum(
        s["session_optimizer_seconds"] for m in report["models"].values() for s in m["sessions"]
    )
    report["reference_optimizer_seconds"] = sum(
        m["continuous_reference_session"]["session_optimizer_seconds"]
        for m in report["models"].values()
    )
    report["limits"] = [
        "Disjoint calibration/selection campaigns; same lab environment, not production generalization"
        if scale
        else "Validation metrics share calibration data; test labels remain sealed",
        "Scale candidates use the same fixed two-epoch/data/schedule protocol; algorithms/regularizers differ, so this is not an isolated architecture ablation",
        "Loopback fixture workload, no production quality or zero-day acceptance",
        "No time-filling epochs; short pilot is not a 2–3h thermal/endurance test",
    ]
    atomic_json(output / "pilot-report.json", report)
    return report

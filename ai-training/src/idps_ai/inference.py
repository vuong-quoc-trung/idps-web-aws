"""Reference streaming inference on the SAME fused-request contract as training.

Rust must implement this versioned preprocessing contract + golden vectors in
its own integration task; this module never connects to the Security engine.
"""

from pathlib import Path

import numpy as np

from idps_ai.common import CLASSES, PipelineError, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import FeatureExtractor, implementation_fingerprint, transform
from idps_ai.training.deep import AUTOENCODERS


class InferencePipeline:
    def __init__(self, bundle, max_threads=8):
        bundle = Path(bundle)
        self.manifest = load_json(bundle / "model_manifest.json")
        for name in ("model.onnx", "feature_spec.json"):
            if file_sha256(bundle / name) != self.manifest["files"][name]:
                raise PipelineError("Model bundle checksum mismatch")
        self.spec = load_json(bundle / "feature_spec.json")
        if self.spec["implementation_sha256"] != implementation_fingerprint():
            raise PipelineError(
                "Preprocessing implementation differs from the fitted feature contract"
            )
        self.extractor = FeatureExtractor(**self.spec["state_limits"])
        self.session = cpu_session(bundle / "model.onnx", max_threads)

    def observe(self, fused_request, include_features=False):
        """Consume one chronological post-response fused row exactly once."""
        vector = transform(self.spec, self.extractor.observe(fused_request))
        score, output = self.session.run(None, {"input": vector[np.newaxis, :]})
        above = float(score[0]) >= self.manifest["threshold"]
        supervised = self.manifest["model_kind"] not in AUTOENCODERS
        result = {
            "score": float(score[0]),
            "above_threshold": above,
            "decision": ("attack_candidate" if supervised else "anomaly_candidate")
            if above
            else "below_threshold",
            "family_candidate": CLASSES[int(np.argmax(output[0, 1:])) + 1]
            if supervised and above
            else None,
        }
        if include_features:
            result["feature_vector"] = vector.tolist()
        return result


def shadow_replay(dataset, bundle, output, partition="val", max_requests=512, max_threads=8):
    """Bounded AI-only integration on chronological fused rows. Never calls web/firewall APIs."""
    import os
    import tempfile
    import time

    from idps_ai.common import atomic_json
    from idps_ai.data.dataset import iter_rows, verify_dataset
    from idps_ai.data.snapshot import new_destination
    from idps_ai.training.resources import resource_envelope

    if partition not in ("train", "val") or not 1 <= max_requests <= 10000:
        raise PipelineError("Technical shadow replay requires train/val and a1–10000request cap")
    dataset = Path(dataset).resolve()
    output = new_destination(output)
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise PipelineError("Shadow output must be outside the immutable dataset")
    manifest = verify_dataset(dataset, "prepared")
    timings = []
    with tempfile.TemporaryDirectory(prefix=".shadow-", dir=output.parent) as temporary:
        work = Path(temporary)
        with resource_envelope(max_threads, 16):
            pipeline = InferencePipeline(bundle, max_threads)
            with (work / "predictions.jsonl").open("x") as stream:
                (work / "predictions.jsonl").chmod(0o600)
                for row in iter_rows(dataset / "requests.parquet"):
                    if row["split"] != partition:
                        continue
                    before = time.perf_counter_ns()
                    result = pipeline.observe(row)
                    timings.append((time.perf_counter_ns() - before) / 1e6)
                    import json

                    stream.write(
                        json.dumps({"event_key": row["event_key"], **result}, allow_nan=False)
                        + "\n"
                    )
                    if len(timings) >= max_requests:
                        break
                stream.flush()
                os.fsync(stream.fileno())
        if not timings:
            raise PipelineError("No replayable requests in the selected partition")
        verify_dataset(dataset, "prepared")
        report = {
            "format_version": 1,
            "mode": "offline_shadow_only",
            "requests": len(timings),
            "partition": partition,
            "dataset_sha256": manifest["dataset_sha256"],
            "bundle_manifest_sha256": file_sha256(Path(bundle) / "model_manifest.json"),
            "predictions_sha256": file_sha256(work / "predictions.jsonl"),
            "enforcement_actions": 0,
            "latency_ms": dict(
                zip(("p50", "p95", "p99"), map(float, np.percentile(timings, [50, 95, 99])))
            ),
            "latency_scope": "Python feature extraction plus ONNX, one ordered request at a time; includes cold first observation",
            "test_labels_used": False,
            "limits": [
                "This is offline integration, not a live sensor/Web/IPS rollout.",
                "Input must be chronological fused requests using the matching numeric bridge and feature contract.",
            ],
        }
        atomic_json(work / "report.json", report)
        os.rename(work, output)
    return report

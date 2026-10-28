"""Reference streaming inference on the SAME fused-request contract as training.

Rust must implement this versioned preprocessing contract + golden vectors in
its own integration task; this module never connects to the Security engine.
"""

from pathlib import Path

import numpy as np

from idps_ai.common import CLASSES, PipelineError, file_sha256, load_json
from idps_ai.export.onnx import cpu_session
from idps_ai.features.pipeline import FeatureExtractor, implementation_fingerprint, transform


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
        supervised = self.manifest["model_kind"] != "autoencoder"
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

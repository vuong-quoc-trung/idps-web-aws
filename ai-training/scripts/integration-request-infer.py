#!/usr/bin/env python3
"""Portable, local-only shadow inference for an explicit checksum-pinned bundle."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Set before NumPy/BLAS import. The demo loads a single worker and never spawns
# training jobs, installs dependencies, connects to a network or invokes blocking.
for name in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[name] = "1"


class RequestPredictor:
    def __init__(self, bundle):
        self.root = Path(bundle).resolve()
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        for name, expected in self.manifest["files_sha256"].items():
            p = self.root / name
            if (
                p.is_symlink()
                or not p.resolve().is_relative_to(self.root)
                or hashlib.sha256(p.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("Bundle integrity verification failed")
        sys.path.insert(0, str(self.root / "python"))
        import numpy as np
        from sklearn.feature_extraction.text import HashingVectorizer

        from idps_ai.features.request_preprocessing import bounded_spec
        from idps_ai.training.checkpoint import load_checkpoint

        self.np = np
        loaded = load_checkpoint(self.root / "checkpoint")
        if loaded.model.kind != "deep_mlp" or loaded.model.input_dim != 588:
            raise ValueError("Wrong model architecture in bundle")
        self.model = loaded.model
        self.spec = bounded_spec()
        self.threshold = float(self.manifest["threshold"])
        self.hashing = HashingVectorizer(
            analyzer="char",
            ngram_range=(3, 5),
            n_features=512,
            alternate_sign=False,
            norm="l2",
            dtype=np.float32,
        )

    def predict(self, record):
        from threadpoolctl import threadpool_limits

        from idps_ai.features.request_preprocessing import encode_request
        from idps_ai.features.request_view import project_request
        from idps_ai.features.rich_content_v2 import rich_request_v2
        from idps_ai.mvp_inference import validate_http

        if not isinstance(record, dict) or record.get("schema_version") not in [
            "integration-request-1",
            "research-mvp-1",
        ]:
            raise ValueError("Unsupported request schema")
        rid = record.get("record_id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", rid):
            raise ValueError("Invalid opaque record_id")
        request = validate_http(record.get("http_request"))
        numbers = project_request(request["url"], request["method"])
        numeric = encode_request(self.spec, numbers["numbers"])
        symbolic, availability = rich_request_v2(
            request["method"], request["url"], request["headers"], request["body"]
        )
        content = self.hashing.transform([symbolic]).toarray().astype(self.np.float32)[0]
        vector = self.np.concatenate((numeric, content))[None, :]
        with threadpool_limits(limits=1):
            score = float(self.model.predict(vector)[0][0])
        if not self.np.isfinite(score):
            raise ValueError("Nonfinite model result")
        return {
            "schema_version": "integration-request-1",
            "record_id": rid,
            "mode": "shadow",
            "model_version": self.manifest["model_version"],
            "encoder_version": "rich_content_v2+bounded-request-v1",
            "score": score,
            "research_threshold": self.threshold,
            "threshold_rule": "strict_greater_than",
            "above_research_threshold": score > self.threshold,
            "combined_score": None,
            "enforcement_actions": 0,
            "feature_availability": {
                "headers_observed": request["headers"] is not None,
                "body_observed": request["body"] is not None,
                "numeric_dropped_query_fields": numbers["availability"]["dropped_fields"],
                **availability,
            },
            "quality_scope": "publisher-label research; score is not calibrated attack probability",
        }


def infer(bundle, input_path, output_path):
    source = Path(input_path).resolve()
    destination = Path(output_path).absolute()
    if (
        destination.is_symlink()
        or destination.exists()
        or source == destination
        or not source.is_file()
    ):
        raise ValueError("Require existing input and a new different nonsymlink output")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    model = RequestPredictor(bundle)
    seen = set()
    count = 0
    descriptor, tmp = tempfile.mkstemp(prefix=".shadow-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w") as stream, source.open("rb") as incoming:
            os.chmod(tmp, 0o600)
            for line_number, line in enumerate(incoming, 1):
                if not line.strip() or len(line) > 256 * 1024:
                    raise ValueError(f"Invalid record at line{line_number}")
                record = json.loads(line)
                result = model.predict(record)
                if result["record_id"] in seen:
                    raise ValueError("Duplicate record_id")
                seen.add(result["record_id"])
                count += 1
                stream.write(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")
            if not count:
                raise ValueError("Input has no records")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, destination)
        parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {
        "records": count,
        "mode": "shadow",
        "output": str(destination),
        "enforcement_actions": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(infer(args.bundle, args.input, args.output)))
    except (ValueError, TypeError, KeyError, OSError):
        print("Shadow inference rejected input or bundle; raw content omitted", file=sys.stderr)
        raise SystemExit(2)

"""Versioned request encodings. Frozen legacy and45-feature contracts stay intact."""

import math
from functools import cache
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, digest, file_sha256
from idps_ai.features.request_encoding import INTERACTIONS, encoding_fingerprint
from idps_ai.features.request_encoding import encode_request as encode_legacy
from idps_ai.features.request_view import PROFILE, columns, fingerprint, validate_numbers

FULL_ENCODING = "bounded-request-v1"


@cache
def full_encoding_fingerprint():
    return digest(
        {
            "implementation": file_sha256(Path(__file__)),
            "interaction_definition": encoding_fingerprint(),
        }
    )


def bounded_spec():
    return {
        "profile": PROFILE,
        "feature_version": FULL_ENCODING,
        "columns": sorted([*columns(), *INTERACTIONS]),
        "implementation_sha256": fingerprint(),
        "encoding": {
            "name": FULL_ENCODING,
            "implementation_sha256": full_encoding_fingerprint(),
            "operation": "flags/ratios unchanged; other nonnegative v: log1p(v)/(1+log1p(v)); interaction=min(two_counts)",
        },
        "dtype": "float32",
        "fit_rows": 0,
        "fit_partition": "none; fixed positivebounded transform",
        "fit_labels": "none",
        "temporal_features": False,
        "excluded": "no additional rawtext/source/identity/status/flow/clock; all70 observednumericinputs retained",
    }


def encode_request(spec, numbers):
    encoding = spec.get("encoding", {})
    if encoding.get("name") != FULL_ENCODING:
        return encode_legacy(spec, numbers)
    if encoding.get("implementation_sha256") != full_encoding_fingerprint() or spec[
        "columns"
    ] != sorted([*columns(), *INTERACTIONS]):
        raise PipelineError("Full request encoding contract/hash mismatch")
    validate_numbers(numbers)
    values = dict(numbers)
    values.update({key: min(numbers[a], numbers[b]) for key, (a, b) in INTERACTIONS.items()})
    result = []
    for name in spec["columns"]:
        value = values[name]
        if name.startswith("method_") or name.endswith(("_ratio", "_available")):
            if not 0 <= value <= 1:
                raise PipelineError("Invalid flag/ratio in full request encoding")
            result.append(value)
        else:
            z = math.log1p(value)
            result.append(z / (1 + z))
    return np.asarray(result, np.float32)

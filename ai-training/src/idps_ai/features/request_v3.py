"""Separate research tensor: immutable runtime v2 prefix plus bounded body syntax.

No fitting, raw body text, secret hashes or labels participate in this transform.
"""

import numpy as np

from idps_ai.common import digest
from idps_ai.features import body_syntax_v1 as body
from idps_ai.features.request_preprocessing import bounded_spec

VERSION = "request-v3-body-syntax-v1"
WIDTH = 634


def contract():
    spec = bounded_spec()
    return {
        "version": VERSION,
        "dtype": "float32",
        "input_dimension": WIDTH,
        "blocks": [
            {"offset": 0, "width": 76, "columns": spec["columns"], "spec": spec},
            {
                "offset": 76,
                "width": 512,
                "columns": [f"runtime_rich_v2_hash_{i:03}" for i in range(512)],
                "encoding": "Frozen rich_content_v2, body=None, URI and three selected headers; char3-5, unsigned hash512, shared L2",
            },
            {
                "offset": 588,
                "width": 46,
                "columns": list(body.COLUMNS),
                "body_contract_sha256": body.CONTRACT_SHA256,
                "encoding": "float32(raw_integer)/float32(fixed_maximum)",
                "divisors": list(body.MAXIMA),
            },
        ],
        "fit_rows": 0,
        "statistics_partition": "NONE_FIXED_CONTRACT_MAXIMA",
        "missingness": "11 one-hot states and 4 media states retained; non-OK syntax tail zero; never impute missing as empty",
        "base_body_observed": False,
        "body_observed_separately": True,
        "frozen_input_compatible": False,
        "privacy": "Inherited runtime projection plus existing body allowlist; no identities, field values/names or secret digests added; derived vectors local only",
    }


def assemble(runtime, syntax):
    x = np.asarray(runtime)
    b = np.asarray(syntax)
    if x.shape != (588,) or not np.isfinite(x).all() or np.any(x < 0) or np.any(x > 1.00001):
        raise ValueError("Invalid runtime prefix")
    # validate_event rejects bools, nonintegers, bad shape/range/state and non-OK content.
    body.validate_event(body.event("0" * 32, syntax))
    result = np.concatenate(
        [x.astype(np.float32), b.astype(np.float32) / np.asarray(body.MAXIMA, np.float32)]
    ).astype(np.float32)
    if result.shape != (WIDTH,) or not np.isfinite(result).all():
        raise ValueError("Invalid candidate tensor")
    return result


def fingerprint():
    return digest(contract())


def expanded_parameters(parameters):
    """Versioned in-memory warm start, no optimizer/checkpoint/training operation.

    Initial body weights zero: preserves the old function while allowing a later
    gradient update to learn new inputs. Existing optimizer state must be reset.
    """
    if parameters["W0"].shape != (588, 64):
        raise ValueError("Unexpected frozen first layer")
    result = {k: v.copy() for k, v in parameters.items()}
    result["W0"] = np.concatenate([result["W0"], np.zeros((46, 64), np.float32)])
    return result

"""Bounded request-only numeric projection for research shadow inference."""

from functools import cache
from pathlib import Path

from idps_ai.common import PipelineError, digest, file_sha256
from idps_ai.features.request_preprocessing import bounded_spec, encode_request
from idps_ai.features.request_view import METHODS, project_request

VERSION = "idps-request-time-uri76-v1"


@cache
def schema():
    spec = bounded_spec()
    return {
        "version": VERSION,
        "columns": spec["columns"],
        "input_shape": [None, 76],
        "dtype": "float32",
        "stage": "REQUEST_ONLY",
        "includes_response_status": False,
        "transform_sha256": digest([VERSION, spec, file_sha256(Path(__file__))]),
    }


def from_numbers(numbers):
    return encode_request(bounded_spec(), numbers)


def from_request(target, method):
    if (
        type(target) is not str
        or not target.startswith("/")
        or target.startswith("//")
        or len(target) > 4096
        or not target.isascii()
        or any(ord(c) < 0x21 or ord(c) == 0x7F for c in target)
        or "#" in target
        or method not in METHODS
        or method == "OTHER"
    ):
        raise PipelineError("Unsupported research request envelope")
    # The existing projector removes sensitive fields before deriving numeric features.
    return from_numbers(project_request(target, method)["numbers"])

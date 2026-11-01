"""Opt-in bounded syntax encoding of the immutable70-number request envelope.

No vocabulary, source moments, actor, clock or labels enter this transform.
Counts and interactions are features, never hard-rule decisions. It does not
recover body/header/query information absent in the original observation.
"""

import math
from functools import cache
from pathlib import Path

import numpy as np

from idps_ai.common import PipelineError, file_sha256
from idps_ai.features.pipeline import transform
from idps_ai.features.request_view import PROFILE, fingerprint, validate_numbers

ENCODING = "bounded-security-v1"
COUNTERS = tuple(
    sorted(
        """sqli_keywords xss_tokens traversal_tokens quote_single quote_double
semicolon percent lt gt dollar pipe encoding_rounds percent_escape_count invalid_escape_count
sql_comment_open_count sql_comment_close_count sql_line_comment_count comparison_operator_count
boolean_operator_count comma_count parenthesis_open_count parenthesis_close_count parenthesis_max_depth
html_tag_open_count html_tag_close_count html_entity_count event_assignment_count uri_scheme_count
path_parent_segment_count path_dot_segment_count backslash_count shell_and_count shell_or_count
shell_substitution_count backtick_count newline_count null_byte_count duplicate_parameter_count
empty_parameter_count""".split()
    )
)
INTERACTIONS = {
    "quote_boolean": ("quote_single", "boolean_operator_count"),
    "quote_comparison": ("quote_single", "comparison_operator_count"),
    "tag_event": ("html_tag_open_count", "event_assignment_count"),
    "tag_scheme": ("html_tag_open_count", "uri_scheme_count"),
    "parent_backslash": ("path_parent_segment_count", "backslash_count"),
    "dollar_parenthesis": ("dollar", "parenthesis_open_count"),
}


@cache
def encoding_fingerprint():
    return file_sha256(Path(__file__))


def security_spec():
    columns = sorted([*COUNTERS, *INTERACTIONS])
    return {
        "profile": PROFILE,
        "feature_version": ENCODING,
        "columns": columns,
        "implementation_sha256": fingerprint(),
        "encoding": {
            "name": ENCODING,
            "implementation_sha256": encoding_fingerprint(),
            "count_cap": 32,
            "operation": "log1p(min(nonnegative_count,32))/log1p(32); interaction=min(two_counts)",
        },
        "dtype": "float32",
        "fit_rows": 0,
        "fit_partition": "none; fixed transform chosen before validation study",
        "fit_labels": "none",
        "temporal_features": False,
        "excluded": "route/method/length/entropy/parametercount/source/status/actor/time/UA/rule",
    }


def encode_request(spec, numbers):
    # Original affine request contracts keep their exact numerical semantics.
    if "encoding" not in spec:
        return transform(spec, numbers)
    encoding = spec["encoding"]
    if (
        encoding.get("name") != ENCODING
        or encoding.get("implementation_sha256") != encoding_fingerprint()
        or spec["columns"] != sorted([*COUNTERS, *INTERACTIONS])
        or encoding.get("count_cap") != 32
    ):
        raise PipelineError("Request encoding contract/hash mismatch")
    validate_numbers(numbers)
    values = dict(numbers)
    values.update({key: min(numbers[a], numbers[b]) for key, (a, b) in INTERACTIONS.items()})
    return np.asarray(
        [math.log1p(min(values[key], 32)) / math.log1p(32) for key in spec["columns"]],
        np.float32,
    )

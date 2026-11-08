"""Coverage uses actual feature uniqueness; mutation cannot pass on row count."""

import importlib.util
import json
from pathlib import Path

import numpy as np

from idps_ai.features import body_syntax_v1 as body
from idps_ai.features import request_v3

s = importlib.util.spec_from_file_location(
    "grounded", Path(__file__).parents[1] / "scripts/materialize-grounded-request-v3.py"
)
g = importlib.util.module_from_spec(s)
s.loader.exec_module(g)


def test_benign_post_count_does_not_inflate_unique_feature_views():
    rows = [
        dict(
            sample_id=str(i),
            intent="BENIGN_INTENT",
            method="POST",
            environment="lab",
            endpoint_template="/safe",
            workflow_group="owned-json",
            session_group="session-1",
            campaign_group="campaign-1",
            family="benign",
            oracle_verified=True,
            review_status="PENDING",
        )
        for i in range(6)
    ]
    syntax = np.array(
        [body.extract(b'{"description":"Ordinary product"}', "application/json")] * 6, np.uint8
    )
    x = np.stack([request_v3.assemble(np.zeros(588, np.float32), v.tolist()) for v in syntax])
    report = g.augment_coverage(g.module("materialize-request-v3"), rows, x, syntax, list(range(6)))
    assert report["records"] == 6 and report["benign_JSON_POST"] == 6
    assert report["benign_POST_unique_views"] == 1 and report["benign_POST_workflows"] == 1
    assert report["lineage_components"] == 1
    assert json.loads(json.dumps(report))["benign_JSON_POST"] == 6

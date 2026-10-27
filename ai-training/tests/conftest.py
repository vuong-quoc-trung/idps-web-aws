import pytest

from idps_ai.data.dataset import collect
from idps_ai.data.readers import Input
from idps_ai.data.split import prepare
from idps_ai.data.synthetic import synthetic_s0


@pytest.fixture(scope="session")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("prepared")
    raw = root / "raw"
    synthetic_s0(raw, campaigns=10, requests_per_campaign=16)
    inputs = [
        Input("student", raw / "student-audit.log"),
        Input("nginx", raw / "access.log"),
        Input("suricata", raw / "eve.json"),
    ]
    collect(inputs, root / "collected", (raw / "redaction.key").read_bytes(), raw / "labels.jsonl")
    prepare(root / "collected", root / "prepared")
    return root / "prepared"

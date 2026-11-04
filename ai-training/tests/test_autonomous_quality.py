"""The automatic quality gate must reject tampering and sealed references."""

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from idps_ai.common import PipelineError, digest


def _qa():
    path = Path(__file__).resolve().parents[1] / "scripts/assess-autonomous-quality.py"
    spec = importlib.util.spec_from_file_location("autonomous_quality", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_self_hash_rejects_mutated_label_claim(tmp_path):
    from idps_ai.common import atomic_json

    path = tmp_path / "oracle.json"
    report = {"machine_verified_attack_intent": 0, "intent_unknown": 8}
    report["report_sha256"] = digest(report)
    atomic_json(path, report)
    assert _qa()._report(path)["intent_unknown"] == 8
    report["machine_verified_attack_intent"] = 8
    atomic_json(path, report)
    with pytest.raises(PipelineError, match="self-hash"):
        _qa()._report(path)


def test_inconclusive_evidence_never_promotes_research_ready():
    qa = _qa()
    gates = {"integrity": {"status": "PASS"}, "label": {"status": "INCONCLUSIVE"}}
    assert qa._overall_status(gates, ("integrity", "label")) == "INCONCLUSIVE"
    gates["label"]["status"] = "FAIL"
    assert qa._overall_status(gates, ("integrity", "label")) == "FAIL"
    gates["label"]["status"] = "PASS"
    assert qa._overall_status(gates, ("integrity", "label")) == "PASS"


def test_numeric_tamper_and_sealed_reference_fail_closed(tmp_path):
    qa = _qa()
    vector = np.zeros(76, np.float32)
    good_key = hashlib.sha256(vector.tobytes()).hexdigest()
    staging = tmp_path / "staging.parquet"

    def write_staging(key):
        pq.write_table(
            pa.table(
                {
                    "view_sha256": [key],
                    "label": pa.array([1], type=pa.int8()),
                    "occurrence_rows": pa.array([1], type=pa.int32()),
                    "features": pa.FixedSizeListArray.from_arrays(pa.array(vector), 76),
                }
            ),
            staging,
        )

    write_staging(good_key)
    assert qa._read_numeric_views(staging, _sha(staging), 1)[0] == {good_key}
    write_staging("0" * 64)
    with pytest.raises(PipelineError, match="mismatches its key"):
        qa._read_numeric_views(staging, _sha(staging), 1)

    reference = tmp_path / "sealed.parquet"
    pq.write_table(
        pa.table(
            {
                "split": ["test"],
                "x": pa.FixedSizeListArray.from_arrays(pa.array(vector), 76),
            }
        ),
        reference,
    )
    with pytest.raises(PipelineError, match="sealed"):
        qa._reference_keys(reference, _sha(reference))

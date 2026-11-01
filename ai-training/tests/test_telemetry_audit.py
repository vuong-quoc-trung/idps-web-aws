import zipfile

import pytest

from idps_ai.common import PipelineError, file_sha256
from idps_ai.data.telemetry_audit import audit_telemetry_bundle


def bundle(path):
    fields = "timestamp,source,request_id,flow_id,attack_instance_id,label\n"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in {
            "LICENSE": "UNIT TEST FIXTURE ONLY",
            "README.md": "not real telemetry",
            "code/extract_features.py": 'return "NORMAL"\n',
            "dataset/raw/access.log": '127.0.0.1 - - [01/Nov/2026:00:00:00 +0000] "GET /?secret=PRIVATE HTTP/1.1" 200 10 "-" "test"\n'
            * 2
            + '127.0.0.1 - - [01/Nov/2026:00:00:01 +0000] "HEAD / HTTP/1.0" 204 0\n'
            + "bad line\n",
            "dataset/raw/eve.json": '{"event_type":"flow"}\n{"event_type":"alert"}\n',
            "dataset/raw/dataset_labels.csv": "timestamp,scenario_id,label,layer,target,status\n2026-11-01T00:00:00,fixture,SQLI_ATTEMPT,L7,local,OK\n",
            "dataset/curated/dataset.csv": fields + "1,nginx,REQ1,,group1,NORMAL\n",
            "dataset/curated/train.csv": fields + "1,nginx,REQ1,,group1,NORMAL\n",
            "dataset/curated/test.csv": fields + "2,nginx,REQ2,,group2,SQLI_ATTEMPT\n",
        }.items():
            archive.writestr("SOC-MLD-v1.0/" + name, data)


def test_telemetry_audit_counts_observations_without_promoting_rules_or_ok_status(tmp_path):
    archive = tmp_path / "fixture.zip"
    bundle(archive)
    result = audit_telemetry_bundle(archive, tmp_path / "audit", file_sha256(archive))
    assert result["counts"]["parseable_http_observations"] == 3
    assert result["counts"]["distinct_complete_log_observations"] == 2
    assert result["counts"]["distinct_method_target_user_agent_representations"] == 2
    assert result["counts"]["unparsed_access_lines"] == 1
    assert result["counts"]["operator_naive_clock_rows"] == 1
    assert result["counts"]["operator_rows_with_request_id"] == 0
    assert result["operator_statuses_not_exploit_success"] == {"OK": 1}
    assert result["eve_types"] == {"flow": 1, "alert": 1}
    assert result["request_level_verified_labels"] == 0
    assert result["verified_physical_requests"] is None
    assert result["supervised_training_eligible"] == 0
    assert "PRIVATE" not in (tmp_path / "audit/report.json").read_text()
    assert b"PRIVATE" not in (tmp_path / "audit/audit.sqlite").read_bytes()


def test_telemetry_audit_rejects_tampering_and_zip_traversal(tmp_path):
    archive = tmp_path / "fixture.zip"
    bundle(archive)
    with pytest.raises(PipelineError, match="checksum"):
        audit_telemetry_bundle(archive, tmp_path / "bad-sha", "f" * 64)
    with zipfile.ZipFile(archive, "a") as out:
        out.writestr("../escape", "test")
    with pytest.raises(PipelineError, match="Unsafe"):
        audit_telemetry_bundle(archive, tmp_path / "bad-path", file_sha256(archive))

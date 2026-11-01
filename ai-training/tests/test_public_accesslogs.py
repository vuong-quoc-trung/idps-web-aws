import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from idps_ai.data.dataset import iter_rows


def test_public_accesslog_cli_keeps_unknown_labels_and_never_exports_token(tmp_path):
    archive = tmp_path / "logs.tar.gz"
    content = (
        "hashed_ip,request_method,request_path,http_response_code,user_agent,token,date,referer\n"
        "publichash,GET,/api?query=hello&password=canary-secret,200,Mozilla,canary-token,2026-01-01T00:00:00Z,canary-ref\n"
        "publichash,GET,/api?query=hello&password=canary-secret,200,Mozilla,canary-token,2026-01-01T00:00:00Z,canary-ref\n"
    )
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("../../must-not-extract.csv")
        info.size = len(content.encode())
        stream.addfile(info, io.BytesIO(content.encode()))
    output = tmp_path / "safe"
    script = Path(__file__).resolve().parents[1] / "scripts/import-public-accesslogs.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixture",
            str(archive),
            "--output",
            str(output),
            "--max-requests",
            "10",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "manifest.json").read_text())
    assert report["data_kind"] == "synthetic_fixture"
    assert report["unique_observations"] == 1 and report["duplicate_rows"] == 1
    assert report["supervised_eligible_requests"] == 0
    rows = list(iter_rows(output / "requests.parquet"))
    assert rows[0]["label"] is None
    assert rows[0]["timestamp"] == 1767225600.0
    assert rows[0]["status_code"] == 200
    assert "canary" not in json.dumps(rows)
    assert not (tmp_path.parent / "must-not-extract.csv").exists()


def test_public_zip_audit_deduplicates_rotated_logs_without_inventing_benign(tmp_path):
    import zipfile

    from idps_ai.data.real_http import audit_http_zip

    line = '192.0.2.1 - - [17/Jul/2020:12:00:00 +0000] "GET /?token=canary-secret HTTP/1.1" 200 12 "-" "Mozilla"\n'
    path = tmp_path / "original.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("site/access.log", line)
        z.writestr("site/access.log.1", line)
        z.writestr("site/ground-truth.yaml", "- id: weak\n  filter: [python]\n")
    audit = audit_http_zip(path)
    assert audit["HTTP_rows"] == 2 and audit["unique_HTTP_observations"] == 1
    assert audit["duplicate_HTTP_observations"] == 1
    assert audit["supervised_admitted_requests"] == 0
    assert audit["labels"] == "unknown; publisher matching rules are not applied as ground truth"
    assert "canary" not in json.dumps(audit)
    assert not (tmp_path / "site").exists()


def test_public_zip_audit_refuses_unsafe_members_and_sealed_sources(tmp_path):
    import zipfile

    import pytest

    from idps_ai.data.real_http import audit_http_zip

    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("../access.log", "a")
    with pytest.raises(ValueError, match="Unsafe"):
        audit_http_zip(path)
    (tmp_path / "AI_HOLDOUT.json").write_text(json.dumps({"role": "sealed_final"}))
    with pytest.raises(ValueError, match="holdout"):
        audit_http_zip(path)


def test_public_zip_audit_enforces_expansion_budget(tmp_path):
    import zipfile

    import pytest

    from idps_ai.data.real_http import audit_http_zip

    path = tmp_path / "large.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("access.log", "x" * 10000)
    with pytest.raises(ValueError, match="budget"):
        audit_http_zip(path, max_bytes=100)

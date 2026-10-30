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

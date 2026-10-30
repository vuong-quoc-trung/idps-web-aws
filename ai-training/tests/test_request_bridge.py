import json
import subprocess
import sys
from pathlib import Path


def test_stream_bridge_is_numeric_only_compatible_with_v2_and_rejects_secret_errors():
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts/project-request-eve.py"),
    ]
    raw = {
        "event_type": "http",
        "http": {
            "http_method": "GET",
            "url": "/api?hint=1%27OR%201=1--&pwd=canary-password&token=canary-token",
        },
        "payload": "canary-body",
    }
    result = subprocess.run(
        command, input=json.dumps(raw) + "\n", capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert "ai_query_numeric" in row
    assert row["ai_request_view"]["numbers"]["sql_line_comment_count"] == 1
    assert "canary" not in result.stdout
    invalid = subprocess.run(
        command,
        input="canary-secret" + ("x" * 65536) + "\n",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert invalid.returncode == 2 and "canary" not in invalid.stderr and not invalid.stdout

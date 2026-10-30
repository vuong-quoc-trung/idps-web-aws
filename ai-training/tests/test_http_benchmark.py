import hashlib
import io
import json

import pytest

from idps_ai.common import PipelineError


def test_raw_http_reader_consumes_body_without_exposing_credentials():
    from idps_ai.data.http_benchmark import read_http

    body = b"password=canary-secret"
    raw = (
        b"POST http://localhost/login HTTP/1.1\r\nCookie: canary-cookie\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
        + b"\r\n\r\nGET /api?q=%3Cscript%3E&token=canary-token HTTP/1.1\r\n\r\n"
    )
    rows = list(read_http(io.BytesIO(raw)))
    assert len(rows) == 2
    assert rows[0]["body_present"] and not rows[1]["body_present"]
    assert rows[1]["numbers"]["html_tag_open_count"] == 1
    assert "canary" not in json.dumps(rows)
    assert "timestamp" not in rows[0] and "client_ip" not in rows[0]
    with pytest.raises(PipelineError, match="bounded|HTTP|body"):
        list(read_http(io.BytesIO(b"POST / HTTP/1.1\nContent-Length: 100\n\nshort")))


def test_public_import_verifies_source_hash_and_purges_cross_split_duplicates(tmp_path):
    from idps_ai.data.http_benchmark import import_http, iter_benchmark

    train = tmp_path / "normal-train.txt"
    test = tmp_path / "normal-test.txt"
    attack = tmp_path / "attack-test.txt"
    train.write_bytes(b"GET /same?q=1 HTTP/1.1\n\nGET /only-train?q=2 HTTP/1.1\n\n")
    test.write_bytes(b"GET /same?q=1 HTTP/1.1\n\nGET /only-test?q=3 HTTP/1.1\n\n")
    attack.write_bytes(b"GET /attack?q=%3Cscript%3E HTTP/1.1\n\n")
    entries = [
        {
            "file": str(f),
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "label": y,
            "partition": p,
            "source_id": n,
        }
        for f, y, p, n in [
            (train, 0, "train", "normal-train"),
            (test, 0, "test", "normal-test"),
            (attack, 1, "test", "anomaly-test"),
        ]
    ]
    provenance = {
        "doi": "10.60895/redata/RWUUSV",
        "license": "CC BY 4.0",
        "attribution": "Biardo; Gonzalez Guzman; Lanzotti (2024), WebRequests",
    }
    report = import_http(entries, tmp_path / "safe", provenance)
    rows = list(iter_benchmark(tmp_path / "safe"))
    assert report["raw_requests"] == 5
    assert report["cross_partition_duplicate_rows"] == 2
    assert len(rows) == 3
    assert all(r["attack_family"] is None for r in rows if r["label"] == 1)
    assert all(r["label_source"] == "publisher_binary_annotation" for r in rows)
    assert not report["full_three_source_eligible"]
    import subprocess
    import sys
    from pathlib import Path

    command = Path(__file__).resolve().parents[1] / "scripts/audit-public-http.py"
    audit = subprocess.run(
        [
            sys.executable,
            str(command),
            "--benchmark",
            str(tmp_path / "safe"),
            "--output",
            str(tmp_path / "audit.json"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert audit.returncode == 0, audit.stderr
    quality = json.loads((tmp_path / "audit.json").read_text())
    assert quality["unique_observable_request_identities"] == 4
    assert quality["request_identities_crossing_original_train_test"] == 1
    assert quality["test_minimum_errors_any_deterministic_classifier_using_this_view"] == 0
    train.write_bytes(b"changed")
    with pytest.raises(PipelineError, match="checksum"):
        import_http(entries, tmp_path / "bad", provenance)

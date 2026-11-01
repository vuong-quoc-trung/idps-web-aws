import csv
import io
import json

import pytest


def test_real_http_adapter_retains_reviewed_binary_labels_and_real_time_without_secrets():
    from idps_ai.data.real_http import iter_srbh

    fields = [
        "timestamp",
        "src_ip",
        "request_http_method",
        "request_http_request",
        "request_body",
        "request_cookie",
        "000 - Normal",
        "66 - SQL Injection",
        "242 - Code Injection",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    common = dict(
        timestamp="17/Jul/2020:12:23:34 +0100",
        src_ip="203.0.113.5",
        request_http_method="GET",
        request_http_request="/shop?term=hello&token=canary-token",
        request_body="canary-body",
        request_cookie="canary-cookie",
    )
    for normal, sqli, code in [("1", "0", "0"), ("0", "1", "0"), ("1", "1", "0"), ("0", "0", "1")]:
        writer.writerow(
            {
                **common,
                "000 - Normal": normal,
                "66 - SQL Injection": sqli,
                "242 - Code Injection": code,
            }
        )
    stream.seek(0)
    rows = list(iter_srbh(stream, b"k" * 32, "source-sha"))
    assert [r["label"] for r in rows] == [0, 1, None, 1]
    assert rows[1]["attack_family"] == "sqli" and rows[3]["attack_family"] is None
    assert rows[2]["label_state"] == "conflicting_publisher_labels"
    assert rows[0]["timestamp"] == 1594985014.0
    assert (
        len({r["natural_key"] for r in rows}) == 1
    )  # Same observed event with conflicting labels.
    assert "canary" not in json.dumps(rows) and "203.0.113.5" not in json.dumps(rows)
    assert all(r["body_present"] for r in rows)
    assert "status_code" not in rows[0]["numbers"]


def test_real_http_adapter_rejects_missing_label_schema_without_guessing_benign():
    from idps_ai.data.real_http import iter_srbh

    with pytest.raises(ValueError, match="schema"):
        list(iter_srbh(io.StringIO("request_http_request\n/api\n"), b"k" * 32, "source"))


def test_missing_clock_or_uri_stays_unavailable_instead_of_being_fabricated():
    from idps_ai.data.real_http import iter_srbh

    stream = io.StringIO(
        "timestamp,src_ip,request_http_method,request_http_request,000 - Normal,66 - SQL Injection\n,,,,0,1\n"
    )
    row = next(iter_srbh(stream, b"k" * 32, "source"))
    assert row["timestamp"] is None and row["timestamp_state"] == "missing"
    assert row["client_key"] is None
    assert row["label"] == 1  # Preserve publisher annotation while rejecting visibility claims.
    assert row["numbers"] is None
    assert row["projection_state"] == "unavailable_URI_contract"

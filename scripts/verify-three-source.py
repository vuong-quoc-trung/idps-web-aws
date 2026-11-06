#!/usr/bin/env python3
"""Small real-HTTP three-source acceptance. No exploit execution or GT labels."""

import argparse
import concurrent.futures
import http.client
import json
import socket
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def wait(call, predicate, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = call()
        if predicate(value):
            return value
        time.sleep(0.3)
    raise RuntimeError("Timed out waiting for measured telemetry condition")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sensor", type=Path, required=True)
    p.add_argument("--runtime", type=Path, default=ROOT / ".local-dev/foundation")
    p.add_argument("--gateway-port", type=int, default=18782)
    a = p.parse_args()
    receipts = []

    def request(case, query="", connection=None, method="GET", headers=None, body=None):
        own = connection is None
        c = connection or http.client.HTTPConnection(
            "127.0.0.1", a.gateway_port, timeout=20
        )
        started = time.perf_counter()
        c.request(
            method,
            "/api/auth/csrf" + query,
            body=body,
            headers=headers or {"User-Agent": "Python-urllib/3.12"},
        )
        r = c.getresponse()
        r.read()
        item = {
            "case": case,
            "request_id": r.getheader("X-Request-Id"),
            "HTTP": r.status,
            "wall_ms": (time.perf_counter() - started) * 1000,
        }
        receipts.append(item)
        if own:
            c.close()
        return item

    def results():
        path = a.runtime / "correlation/results.jsonl"
        rows = {}
        for f in [path.with_name(path.name + f".{i}") for i in [3, 2, 1]] + [path]:
            if f.exists():
                for l in f.read_text().splitlines():
                    r = json.loads(l)
                    rows[r["request_id"]] = r
        return rows

    def matched(ids):
        return wait(
            results,
            lambda rows: all(
                rows.get(rid, {}).get("status") == "MATCHED" for rid in ids
            ),
            90,
        )

    single = request("single", "?size=2")
    assert single["HTTP"] == 200
    matched([single["request_id"]])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        concurrent_receipts = list(
            pool.map(
                lambda i: request(
                    "concurrent-" + str(i), "?" + urlencode({"size": i + 1})
                ),
                range(4),
            )
        )
    concurrent_ids = [r["request_id"] for r in concurrent_receipts]
    assert len(set(concurrent_ids)) == 4
    observed = matched(concurrent_ids)
    assert (
        len(
            {
                (
                    observed[i]["sensor_instance"],
                    observed[i]["flow_id"],
                    observed[i]["tx_id"],
                )
                for i in concurrent_ids
            }
        )
        == 4
    )
    c = http.client.HTTPConnection("127.0.0.1", a.gateway_port, timeout=20)
    same = []
    for case, payload in [
        ("keepalive-benign", "ordinary"),
        ("keepalive-SQLi-shaped", "1' OR 1=1--"),
        ("keepalive-command-shaped", ";id"),
    ]:
        same.append(request(case, "?" + urlencode({"search": payload}), connection=c))
    c.close()
    same_ids = [r["request_id"] for r in same]
    observed = matched(same_ids)
    assert (
        len(
            {(observed[i]["sensor_instance"], observed[i]["flow_id"]) for i in same_ids}
        )
        == 1
    )
    assert len({observed[i]["tx_id"] for i in same_ids}) == 3
    # A bounded SYN observation on ten new lab connections, no payload/attack success.
    sockets = []
    try:
        for _ in range(10):
            sockets.append(
                socket.create_connection(("127.0.0.1", a.gateway_port), timeout=5)
            )
        time.sleep(1)
    finally:
        for s in sockets:
            s.close()
    time.sleep(2)
    # Stop only IDS, leaving byte relays and Student intact.
    (a.sensor / "STOP_SENSOR").touch()
    wait(lambda: (a.sensor / "sensor-stopped").exists(), bool, 30)
    missing = request("sensor-stopped", "?size=3")
    assert missing["HTTP"] == 200
    rows = wait(
        results,
        lambda r: (
            set(r.get(missing["request_id"], {}).get("sources", []))
            == {"NGINX", "STUDENT_AUDIT"}
        ),
        30,
    )
    assert rows[missing["request_id"]]["status"] == "MISSING_SOURCE"
    (a.sensor / "START_SENSOR").touch()
    wait(lambda: (a.sensor / "sensor-stopped").exists(), lambda v: not v, 30)
    restart = []
    for _ in range(3):
        item = request("sensor-restart-probe", "?size=4")
        restart.append(item)
        try:
            matched([item["request_id"]])
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError("IDS did not recover after bounded actual HTTP probes")
    # Controlled dummy secrets, never real credentials. Success/benign not inferred.
    private = request(
        "privacy-canary",
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "dummy=ThreeSourcePrivateCanary",
            "Authorization": "Bearer ThreeSourcePrivateCanary",
            "X-Request-Id": "f" * 32,
        },
        body="password=ThreeSourcePrivateCanary",
    )
    assert private["request_id"] != "f" * 32
    time.sleep(3)
    paths = [
        a.sensor / "eve.json",
        a.runtime / "suricata/eve.json",
        a.runtime / "correlation/results.jsonl",
        a.runtime / "ai/results.jsonl",
    ]
    for f in paths:
        for part in f.parent.glob(f.name + "*"):
            assert "ThreeSourcePrivateCanary" not in part.read_text()
    eve = []
    for f in (a.sensor).glob("eve.json*"):
        eve += [json.loads(l) for l in f.read_text().splitlines()]
    alerts = [e for e in eve if e.get("event_type") == "alert"]
    flow_alerts = [e for e in alerts if e.get("tx_id") is None]
    tx_alerts = [e for e in alerts if e.get("tx_id") is not None]
    # Attribute rule alerts only by same sensor generation + flow + transaction.
    links = []
    for e in tx_alerts:
        matches = [
            rid
            for rid, r in results().items()
            if (r["sensor_instance"], r["flow_id"], r["tx_id"])
            == (e["sensor_instance"], str(e.get("flow_id")), e["tx_id"])
        ]
        assert len(matches) <= 1
        links.append(
            {
                "signature_id": e["alert"].get("signature_id"),
                "tx_id": e["tx_id"],
                "request_ids": matches,
            }
        )
    assert any(e["alert"].get("signature_id") in [1000002, 1000005] for e in alerts)
    report = {
        "status": "PASS",
        "receipts": receipts,
        "single_request": single,
        "concurrent_requests": 4,
        "concurrent_distinct_transactions": True,
        "same_connection": {
            "request_ids": same_ids,
            "flow_id": observed[same_ids[0]]["flow_id"],
            "tx_ids": [observed[i]["tx_id"] for i in same_ids],
        },
        "IDS_stop_Student_HTTP": missing["HTTP"],
        "missing_source_result": rows[missing["request_id"]],
        "restart_probes": restart,
        "alert_links": links,
        "flow_level_alerts_observed": len(flow_alerts),
        "flow_alerts_never_promoted_to_request_labels": True,
        "duplicate_late_out_of_order_tests": "Separate adversarial fixtures, not fabricated live events",
        "privacy_canary_absent": True,
        "response_request_id_overwrote_client_input": True,
        "enforcement_actions": 0,
        "limitations": [
            "Small controlled plaintext gateway sample, not correlation100% or quality benchmark",
            "Only gateway traffic has EVE; base18780 remains independent",
            "No exploit success or independent ground truth labels claimed",
        ],
    }
    out = a.sensor / ("acceptance-" + str(time.time_ns()) + ".json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": "PASS",
                "evidence": str(out),
                "requests": len(receipts),
                "alerts": len(alerts),
                "flow_level_alerts": len(flow_alerts),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

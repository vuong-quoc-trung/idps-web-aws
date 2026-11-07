#!/usr/bin/env python3
"""Bounded local HTTP acceptance; writes private metadata only to caller output."""

import argparse
import importlib.util
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location(
    "launcher", ROOT / "scripts/dev-up-and-verify.py"
)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
p = argparse.ArgumentParser(
    description="Real metadata/API detector coordination acceptance; run after three-source acceptance with a live bounded GLU consumer."
)
p.add_argument("--sensor", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
if a.output.exists():
    raise RuntimeError("Choose new evidence output")
secret = json.loads((m.RUNTIME / "credentials.json").read_text())


def api(path, data=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    q = urllib.request.Request(
        "http://127.0.0.1:3001" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=h,
    )
    with urllib.request.urlopen(q, timeout=60) as r:
        return json.load(r)


try:
    api("/api/ai-shadow")
except urllib.error.HTTPError as e:
    assert e.code == 401
else:
    raise AssertionError("API unexpectedly public")
token = api(
    "/api/auth/login",
    {"username": "admin", "password": secret["security_admin_password"]},
)["token"]
del secret
# Wait for acceptance evidence file, independent of score arrival.
end = time.monotonic() + 90
while time.monotonic() < end:
    files = list(a.sensor.glob("acceptance-*.json"))
    if files:
        break
    time.sleep(0.5)
assert files, "Real acceptance not completed"
accept = json.loads(files[-1].read_text())
assert accept["status"] == "PASS"
ids = accept["same_connection"]["request_ids"]
page = api("/api/ai-shadow?limit=200", token=token)
rows = {r["request_id"]: r for r in page["detectors"]}
assert all(k in rows for k in ids)
# Wait for all real transaction rule alerts, allowing any ingestion ordering.
end = time.monotonic() + 20
while time.monotonic() < end:
    rows = {
        r["request_id"]: r
        for r in api("/api/ai-shadow?limit=200", token=token)["detectors"]
    }
    if all(
        any(
            a["source"] == "SURICATA" and "SENSOR_TRANSACTION" == a["basis"]
            for a in rows[k]["rules"]
        )
        for k in ids[1:]
    ):
        break
    time.sleep(0.25)
else:
    raise AssertionError("Native sensor transaction link missing")
for i, k in enumerate(ids):
    r = rows[k]
    assert r["correlation"]["tx_id"] == i
    sensor = [a for a in r["rules"] if a["source"] == "SURICATA"]
    if i == 0:
        assert not sensor
    else:
        assert sensor and all(a["tx_id"] == i for a in sensor)
    assert r["request_ai"] and r["request_ai"]["status"] == "SCORED"
assert any(a["source"] == "NGINX" for a in rows[ids[1]]["rules"])
missing = rows[accept["missing_source_result"]["request_id"]]
assert missing["glu"] is None and missing["correlation"]["status"] == "MISSING_SOURCE"
receipts = []
for i in range(2):
    start = time.time()
    with urllib.request.urlopen(
        f"http://127.0.0.1:18782/api/auth/csrf?size={31 + i}", timeout=20
    ) as r:
        rid = r.headers["X-Request-Id"]
        http = r.status
        r.read()
    receipts.append({"request_id": rid, "start_time": start, "HTTP": http})
end = time.monotonic() + 60
while time.monotonic() < end:
    page = api("/api/ai-shadow?limit=200", token=token)
    allrows = {r["request_id"]: r for r in page["detectors"]}
    for r in receipts:
        v = allrows.get(r["request_id"])
        if v and v["glu"] is not None and "api_visible_seconds" not in r:
            r["api_visible_seconds"] = time.time() - r["start_time"]
            r["detectors"] = v
    if all("api_visible_seconds" in r for r in receipts):
        break
    time.sleep(0.2)
assert all("api_visible_seconds" in r for r in receipts), (
    "New GLU results not delivered within60s"
)
# Exact metadata replay, not new HTTP/attack. It must not create an alert.
al = next(
    json.loads(l)
    for l in (a.sensor / "eve.json").read_text().splitlines()
    if json.loads(l).get("event_type") == "alert"
)
q = "SELECT count(*) FROM security_alerts"
before = int(m.sql(m.container_name("security"), "security_db", q))
with (m.RUNTIME / "suricata/eve.json").open("a") as f:
    f.write(json.dumps(al) + "\n")
time.sleep(2)
after = int(m.sql(m.container_name("security"), "security_db", q))
assert after == before
assert (
    m.sql(
        m.container_name("security"),
        "security_db",
        "SELECT count(*) FROM firewall_actions WHERE source='AUTO'",
    )
    == "0"
)
report = {
    "status": "PASS",
    "acceptance_file": str(files[-1]),
    "keepalive_transactions": [
        {
            k: r[k]
            for k in [
                "request_id",
                "status",
                "rules",
                "flow_context",
                "request_ai",
                "glu",
            ]
        }
        for r in [rows[k] for k in ids]
    ],
    "sensor_missing_GLU": None,
    "new_live_probes": receipts,
    "metadata_replay_alerts": [before, after],
    "automatic_firewall_actions": 0,
    "unauthenticated_API": 401,
    "scope": "Real HTTP + genuine sanitized metadata replay; not attack outcomes or detection quality",
}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {
            "status": "PASS",
            "keepalive_rule_tx_links": 3,
            "new_GLU_API_seconds": [r["api_visible_seconds"] for r in receipts],
            "replay_counts": [before, after],
        },
        indent=2,
    )
)

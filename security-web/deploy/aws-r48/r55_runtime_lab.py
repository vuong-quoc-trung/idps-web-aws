"""Verify multi-detector aggregation and C2 denial in the R53 private runtime."""

import json
from pathlib import Path
import re
import sys

from r53_runtime_lab import main, request, wait_for


def verify(rid, alert_id, admin, viewer, sql, stream):
    assert re.fullmatch("[0-9a-f]{32}", rid) and alert_id.isdecimal()
    for method, endpoint, payload in (
        ("POST", "/api/blocked-ips", {"ip": "192.0.2.55", "reason": "R55 isolated safety check"}),
        ("DELETE", "/api/blocked-ips/192.0.2.55", None),
    ):
        assert request(33053, endpoint, method, payload)[0] == 401
        assert request(33053, endpoint, method, payload, viewer)[0] == 403
        status, _, body = request(33053, endpoint, method, payload, admin)
        assert status == 400 and "C2_EXECUTION_DISABLED" in json.loads(body)["message"]
    assert request(33053, "/api/prevention/proposals", token=viewer)[0] == 403
    assert request(33053, "/api/prevention/proposals", token=admin)[0] == 200

    # Two explicitly synthetic source alerts test aggregation, not upstream detection.
    # The Suricata alert and request correlation come from the real lab runtime.
    fixture = f"""
    WITH alerts AS (
        INSERT INTO security_alerts
            (event_key, occurred_at, source, event_type, rule_name, category, severity, action, evidence)
        VALUES
            ('r55-fixture-nginx-{rid}', now(), 'NGINX', 'alert', 'R55 fixture gateway signal',
                'Lab gateway marker', 2, 'ALERT', '{{"fixture":true}}'),
            ('r55-fixture-audit-{rid}', now(), 'STUDENT_AUDIT', 'alert', 'R55 fixture application signal',
                'Lab application marker', 1, 'ALERT', '{{"fixture":true}}')
        ON CONFLICT DO NOTHING RETURNING id
    )
    INSERT INTO detector_alert_links (alert_id, request_id, source_instance, link_basis)
    SELECT id, '{rid}', 'r55-fixture', 'REQUEST_ID' FROM alerts;
    """
    sql(fixture)
    sql(fixture)

    def incident():
        status, _, body = request(33053, f"/api/hybrid-incidents?request_id={rid}", token=admin)
        assert status == 200
        rows = json.loads(body)["incidents"]
        expected = ["NGINX", "STUDENT_AUDIT", "SURICATA"]
        if len(rows) == 1 and rows[0]["rule_sources"] == expected:
            return rows[0]

    result = wait_for(incident)
    ids = {int(item.split(":")[1]) for item in result["evidence_ids"] if item.startswith("alert:")}
    assert len(ids) == 3 and int(alert_id) in ids
    assert result["policy_action"] == "REVIEW" and result["final_risk"] == 90
    assert result["rule_risk_component"] == 90 and not result["automatic_block"]
    assert result["https_research"]["action"] == "LOG_ONLY" and result["trusted_client_ip"] is None
    injected = ids - {int(alert_id)}
    for identifier in injected:
        status, _, body = request(33053, f"/api/alerts/{identifier}", token=admin)
        assert status == 200 and json.loads(body)["alert"]["rule_name"].startswith("R55 fixture")
    delivered = set()
    while delivered != injected:
        line = stream.readline()
        if not line:
            raise RuntimeError("SSE closed before fixture delivery")
        if line.strip() == b"event: alert.created":
            match = re.fullmatch(rb"data: ([0-9]+)", stream.readline().strip())
            if match and int(match[1]) in injected:
                delivered.add(int(match[1]))
    assert sql(f"SELECT count(*) FROM hybrid_incidents WHERE request_id='{rid}'") == "1"
    assert sql(f"SELECT count(*) FROM security_alerts WHERE event_key LIKE 'r55-fixture-%-{rid}'") == "2"
    assert sql("SELECT count(*) FROM firewall_actions") == "0"
    print(json.dumps({"request_id": rid, "sources": result["rule_sources"], "source_alerts": len(ids),
                      "synthetic_alerts": 2, "hybrid": "REVIEW", "risk": 90, "native_suricata": 1,
                      "incident_count": 1, "sse_alerts": len(delivered),
                      "c2_authenticated_write": 400, "firewall_actions": 0}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], verify)

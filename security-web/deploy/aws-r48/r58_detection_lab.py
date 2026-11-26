"""Verify source-specific alerts using harmless HTTP on the R53 private stack."""

import json
from pathlib import Path
import ssl
import sys

from r53_runtime_lab import main, request, wait_for

def unavailable_location(root):
    return f"""location = /r58-unavailable {{
        access_log {root / 'edge.jsonl'} r48_access;
        proxy_pass http://127.0.0.1:19958;
    }}"""


def checks(https, sql, token, correlated_id):
    # Observe a disposable unavailable upstream and rejected empty form submissions.
    nginx_ids, audit_ids = [], []
    for _ in range(10):
        code, rid, _ = https("/r58-unavailable")
        assert code == 502 and rid
        nginx_ids.append(rid)
    for _ in range(5):
        code, rid, _ = https("/api/users", method="POST")
        assert code == 403 and rid
        identities = {value.strip() for value in rid.split(",")}
        assert len(identities) == 1, "Proxy and application reported different request IDs"
        audit_ids.extend(identities)

    def counts():
        value = json.loads(sql("""
            SELECT jsonb_object_agg(rule_code, n) FROM (
                SELECT rule_code,count(*) n FROM security_alerts
                WHERE rule_code IN ('GATEWAY_ERROR_BURST','APP-1018','SID 153001')
                GROUP BY rule_code
            ) a
        """))
        return value if value and value.get("GATEWAY_ERROR_BURST") and value.get("APP-1018") else None

    try:
        alerts = wait_for(counts)
    except RuntimeError:
        print("R58_DETECTION_DIAGNOSTIC=" + sql(
            "SELECT json_build_object('alerts',(SELECT jsonb_agg(rule_code) FROM security_alerts),"
            "'gateway_observations',(SELECT count(*) FROM nginx_behavior_observations WHERE gateway),"
            "'audit_signals',(SELECT count(*) FROM application_security_observations))"
        ), flush=True)
        raise
    assert alerts["GATEWAY_ERROR_BURST"] == alerts["APP-1018"] == 1
    stats_code, _, body = request(33053, "/api/stats?range=1h", token=token)
    assert stats_code == 200
    stats = json.loads(body)
    link = sql("""SELECT l.request_id FROM detector_alert_links l
                    JOIN security_alerts a ON a.id=l.alert_id WHERE a.rule_code='APP-1018'""")
    assert link in audit_ids, {"linked": link, "application_responses": audit_ids}
    assert not sql("""SELECT l.request_id FROM detector_alert_links l
                        JOIN security_alerts a ON a.id=l.alert_id WHERE a.rule_code='GATEWAY_ERROR_BURST'""")
    for source in ("NGINX", "STUDENT_AUDIT", "SURICATA"):
        stored = int(sql(f"SELECT count(*) FROM security_alerts WHERE source='{source}'"))
        observed = int(sql(f"SELECT count(*) FROM normalized_events WHERE source='{source}'"))
        assert any(row["name"] == source and row["count"] == stored for row in stats["sources"])
        # Ingest is still running. The response is a snapshot taken before this readback.
        assert 1 <= stats["observation_counts"][source] <= observed
    print("R58_DETECTION=" + json.dumps({"alerts": alerts, "stats": stats["sources"],
        "observations": stats["observation_counts"], "audit_request": link,
        "correlation_request": correlated_id, "proxy_episode_unlinked": True}), flush=True)


if __name__ == "__main__":
    root = Path(sys.argv[1])

    def check(rid, _alert, token, _viewer, sql, _stream):
        def https(path, method="GET"):
            return request(18453, path, method,
                           tls=ssl.create_default_context(cafile=str(root / "tls.crt")))

        checks(https, sql, token, rid)

    main(root, Path(sys.argv[2]), sys.argv[3], check, extra_nginx_location=unavailable_location(root))

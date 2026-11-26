WITH filtered AS MATERIALIZED (
 SELECT id, occurred_at, source, event_type, host(src_ip) AS src_ip, host(dest_ip) AS dest_ip,
        host(client_ip) AS client_ip, host(network_src_ip) AS network_src_ip, client_ip_verified, suricata_post_proxy,
        proto, rule_name, signature, category, severity, action, evidence, triage_status, triage_version, triage_actor, triage_updated_at
 FROM security_alerts
 WHERE (NOT $11::boolean OR source <> 'AI_SHADOW')
 AND ($3::text IS NULL OR rule_name ILIKE '%' || $3 || '%' OR host(src_ip) ILIKE '%' || $3 || '%' OR host(network_src_ip) ILIKE '%' || $3 || '%')
 AND ($4::smallint IS NULL OR severity = $4)
 AND ($5::timestamptz IS NULL OR occurred_at >= $5)
 AND ($6::timestamptz IS NULL OR occurred_at < $6)
 AND ($7::text IS NULL OR source = $7 OR ($7 = 'STUDENT_AUDIT' AND source = 'APPLICATION'))
 AND ($8::text IS NULL OR action = $8)
 AND ($9::text IS NULL OR dest_ip = $9::inet)
 AND ($10::text IS NULL OR triage_status = $10)
), page AS (SELECT * FROM filtered ORDER BY occurred_at DESC, id DESC LIMIT $1 OFFSET $2)
SELECT jsonb_build_object('total', (SELECT count(*) FROM filtered),
 'items', COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM page p), '[]'::jsonb))

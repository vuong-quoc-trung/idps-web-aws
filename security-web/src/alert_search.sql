WITH filtered AS MATERIALIZED (
 SELECT id, occurred_at, source, event_type, host(src_ip) AS src_ip, host(dest_ip) AS dest_ip,
        proto, rule_name, signature, category, severity, action, evidence
 FROM security_alerts
 WHERE ($3::text IS NULL OR rule_name ILIKE '%' || $3 || '%' OR host(src_ip) ILIKE '%' || $3 || '%')
 AND ($4::smallint IS NULL OR severity = $4)
 AND ($5::timestamptz IS NULL OR occurred_at >= $5)
 AND ($6::timestamptz IS NULL OR occurred_at < $6)
 AND ($7::text IS NULL OR source = $7)
 AND ($8::text IS NULL OR action = $8)
 AND ($9::text IS NULL OR dest_ip = $9::inet)
), page AS (SELECT * FROM filtered ORDER BY occurred_at DESC, id DESC LIMIT $1 OFFSET $2)
SELECT jsonb_build_object('total', (SELECT count(*) FROM filtered),
 'items', COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM page p), '[]'::jsonb))

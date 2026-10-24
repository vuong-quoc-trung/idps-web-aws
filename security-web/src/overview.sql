WITH bounds AS (
    SELECT now() AS until, now() - make_interval(secs => $1::double precision) AS since,
           make_interval(secs => ($1 / $2)::double precision) AS step
), events AS MATERIALIZED (
    SELECT a.* FROM security_alerts a, bounds b
    WHERE a.occurred_at >= b.since AND a.occurred_at < b.until
), buckets AS (
    SELECT h FROM bounds b, LATERAL generate_series(b.since, b.until - b.step, b.step) h
), trend AS (
    SELECT h AS hour, count(e.id) AS count FROM buckets CROSS JOIN bounds b
    LEFT JOIN events e ON e.occurred_at >= h AND e.occurred_at < h + b.step
    GROUP BY h ORDER BY h
), types AS (
    SELECT rule_name AS name, count(*) AS count FROM events
    GROUP BY rule_name ORDER BY count DESC, name LIMIT 8
), sources AS (
    SELECT source AS name, count(*) AS count FROM events GROUP BY source ORDER BY count DESC, name
), severities AS (
    SELECT severity, count(*) AS count FROM events GROUP BY severity ORDER BY severity
), source_ips AS (
    SELECT host(src_ip) AS ip, count(*) AS count, min(severity) AS severity, max(occurred_at) AS last_seen
    FROM events WHERE src_ip IS NOT NULL GROUP BY src_ip ORDER BY count DESC, ip LIMIT 5
), destination_ips AS (
    SELECT host(dest_ip) AS ip, count(*) AS count, min(severity) AS severity, max(occurred_at) AS last_seen
    FROM events WHERE dest_ip IS NOT NULL GROUP BY dest_ip ORDER BY count DESC, ip LIMIT 5
), recent AS (
    SELECT id, occurred_at, source, host(src_ip) AS src_ip, host(dest_ip) AS dest_ip,
           rule_name, severity, action, evidence FROM events ORDER BY occurred_at DESC, id DESC LIMIT 10
), jobs AS (
    SELECT status, count(*) AS count FROM firewall_actions, bounds b
    WHERE action = 'BLOCK' AND created_at >= b.since AND created_at < b.until GROUP BY status
)
SELECT jsonb_build_object(
    'from', (SELECT since FROM bounds), 'to', (SELECT until FROM bounds),
    'total_alerts', (SELECT count(*) FROM events),
    'critical_alerts', (SELECT count(*) FROM events WHERE severity = 1),
    'blocked_attacks', (SELECT count(*) FROM events WHERE action = 'AUTO-BLOCK'),
    'unique_sources', (SELECT count(DISTINCT src_ip) FROM events),
    'unknown_destinations', (SELECT count(*) FROM events WHERE dest_ip IS NULL),
    'trend', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM trend t), '[]'::jsonb),
    'types', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM types t), '[]'::jsonb),
    'sources', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM sources t), '[]'::jsonb),
    'severities', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM severities t), '[]'::jsonb),
    'source_ips', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM source_ips t), '[]'::jsonb),
    'destination_ips', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM destination_ips t), '[]'::jsonb),
    'recent', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM recent t), '[]'::jsonb),
    'jobs', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM jobs t), '[]'::jsonb)
)

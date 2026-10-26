WITH filtered AS MATERIALIZED (
 SELECT id, occurred_at
 FROM normalized_events
 WHERE ($3::timestamptz IS NULL OR occurred_at >= $3)
 AND ($4::timestamptz IS NULL OR occurred_at < $4)
 AND ($5::text IS NULL OR source = $5)
 AND ($6::text IS NULL OR client_ip = $6::inet)
 AND ($7::text IS NULL OR strpos(uri_path, $7) > 0)
 AND ($8::integer IS NULL OR status_code = $8)
 AND ($9::text IS NULL OR request_id = $9)
 AND ($10::text IS NULL OR http_method = $10)
), page AS (
 SELECT e.id, e.occurred_at, e.observed_at, e.canonical
 FROM (SELECT id FROM filtered ORDER BY occurred_at DESC,id DESC LIMIT $1 OFFSET $2) f
 JOIN normalized_events e ON e.id=f.id
)
SELECT jsonb_build_object('total', (SELECT count(*) FROM filtered),
 'items', COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.occurred_at DESC,p.id DESC) FROM page p), '[]'::jsonb))

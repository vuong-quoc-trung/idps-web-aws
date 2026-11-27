-- Use request IDs from the signed gateway leg, plus validated receipts that
-- arrived before the NGINX line. Direct routes are outside the denominator.
WITH expected AS MATERIALIZED (
    SELECT DISTINCT request_id
    FROM normalized_events
    WHERE source='NGINX' AND observed_at >= now()-interval '15 minutes'
      AND request_id IS NOT NULL AND canonical @> '{"ai_projection":true}'
), latest_receipts AS MATERIALIZED (
    SELECT request_id
    FROM https_research_observations
    WHERE observation->>'version'=$1 AND observation->>'model_sha256'=$2
    ORDER BY received_at DESC, request_id LIMIT 50
), receipts AS MATERIALIZED (
    SELECT request_id, received_at, observation, conflicted
    FROM https_research_observations
    WHERE observation->>'version'=$1 AND observation->>'model_sha256'=$2
      AND (received_at >= now()-interval '15 minutes' OR request_id IN (SELECT request_id FROM latest_receipts))
), joined AS MATERIALIZED (
    SELECT COALESCE(e.request_id,h.request_id) AS request_id, h.received_at,
           (e.request_id IS NOT NULL OR h.received_at >= now()-interval '15 minutes') AS in_window,
           CASE
               WHEN h.conflicted OR c.result->>'status'='AMBIGUOUS' THEN 'CONFLICT'
               WHEN h.request_id IS NULL THEN 'PENDING'
               ELSE h.observation->>'status'
           END AS status,
           (h.observation->>'score')::double precision AS score,
           (h.observation->>'threshold')::double precision AS threshold,
           CASE WHEN i.decision#>>'{https_research,model_id}'=$1
               AND i.decision#>>'{https_research,model_sha256}'=$2 THEN i.decision->>'policy_action' END AS hybrid
    FROM expected e FULL JOIN receipts h USING(request_id)
    LEFT JOIN request_correlations c ON c.request_id=COALESCE(e.request_id,h.request_id)
    LEFT JOIN hybrid_incidents i ON i.request_id=COALESCE(e.request_id,h.request_id)
), recent AS (
    SELECT request_id, received_at, status,
           CASE WHEN status='SCORED' THEN score END AS score,
           CASE WHEN status='SCORED' THEN threshold END AS threshold,
           CASE WHEN status='SCORED' THEN score > threshold END AS anomalous,
           hybrid
    FROM joined ORDER BY received_at DESC NULLS LAST, request_id LIMIT 50
)
SELECT jsonb_build_object(
    'window_minutes',15,
    'eligible',count(*),
    'scored',count(*) FILTER (WHERE status='SCORED'),
    'anomalous',count(*) FILTER (WHERE status='SCORED' AND score > threshold),
    'pending',count(*) FILTER (WHERE status='PENDING'),
    'abstained',count(*) FILTER (WHERE status='ABSTAIN'),
    'conflicts',count(*) FILTER (WHERE status='CONFLICT'),
    'inference_errors',count(*) FILTER (WHERE status='INFERENCE_ERROR'),
    'latest_score_at',max(received_at) FILTER (WHERE status='SCORED'),
    'recent',COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY r.received_at DESC NULLS LAST,r.request_id) FROM recent r),'[]'::jsonb)
) FROM joined WHERE in_window

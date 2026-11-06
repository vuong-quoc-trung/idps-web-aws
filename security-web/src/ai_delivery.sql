-- Observed Nginx IDs are a lower bound, never a transport-loss denominator.
WITH requests AS (
  SELECT DISTINCT request_id FROM normalized_events
  WHERE source='NGINX' AND event_type='http_request' AND request_id IS NOT NULL
    AND uri_path LIKE '/api/%' AND occurred_at >= now()-interval '5 minutes'
    AND occurred_at < now()-interval '15 seconds'
), joined AS (
  SELECT n.request_id,r.result->>'status' AS status
  FROM requests n LEFT JOIN ai_shadow_results r USING(request_id)
)
SELECT jsonb_build_object(
 'collection_enabled',$1::boolean,'window_seconds',300,'grace_seconds',15,
 'nginx_observed_requests',count(*),
 'scored',count(*) FILTER(WHERE status='SCORED'),
 'inference_errors',count(*) FILTER(WHERE status='INFERENCE_ERROR'),
 'unresolved_after_grace',count(*) FILTER(WHERE status IS NULL),
 'scope','Observed Nginx API request IDs only; unresolved can mean loss, rejection, worker outage or processing/ingestion delay. Not a measured end-to-end packet loss rate.'
) FROM joined

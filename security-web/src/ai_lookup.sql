-- Match the active artifact before reading any historical result.
WITH model_result AS (
SELECT jsonb_build_object(
    'request_id', a.request_id,
    'status', CASE WHEN a.conflicted OR c.result->>'status'='AMBIGUOUS'
        THEN 'CONFLICT' ELSE a.observation->>'status' END,
    'score', CASE WHEN NOT a.conflicted AND c.result->>'status' IS DISTINCT FROM 'AMBIGUOUS'
        AND a.observation->>'status'='SCORED' THEN a.observation->'score' END,
    'threshold', CASE WHEN NOT a.conflicted AND c.result->>'status' IS DISTINCT FROM 'AMBIGUOUS'
        AND a.observation->>'status'='SCORED' THEN a.observation->'threshold' END,
    'anomalous', CASE WHEN NOT a.conflicted AND c.result->>'status' IS DISTINCT FROM 'AMBIGUOUS'
        AND a.observation->>'status'='SCORED' THEN
        (a.observation->>'score')::double precision > (a.observation->>'threshold')::double precision END,
    'hybrid', CASE WHEN i.decision#>>'{https_research,model_id}'=$2
        AND i.decision#>>'{https_research,model_sha256}'=$3 THEN i.decision->>'policy_action' END,
    'hybrid_reason', CASE WHEN i.decision#>>'{https_research,model_id}'=$2
        AND i.decision#>>'{https_research,model_sha256}'=$3 THEN i.decision->'policy_reason' END,
    'receipt', CASE WHEN NOT a.conflicted AND c.result->>'status' IS DISTINCT FROM 'AMBIGUOUS'
        THEN jsonb_build_object('request_id',a.request_id,'status',a.observation->'status',
            'score',a.observation->'score','threshold',a.observation->'threshold','received_at',a.received_at) END
) AS result
FROM https_research_observations a
LEFT JOIN request_correlations c USING (request_id)
LEFT JOIN hybrid_incidents i USING (request_id)
WHERE a.request_id=$1 AND a.observation->>'version'=$2 AND a.observation->>'model_sha256'=$3
UNION ALL
SELECT jsonb_build_object(
    'request_id', i.request_id,
    'status', 'NO_AI_RECEIPT',
    'score', NULL,
    'threshold', NULL,
    'anomalous', NULL,
    'hybrid', i.decision->>'policy_action',
    'hybrid_reason', i.decision->'policy_reason'
)
FROM hybrid_incidents i
WHERE i.request_id=$1
  AND i.decision#>>'{https_research,model_id}' IS NULL
  AND NOT EXISTS (SELECT 1 FROM https_research_observations a WHERE a.request_id=i.request_id)
), edge AS (
    SELECT *, count(*) OVER () AS matches FROM normalized_events WHERE request_id=$1 AND source='NGINX'
)
SELECT COALESCE(m.result,jsonb_build_object('request_id',$1,'status','NO_AI_RECEIPT',
        'score',NULL,'threshold',NULL,'anomalous',NULL,'hybrid',NULL))
    || jsonb_build_object(
        'correlation_status', c.result->>'status', 'sources', c.result->'sources',
        'late', c.result->'late_event', 'flow_id', c.result->>'flow_id', 'tx_id', c.result->'tx_id',
        'client_ip', host(n.client_ip), 'http_method', n.http_method, 'uri_path', n.uri_path,
        'status_code', n.status_code, 'latency_ms', n.canonical->'latency_ms'
    ) AS result
FROM (SELECT $1::text AS request_id) k
LEFT JOIN model_result m ON true
LEFT JOIN request_correlations c USING (request_id)
LEFT JOIN edge n ON k.request_id=n.request_id AND n.matches=1
WHERE m.result IS NOT NULL OR c.request_id IS NOT NULL OR n.id IS NOT NULL

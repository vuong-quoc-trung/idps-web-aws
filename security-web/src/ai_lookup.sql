-- Match the active artifact before reading any historical result.
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
        AND i.decision#>>'{https_research,model_sha256}'=$3 THEN i.decision->>'policy_action' END
)
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
    'hybrid', i.decision->>'policy_action'
)
FROM hybrid_incidents i
WHERE i.request_id=$1
  AND i.decision#>>'{https_research,model_id}' IS NULL
  AND NOT EXISTS (SELECT 1 FROM https_research_observations a WHERE a.request_id=i.request_id)

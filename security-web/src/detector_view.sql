WITH ids AS (
 SELECT request_id FROM request_correlations
 UNION SELECT request_id FROM ai_shadow_results
 UNION SELECT request_id FROM normalized_events WHERE request_id IS NOT NULL
), selected AS (
 SELECT i.request_id, COALESCE(c.observed_at,(SELECT max(a.observed_at) FROM ai_shadow_results a WHERE a.request_id=i.request_id),(SELECT max(n.occurred_at) FROM normalized_events n WHERE n.request_id=i.request_id)) AS observed_at,c.result AS correlation
 FROM ids i LEFT JOIN request_correlations c USING(request_id)
 WHERE ($1::text IS NULL OR i.request_id=$1)
 ORDER BY observed_at DESC LIMIT $2
)
SELECT jsonb_build_object(
 'request_id',s.request_id,'observed_at',s.observed_at,
 'correlation',s.correlation,
 'rules',COALESCE(r.alerts,'[]'::jsonb),
 'flow_context',COALESCE(f.alerts,'[]'::jsonb),
 'request_ai',ai.result,
 'glu',CASE WHEN s.correlation->>'status'='MATCHED' AND s.correlation->>'late_event'='false' THEN g.result->'glu' ELSE NULL END,
 'glu_observed_at',g.result->>'observed_at',
 'rule_observation','ALERTS_ONLY; empty list is not proof all rules observed the request',
 'status',CASE
  WHEN s.correlation->>'status'='AMBIGUOUS' THEN 'UNCERTAIN_CORRELATION'
  WHEN (ai.result->>'above_threshold'='true' OR (s.correlation->>'status'='MATCHED' AND s.correlation->>'late_event'='false' AND g.result->'glu'->>'above_threshold'='true')) THEN CASE WHEN r.alerts IS NOT NULL THEN 'RULE_AND_AI_ALERT' ELSE 'AI_ALERT_ONLY_OBSERVED' END
  WHEN r.alerts IS NOT NULL THEN 'RULE_ALERT_ONLY_OBSERVED'
  WHEN ai.result->>'status'='SCORED' AND s.correlation->>'status'='MATCHED' AND s.correlation->>'late_event'='false' AND g.result IS NOT NULL THEN 'NO_ALERT_OBSERVED'
  ELSE 'INCOMPLETE_DETECTOR_EVIDENCE' END,
 'enforcement','AI_SHADOW_ONLY',
 'dependency','GLU207 uses Suricata-derived metadata; not independent detector votes'
)
FROM selected s
LEFT JOIN LATERAL (
 SELECT result FROM ai_shadow_results a WHERE a.request_id=s.request_id ORDER BY a.observed_at DESC,a.id DESC LIMIT 1
) ai ON true
LEFT JOIN glu207_shadow_results g ON g.request_id=s.request_id AND g.proof_sha256=s.correlation->>'proof_sha256'
LEFT JOIN LATERAL (
 SELECT jsonb_agg(jsonb_build_object('id',a.id,'source',a.source,'rule',a.rule_name,'severity',a.severity,'action',a.action,'occurred_at',a.occurred_at,'received_at',a.created_at,'basis',l.link_basis,'source_instance',l.source_instance,'flow_id',l.flow_id,'tx_id',l.tx_id) ORDER BY a.id) AS alerts
 FROM detector_alert_links l JOIN security_alerts a ON a.id=l.alert_id
 WHERE (l.link_basis='REQUEST_ID' AND l.request_id=s.request_id)
 OR (l.link_basis='SENSOR_TRANSACTION' AND s.correlation->>'status'='MATCHED' AND l.source_instance='suricata-'||(s.correlation->>'sensor_instance') AND l.flow_id=s.correlation->>'flow_id' AND l.tx_id=(s.correlation->>'tx_id')::bigint)
) r ON true
LEFT JOIN LATERAL (
 SELECT jsonb_agg(jsonb_build_object('id',a.id,'source',a.source,'rule',a.rule_name,'severity',a.severity,'occurred_at',a.occurred_at,'basis','FLOW_CONTEXT') ORDER BY a.id) AS alerts
 FROM detector_alert_links l JOIN security_alerts a ON a.id=l.alert_id
 WHERE l.link_basis='FLOW_CONTEXT' AND s.correlation->>'status'='MATCHED' AND l.source_instance='suricata-'||(s.correlation->>'sensor_instance') AND l.flow_id=s.correlation->>'flow_id'
) f ON true
ORDER BY s.observed_at DESC

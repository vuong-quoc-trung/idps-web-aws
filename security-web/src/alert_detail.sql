SELECT jsonb_build_object(
 'alert', to_jsonb(a) || jsonb_build_object('src_ip',host(a.src_ip),'dest_ip',host(a.dest_ip),'client_ip',host(a.client_ip),'network_src_ip',host(a.network_src_ip)),
 'link', (SELECT jsonb_build_object('basis',link_basis,'request_id',request_id,'flow_id',flow_id,'tx_id',tx_id)
          FROM detector_alert_links WHERE alert_id=a.id),
 'linked_normalized', (SELECT CASE WHEN count(*)=1 THEN jsonb_agg(n.canonical)->0 END
    FROM detector_alert_links l JOIN normalized_events n
      ON n.request_id=l.request_id AND n.source=a.source AND n.source_instance=l.source_instance
    WHERE l.alert_id=a.id AND l.link_basis='REQUEST_ID'),
 'rule_id', COALESCE(substring(a.rule_name FROM 'SID ([1-9][0-9]*):'),
   CASE WHEN a.event_key ~ '^[a-f0-9]{64}:[A-Z_]+$' AND a.source <> 'SURICATA' THEN split_part(a.event_key,':',2) END),
 'lua_shadow', (SELECT to_jsonb(s)-'alert_id' FROM suricata_lua_alert_status s WHERE s.alert_id=a.id),
 'suricata_http', COALESCE((
   SELECT jsonb_agg(to_jsonb(h) ORDER BY h.tx_id)
   FROM (
     SELECT l.link_basis AS basis, s.request_id, s.flow_id, s.tx_id,
            host(n.client_ip) AS client_ip, n.http_method, n.uri_path, n.status_code, n.latency_ms,
            c.result->>'status' AS correlation_status, c.result->'sources' AS sources,
            jsonb_pretty(c.result) AS correlation_json, jsonb_pretty(to_jsonb(s)) AS sensor_proof_json
     FROM detector_alert_links l
     JOIN suricata_lua_shadow s ON s.generation = substring(l.source_instance FROM 10)
       AND s.flow_id = l.flow_id
       AND (l.link_basis = 'FLOW_CONTEXT' OR (l.link_basis = 'SENSOR_TRANSACTION' AND l.tx_id = s.tx_id))
       AND (l.request_id IS NULL OR l.request_id = s.request_id)
     JOIN request_correlations c ON c.request_id = s.request_id
       AND c.result->>'status' = 'MATCHED'
       AND c.result->>'sensor_instance' = s.generation
       AND c.result->>'flow_id' = s.flow_id
       AND c.result->>'tx_id' = s.tx_id::text
     JOIN LATERAL (
       SELECT client_ip, http_method, uri_path, status_code, canonical->'latency_ms' AS latency_ms,
              count(*) OVER () AS observations
       FROM normalized_events
       WHERE request_id = s.request_id AND source = 'NGINX' AND canonical @> '{"ai_projection":true}'
     ) n ON n.observations = 1 AND n.client_ip IS NOT NULL
     WHERE a.source = 'SURICATA' AND l.alert_id = a.id
       AND l.source_instance ~ '^suricata-[a-f0-9]{32}$'
       AND s.proof_present AND s.receipt_present AND NOT s.mismatched
     ORDER BY s.tx_id LIMIT 5
   ) h
 ), '[]'::jsonb),
 'triage_history', COALESCE((SELECT jsonb_agg(to_jsonb(h)) FROM (
   SELECT version,previous_status,status,actor,note,created_at FROM alert_triage_history
   WHERE alert_id=a.id ORDER BY version DESC LIMIT 50
 ) h), '[]'::jsonb),
 'related', COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM (
   SELECT id,occurred_at,rule_name,severity,source FROM security_alerts
   WHERE src_ip = a.src_ip AND id <> a.id AND (NOT $2::boolean OR source <> 'AI_SHADOW') ORDER BY occurred_at DESC,id DESC LIMIT 10
 ) r), '[]'::jsonb),
 'firewall', COALESCE((SELECT jsonb_agg(to_jsonb(f)) FROM (
   SELECT id,host(ip) AS ip,action,status,actor,source,reason,details,created_at,completed_at
   FROM firewall_actions WHERE event_id = a.id ORDER BY created_at DESC,id DESC
 ) f), '[]'::jsonb)
) FROM security_alerts a WHERE a.id = $1 AND (NOT $2::boolean OR a.source <> 'AI_SHADOW')

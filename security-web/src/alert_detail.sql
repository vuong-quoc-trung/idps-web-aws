SELECT jsonb_build_object(
 'alert', to_jsonb(a) || jsonb_build_object('src_ip',host(a.src_ip),'dest_ip',host(a.dest_ip)),
 'related', COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM (
   SELECT id,occurred_at,rule_name,severity,source FROM security_alerts
   WHERE src_ip = a.src_ip AND id <> a.id ORDER BY occurred_at DESC,id DESC LIMIT 10
 ) r), '[]'::jsonb),
 'firewall', COALESCE((SELECT jsonb_agg(to_jsonb(f)) FROM (
   SELECT id,host(ip) AS ip,action,status,actor,source,reason,details,created_at,completed_at
   FROM firewall_actions WHERE event_id = a.id ORDER BY created_at DESC,id DESC
 ) f), '[]'::jsonb)
) FROM security_alerts a WHERE a.id = $1

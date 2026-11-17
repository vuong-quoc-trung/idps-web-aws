-- Opt-in Shadow metadata only; no raw proof/receipt or client attribution.
CREATE TABLE suricata_lua_shadow (
 generation TEXT NOT NULL CHECK (generation ~ '^[a-f0-9]{32}$'),
 flow_id TEXT NOT NULL,
 tx_id BIGINT NOT NULL CHECK (tx_id >= 0),
 request_id TEXT NOT NULL,
 record_hash TEXT NOT NULL,
 proof_present BOOLEAN NOT NULL,
 receipt_present BOOLEAN NOT NULL,
 mismatched BOOLEAN NOT NULL DEFAULT false,
 duplicate_count BIGINT NOT NULL DEFAULT 0,
 first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
 last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(generation,flow_id,tx_id)
);
CREATE TABLE suricata_lua_seen (
 physical_key TEXT PRIMARY KEY,
 seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Resolve at read time: delayed evidence and conflicts revoke a previous match.
CREATE VIEW suricata_lua_alert_status AS
SELECT l.alert_id,
 CASE WHEN l.source_instance !~ '^suricata-[a-f0-9]{32}$' THEN 'PENDING_GENERATION'
 WHEN l.flow_id IS NULL OR l.tx_id IS NULL THEN 'MISSING_TRANSACTION'
 WHEN e.generation IS NULL THEN 'PENDING_EVIDENCE'
 WHEN e.mismatched OR (l.request_id IS NOT NULL AND l.request_id <> e.request_id) THEN 'MISMATCHED'
 WHEN NOT e.proof_present OR NOT e.receipt_present THEN 'MISSING_PROOF_OR_RECEIPT'
 WHEN e.duplicate_count > 0 THEN 'DUPLICATE_SHADOW'
 ELSE 'MATCHED_SHADOW' END AS status,
 false AS client_ip_verified,
 COALESCE(e.duplicate_count,0) AS duplicate_count
FROM detector_alert_links l JOIN security_alerts a ON a.id=l.alert_id
LEFT JOIN suricata_lua_shadow e ON l.source_instance='suricata-'||e.generation
 AND l.flow_id=e.flow_id AND l.tx_id=e.tx_id
WHERE a.source='SURICATA';

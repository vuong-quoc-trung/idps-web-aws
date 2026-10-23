ALTER TABLE security_alerts ADD COLUMN event_key TEXT UNIQUE;
ALTER TABLE firewall_actions DROP CONSTRAINT firewall_actions_status_check;
ALTER TABLE firewall_actions ADD CONSTRAINT firewall_actions_status_check CHECK(status IN ('PENDING','SUCCESS','ERROR'));
ALTER TABLE firewall_actions ADD COLUMN actor TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE firewall_actions ADD COLUMN event_id BIGINT UNIQUE REFERENCES security_alerts(id);
ALTER TABLE firewall_actions ADD COLUMN completed_at TIMESTAMPTZ;
CREATE TABLE log_cursors (
    file_key TEXT PRIMARY KEY, path TEXT NOT NULL, byte_offset BIGINT NOT NULL DEFAULT 0,
    generation BIGINT NOT NULL DEFAULT 0, anchor TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE ingestion_errors (
    event_key TEXT PRIMARY KEY, source TEXT NOT NULL, reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_firewall_pending ON firewall_actions(id) WHERE status='PENDING';

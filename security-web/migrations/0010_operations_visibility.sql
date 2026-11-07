ALTER TABLE security_alerts
 ADD COLUMN triage_status TEXT NOT NULL DEFAULT 'NEW' CHECK (triage_status IN ('NEW','INVESTIGATING','RESOLVED','FALSE_POSITIVE')),
 ADD COLUMN triage_version BIGINT NOT NULL DEFAULT 0,
 ADD COLUMN triage_actor TEXT,
 ADD COLUMN triage_updated_at TIMESTAMPTZ,
 ADD COLUMN rule_code TEXT GENERATED ALWAYS AS (
   CASE
     WHEN source='SURICATA' THEN 'SID ' || substring(rule_name from '^SURICATA: SID ([0-9]+):')
     WHEN source='STUDENT_AUDIT' THEN substring(signature from '^(APP-[0-9]+)$')
     WHEN source='NGINX' THEN COALESCE(substring(signature from '^([A-Z_]+)$'), substring(event_key from ':([A-Z_]+)$'))
   END
 ) STORED;
CREATE INDEX security_alerts_triage ON security_alerts(triage_status,occurred_at DESC,id DESC);
CREATE INDEX security_alerts_rule_evidence ON security_alerts(source,rule_code,created_at DESC,id DESC);
CREATE INDEX normalized_events_ingest_time ON normalized_events(source,observed_at DESC,id DESC);
CREATE TABLE alert_triage_history (
 id BIGSERIAL PRIMARY KEY,
 alert_id BIGINT NOT NULL REFERENCES security_alerts(id) ON DELETE CASCADE,
 version BIGINT NOT NULL,
 previous_status TEXT NOT NULL,
 status TEXT NOT NULL,
 actor TEXT NOT NULL,
 note TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(alert_id,version)
);

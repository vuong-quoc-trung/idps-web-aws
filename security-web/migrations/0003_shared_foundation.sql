-- Canonical Schema v1 stores redacted observations, never raw request bodies/headers.
CREATE TABLE normalized_events (
    id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    source TEXT NOT NULL CHECK (source IN ('NGINX','SURICATA','STUDENT_AUDIT')),
    source_instance TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id TEXT,
    client_ip INET,
    dest_ip INET,
    event_type TEXT NOT NULL,
    http_method TEXT,
    uri_path TEXT,
    status_code INTEGER CHECK (status_code BETWEEN 100 AND 599),
    canonical JSONB NOT NULL CHECK (canonical->>'schema_version' = '1.0'),
    UNIQUE (source,source_instance,source_event_id)
);
CREATE INDEX normalized_events_time ON normalized_events(occurred_at DESC,id DESC);
CREATE INDEX normalized_events_request ON normalized_events(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX normalized_events_client_time ON normalized_events(client_ip,occurred_at DESC);
CREATE INDEX normalized_events_source_type ON normalized_events(source,event_type,occurred_at DESC);

-- An identity receipt survives dataset retention and collection-off periods. It also
-- deduplicates copied producer JSONL lines independently of inode/offset.
CREATE TABLE source_event_receipts (
    event_key TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Oversized records are quarantined by byte range/hash only: raw secrets are never copied.
ALTER TABLE log_cursors ADD COLUMN discarding_oversized BOOLEAN NOT NULL DEFAULT false;
CREATE TABLE ingestion_quarantine (
    event_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    file_key TEXT NOT NULL,
    generation BIGINT NOT NULL,
    byte_start BIGINT NOT NULL,
    byte_end BIGINT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Minimal detector state is separate from optional dataset storage. Two source
-- observations with the same trusted request ID count as one authentication attempt.
CREATE TABLE auth_observations (
    observation_key TEXT PRIMARY KEY,
    client_ip INET NOT NULL,
    uri_path TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status_code INTEGER NOT NULL
);
CREATE INDEX auth_observations_window ON auth_observations(client_ip,uri_path,occurred_at DESC);
CREATE TABLE auth_detection_state (
    client_ip INET NOT NULL,
    uri_path TEXT NOT NULL,
    last_alert_at TIMESTAMPTZ,
    PRIMARY KEY(client_ip,uri_path)
);

-- Kernel helper TTL is 300s. Legacy blocks require explicit review, never immortal restore.
ALTER TABLE blocked_ips ADD COLUMN expires_at TIMESTAMPTZ;

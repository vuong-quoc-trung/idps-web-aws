-- Bounded detector state independent of optional normalized event collection.
-- No raw payload, identities or changes to canonical/AI schema.
CREATE TABLE application_observations (
 event_key TEXT PRIMARY KEY,
 source_instance TEXT NOT NULL,
 client_ip INET NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 uri_path TEXT,
 status_code INTEGER,
 outcome TEXT NOT NULL
);
CREATE INDEX application_observations_window ON application_observations(source_instance,client_ip,occurred_at);
CREATE INDEX application_observations_expiry ON application_observations(received_at);

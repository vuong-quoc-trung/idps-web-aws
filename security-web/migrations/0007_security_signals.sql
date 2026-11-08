-- Bounded, pseudonymized observations for server-confirmed security decisions.
CREATE TABLE application_security_observations (
 event_key TEXT PRIMARY KEY,
 source_instance TEXT NOT NULL,
 client_ip INET,
 actor_hmac TEXT,
 occurred_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 signals JSONB NOT NULL,
 status_code INTEGER NOT NULL
);
CREATE INDEX application_security_ip ON application_security_observations(source_instance,client_ip,occurred_at);
CREATE INDEX application_security_actor ON application_security_observations(source_instance,actor_hmac,occurred_at);
CREATE INDEX application_security_expiry ON application_security_observations(received_at);

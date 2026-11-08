CREATE TABLE nginx_behavior_observations (
 event_key TEXT PRIMARY KEY,
 source_instance TEXT NOT NULL,
 client_ip INET,
 occurred_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 burst BOOLEAN NOT NULL,
 rejection BOOLEAN NOT NULL,
 large_response BOOLEAN NOT NULL,
 gateway BOOLEAN NOT NULL,
 response_bytes BIGINT NOT NULL
);
CREATE INDEX nginx_behavior_window ON nginx_behavior_observations(source_instance,occurred_at);
CREATE INDEX nginx_behavior_expiry ON nginx_behavior_observations(received_at);

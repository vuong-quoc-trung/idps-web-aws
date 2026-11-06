-- Correlation evidence and GLU shadow scores never enter enforcement policy.
CREATE TABLE request_correlations (
 request_id TEXT PRIMARY KEY,
 observed_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 result JSONB NOT NULL
);
CREATE INDEX request_correlations_time ON request_correlations(observed_at DESC);
CREATE TABLE glu207_shadow_results (
 request_id TEXT NOT NULL,
 proof_sha256 TEXT NOT NULL,
 result JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(request_id,proof_sha256)
);

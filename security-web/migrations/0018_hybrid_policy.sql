CREATE TABLE hybrid_incidents (
 request_id TEXT PRIMARY KEY,
 evidence_fingerprint TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL,
 decision JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE hybrid_proposals (
 id BIGSERIAL PRIMARY KEY,
 request_id TEXT NOT NULL UNIQUE REFERENCES hybrid_incidents(request_id),
 decision_fingerprint TEXT NOT NULL,
 ip INET NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','STALE','REJECTED')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 approved_by TEXT,
 action_id BIGINT REFERENCES firewall_actions(id)
);
CREATE TABLE hybrid_decision_audit (
 id BIGSERIAL PRIMARY KEY,
 request_id TEXT NOT NULL,
 evidence_fingerprint TEXT NOT NULL,
 decision JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(request_id,evidence_fingerprint)
);

CREATE INDEX hybrid_observed ON hybrid_incidents(observed_at DESC);
CREATE INDEX hybrid_audit_time ON hybrid_decision_audit(created_at);

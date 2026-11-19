CREATE TABLE prevention_ai_keys (
 key_id TEXT PRIMARY KEY, issuer TEXT NOT NULL, epoch TEXT NOT NULL,
 not_before TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 revoked BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE prevention_ai_verdicts (
 id BIGSERIAL PRIMARY KEY, key_id TEXT NOT NULL REFERENCES prevention_ai_keys,
 nonce TEXT NOT NULL, digest TEXT NOT NULL, alert_id BIGINT NOT NULL REFERENCES security_alerts,
 binding JSONB NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 revoked BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(key_id,nonce)
);
CREATE TABLE prevention_execution (
 proposal_id BIGINT PRIMARY KEY REFERENCES prevention_proposals,
 verdict_id BIGINT NOT NULL UNIQUE REFERENCES prevention_ai_verdicts,
 ip INET NOT NULL, deadline TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','ACTIVE','DENIED','ROLLED_BACK','ERROR')),
 attempts INTEGER NOT NULL DEFAULT 0, rollback_requested BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE prevention_execution_audit (
 id BIGSERIAL PRIMARY KEY, proposal_id BIGINT, verdict_id BIGINT,
 decision TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

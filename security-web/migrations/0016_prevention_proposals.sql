-- C2: approval records only. No firewall queue or IP changes.
CREATE TABLE prevention_proposals (
 id BIGSERIAL PRIMARY KEY,
 alert_id BIGINT NOT NULL REFERENCES security_alerts(id),
 creator TEXT NOT NULL,
 idempotency_key TEXT NOT NULL,
 reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 500),
 ttl_seconds INTEGER NOT NULL CHECK(ttl_seconds BETWEEN 1 AND 300),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '5 minutes',
 reviewer TEXT,
 reviewed_at TIMESTAMPTZ,
 status TEXT NOT NULL CHECK(status IN ('PROPOSED','DENIED','REVIEW','APPROVED_DRY_RUN','REJECTED','EXPIRED')),
 evaluation JSONB NOT NULL,
 UNIQUE(creator,idempotency_key)
);
CREATE TABLE prevention_decisions (
 id BIGSERIAL PRIMARY KEY,
 proposal_id BIGINT NOT NULL REFERENCES prevention_proposals(id),
 actor TEXT NOT NULL,
 decision TEXT NOT NULL,
 reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 500),
 evaluation JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

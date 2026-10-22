CREATE TABLE IF NOT EXISTS security_alerts (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL,
    source       VARCHAR(32) NOT NULL,
    event_type   VARCHAR(32) NOT NULL,
    src_ip       INET,
    dest_ip      INET,
    proto        VARCHAR(32),
    rule_name    VARCHAR(160) NOT NULL,
    signature    TEXT,
    category     TEXT,
    severity     SMALLINT NOT NULL CHECK (severity BETWEEN 1 AND 5),
    action       VARCHAR(32) NOT NULL,
    evidence     TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_security_alerts_occurred_at
    ON security_alerts (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_alerts_source
    ON security_alerts (source);
CREATE INDEX IF NOT EXISTS idx_security_alerts_src_ip
    ON security_alerts (src_ip);
CREATE INDEX IF NOT EXISTS idx_security_alerts_rule_name
    ON security_alerts (rule_name);

CREATE TABLE IF NOT EXISTS blocked_ips (
    ip            INET PRIMARY KEY,
    reason        TEXT NOT NULL,
    blocked_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    unblocked_at  TIMESTAMPTZ,
    active        BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_blocked_ips_active
    ON blocked_ips (active);

CREATE TABLE IF NOT EXISTS firewall_actions (
    id          BIGSERIAL PRIMARY KEY,
    ip          INET NOT NULL,
    action      VARCHAR(16) NOT NULL CHECK (action IN ('BLOCK', 'UNBLOCK')),
    source      VARCHAR(32) NOT NULL,
    reason      TEXT NOT NULL,
    status      VARCHAR(16) NOT NULL CHECK (status IN ('SUCCESS', 'ERROR')),
    details     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_firewall_actions_created_at
    ON firewall_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_firewall_actions_ip
    ON firewall_actions (ip);

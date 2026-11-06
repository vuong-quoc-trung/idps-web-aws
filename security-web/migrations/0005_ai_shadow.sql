-- AI scores are observations, never Ground Truth or firewall instructions.
CREATE TABLE ai_shadow_results (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL UNIQUE,
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result JSONB NOT NULL
);
CREATE INDEX ai_shadow_results_time ON ai_shadow_results(observed_at DESC,id DESC);
CREATE TABLE ai_shadow_worker (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    report JSONB NOT NULL
);

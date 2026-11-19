CREATE TABLE https_research_observations (
    request_id text PRIMARY KEY,
    observation jsonb NOT NULL,
    conflicted boolean NOT NULL DEFAULT false,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX https_research_received_at ON https_research_observations(received_at);

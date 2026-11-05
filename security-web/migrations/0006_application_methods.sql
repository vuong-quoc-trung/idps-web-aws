-- HTTP method already exists in canonical Schema v1; retain it in bounded detector state.
-- Old observations have unknown method and cannot satisfy method-based rules.
ALTER TABLE application_observations ADD COLUMN http_method TEXT;

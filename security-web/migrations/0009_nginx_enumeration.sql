-- Only sanitized URI paths, never query strings or request bodies.
ALTER TABLE nginx_behavior_observations ADD COLUMN enumeration_path TEXT;

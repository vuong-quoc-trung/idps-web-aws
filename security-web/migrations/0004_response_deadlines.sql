-- Existing PENDING jobs deliberately retain NULL and cannot be executed as BLOCK.
ALTER TABLE firewall_actions ADD COLUMN expires_at TIMESTAMPTZ;
ALTER TABLE firewall_actions ALTER COLUMN expires_at SET DEFAULT (now() + interval '300 seconds');

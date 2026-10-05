-- Stop backend before applying. Safe to re-run.
BEGIN;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS credential_version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_code_hash VARCHAR(255);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_expires_at TIMESTAMP;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_sent_at TIMESTAMP;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_window_started_at TIMESTAMP;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reset_send_count INTEGER NOT NULL DEFAULT 0;
COMMIT;

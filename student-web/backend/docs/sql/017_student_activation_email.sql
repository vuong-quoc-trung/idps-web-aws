BEGIN;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activation_proof_hash VARCHAR(64);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activation_proof_expires_at TIMESTAMP;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS pending_activation_email VARCHAR(150);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activation_check_window TIMESTAMP;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activation_check_count INTEGER NOT NULL DEFAULT 0;
COMMIT;

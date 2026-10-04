-- Apply after 006, with the backend stopped. Existing program codes stay unchanged.
BEGIN;
ALTER TABLE public.training_programs ADD COLUMN IF NOT EXISTS variant_code VARCHAR(6);
ALTER TABLE public.training_programs DROP CONSTRAINT IF EXISTS ck_training_program_variant;
ALTER TABLE public.training_programs ADD CONSTRAINT ck_training_program_variant
    CHECK (variant_code IS NULL OR variant_code ~ '^[A-Z][A-Z0-9]{0,5}$');
COMMIT;

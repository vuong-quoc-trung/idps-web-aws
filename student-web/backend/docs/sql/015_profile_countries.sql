-- Stop backend and run before deploying profile dropdowns.
-- Existing place names and contact details are not rewritten or discarded.
-- VN is the initial country for legacy rows; review foreign legacy addresses in the form.
BEGIN;
ALTER TABLE public.students ADD COLUMN IF NOT EXISTS birth_country_code VARCHAR(2) NOT NULL DEFAULT 'VN';
ALTER TABLE public.students ADD COLUMN IF NOT EXISTS origin_country_code VARCHAR(2) NOT NULL DEFAULT 'VN';
ALTER TABLE public.students ALTER COLUMN nationality TYPE VARCHAR(150);
ALTER TABLE public.student_addresses ADD COLUMN IF NOT EXISTS country_code VARCHAR(2) NOT NULL DEFAULT 'VN';
COMMIT;

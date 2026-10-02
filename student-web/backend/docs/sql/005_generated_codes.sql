-- PostgreSQL: apply after 001-004, before starting the new backend.
-- Preserves existing entity codes, user logins and all foreign keys.
BEGIN;
ALTER TABLE public.faculties ADD COLUMN IF NOT EXISTS short_code VARCHAR(10);
ALTER TABLE public.majors ADD COLUMN IF NOT EXISTS short_code VARCHAR(10);
CREATE UNIQUE INDEX IF NOT EXISTS ux_faculties_short_code ON public.faculties(short_code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_majors_short_code ON public.majors(short_code);
ALTER TABLE public.classes ALTER COLUMN class_code TYPE VARCHAR(60);
CREATE TABLE IF NOT EXISTS public.code_counters (
    scope VARCHAR(80) PRIMARY KEY,
    last_value BIGINT NOT NULL DEFAULT 0 CHECK (last_value >= 0)
);
COMMIT;
-- Assign short_code explicitly through the faculty/major API (or reviewed SQL).
-- Do not infer majors or programs from legacy class codes.
-- Existing program/class cohorts must be completed before creating students.
-- Do not delete or reset code_counters; gaps after failed requests are normal.

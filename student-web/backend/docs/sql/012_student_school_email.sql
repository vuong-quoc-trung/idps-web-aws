-- Stop the backend and run the entire script before deploying the new NOT NULL entity.
-- Preserve existing nonblank emails and student codes. Only fill missing emails.
-- Does not provision mailboxes. Transactional; safe to run again.
BEGIN;
LOCK TABLE public.students IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.students
        WHERE nullif(btrim(school_email), '') IS NULL
          AND (student_code IS NULL
               OR lower(replace(btrim(student_code), '-', '')) !~ '^[a-z0-9]{1,64}$')
    ) THEN
        RAISE EXCEPTION 'Missing email with invalid legacy student code. Review students before migration.';
    END IF;
    IF EXISTS (
        SELECT candidate FROM (
            SELECT CASE WHEN nullif(btrim(school_email), '') IS NULL
                THEN lower(replace(btrim(student_code), '-', '')) || '@sv.pbl4.edu.vn'
                ELSE school_email END AS candidate
            FROM public.students
        ) proposed GROUP BY candidate HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'School email collision (existing or generated). Review students; no changes applied.';
    END IF;
END $$;
UPDATE public.students
SET school_email = lower(replace(btrim(student_code), '-', '')) || '@sv.pbl4.edu.vn'
WHERE nullif(btrim(school_email), '') IS NULL;
ALTER TABLE public.students ALTER COLUMN school_email SET NOT NULL;
-- Reuse any existing single-column UNIQUE constraint; otherwise add a named one.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attname = 'school_email'
        WHERE c.conrelid = 'public.students'::regclass AND c.contype = 'u'
          AND c.conkey = ARRAY[a.attnum]::smallint[]
    ) THEN
        ALTER TABLE public.students ADD CONSTRAINT uq_students_school_email UNIQUE (school_email);
    END IF;
END $$;
COMMIT;

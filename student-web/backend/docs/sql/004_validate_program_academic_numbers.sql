-- PostgreSQL: run manually after 003. Does not modify existing data.
-- Adding the constraint validates existing rows and rolls back on invalid data.
BEGIN;
LOCK TABLE public.training_programs IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.training_programs'::regclass
                     AND conname = 'ck_training_program_academic_numbers') THEN
        ALTER TABLE public.training_programs
            ADD CONSTRAINT ck_training_program_academic_numbers CHECK (
            (number_of_semesters IS NULL OR number_of_semesters > 0)
            AND (total_credits IS NULL OR total_credits >= 0)
            AND (required_credits IS NULL OR required_credits >= 0)
            AND (elective_credits IS NULL OR elective_credits >= 0)
            AND (total_credits IS NULL OR required_credits IS NULL OR required_credits <= total_credits)
            AND (total_credits IS NULL OR elective_credits IS NULL OR elective_credits <= total_credits)
            AND (total_credits IS NULL OR required_credits IS NULL OR elective_credits IS NULL
                 OR CAST(required_credits AS BIGINT) + CAST(elective_credits AS BIGINT) = total_credits));
    END IF;
END $$;
COMMIT;

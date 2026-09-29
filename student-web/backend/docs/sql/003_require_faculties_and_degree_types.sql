-- PostgreSQL, manual migration, run after 002 and explicit data mapping.
BEGIN;
LOCK TABLE public.faculties, public.majors, public.training_programs IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.majors m LEFT JOIN public.faculties f ON f.id = m.faculty_id
        WHERE f.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Assign every major to an existing faculty before applying this migration.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.training_programs
        WHERE degree_type IS NOT NULL AND degree_type NOT IN ('BACHELOR', 'ENGINEER', 'MASTER')
    ) THEN
        RAISE EXCEPTION 'Review legacy degree_type strings and map them to BACHELOR, ENGINEER or MASTER first.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.training_programs
        WHERE number_of_semesters <= 0 OR total_credits < 0 OR required_credits < 0 OR elective_credits < 0
           OR required_credits > total_credits OR elective_credits > total_credits
           OR (required_credits IS NOT NULL AND elective_credits IS NOT NULL AND total_credits IS NOT NULL
               AND required_credits::BIGINT + elective_credits::BIGINT <> total_credits)
    ) THEN
        RAISE EXCEPTION 'Review invalid semester or credit counts before applying this migration.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.majors'::regclass AND conname = 'fk_majors_faculty') THEN
        ALTER TABLE public.majors ADD CONSTRAINT fk_majors_faculty
            FOREIGN KEY (faculty_id) REFERENCES public.faculties(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.training_programs'::regclass AND conname = 'ck_training_program_degree_type') THEN
        ALTER TABLE public.training_programs ADD CONSTRAINT ck_training_program_degree_type
            CHECK (degree_type IN ('BACHELOR', 'ENGINEER', 'MASTER'));
    END IF;
END $$;
ALTER TABLE public.majors ALTER COLUMN faculty_id SET NOT NULL;
COMMIT;

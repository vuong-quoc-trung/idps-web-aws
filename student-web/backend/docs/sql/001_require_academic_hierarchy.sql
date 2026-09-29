-- PostgreSQL: run manually on the existing student database before starting the new backend.
-- Does not choose a program for any class or overwrite conflicting academic assignments.
-- See ../ACADEMIC_HIERARCHY.md for the preflight queries and repair procedure.
BEGIN;
LOCK TABLE public.majors, public.training_programs, public.classes, public.students
    IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.classes c
        LEFT JOIN public.training_programs p ON p.id = c.program_id
        LEFT JOIN public.majors m ON m.id = p.major_id
        WHERE p.id IS NULL OR m.id IS NULL OR c.major_id IS DISTINCT FROM p.major_id
    ) THEN
        RAISE EXCEPTION 'Classes have missing programs or inconsistent majors. Repair the reported class assignments first.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.students s
        LEFT JOIN public.classes c ON c.id = s.class_id
        WHERE c.id IS NULL OR s.major_id IS DISTINCT FROM c.major_id
           OR (s.training_program_id IS NOT NULL AND s.training_program_id IS DISTINCT FROM c.program_id)
    ) THEN
        RAISE EXCEPTION 'Students have inconsistent class/program/major assignments. Review and repair them before migration.';
    END IF;
END $$;

-- A missing primary program has exactly one valid value: the selected class's program.
UPDATE public.students s
SET training_program_id = c.program_id
FROM public.classes c
WHERE s.class_id = c.id AND s.training_program_id IS NULL;

ALTER TABLE public.classes ALTER COLUMN program_id SET NOT NULL;
ALTER TABLE public.students ALTER COLUMN training_program_id SET NOT NULL;
COMMIT;

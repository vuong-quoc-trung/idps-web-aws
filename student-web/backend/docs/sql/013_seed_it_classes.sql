-- Stop the backend. Requires 005 (counters), 006 (faculties), 007 and 009 (IT programs).
-- Six sample management classes, not course sections. Run the entire transaction.
-- Existing IDs, relationships and active states are preserved; conflicts abort.
BEGIN;
LOCK TABLE public.faculties, public.majors, public.training_programs, public.classes,
    public.code_counters IN SHARE ROW EXCLUSIVE MODE;
DO $$
DECLARE
    item RECORD;
    parent RECORD;
    matches BIGINT;
    target_id BIGINT;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('CLS-IT-2024-01', 'CNTT Đặc thù K2024 - Lớp 01', 'PRG-IT-2024-ENG-DT', 2024, 1),
        ('CLS-IT-2024-02', 'CNTT Nhật K2024 - Lớp 02', 'PRG-IT-2024-ENG-JP', 2024, 2),
        ('CLS-IT-2024-03', 'Khoa học dữ liệu và Trí tuệ nhân tạo K2024 - Lớp 03', 'PRG-IT-2024-ENG-DAI', 2024, 3),
        ('CLS-IT-2025-01', 'CNTT Đặc thù K2025 - Lớp 01', 'PRG-IT-2025-ENG-DT', 2025, 1),
        ('CLS-IT-2025-02', 'CNTT Nhật K2025 - Lớp 02', 'PRG-IT-2025-ENG-JP', 2025, 2),
        ('CLS-IT-2025-03', 'Khoa học dữ liệu và Trí tuệ nhân tạo K2025 - Lớp 03', 'PRG-IT-2025-ENG-DAI', 2025, 3)
    ) AS mapping(class_code, class_name, program_code, cohort, sequence_number)
    LOOP
        SELECT p.id AS program_id, m.id AS major_id INTO parent
        FROM public.training_programs p
        JOIN public.majors m ON m.id = p.major_id
        JOIN public.faculties f ON f.id = m.faculty_id
        WHERE p.program_code = item.program_code AND p.cohort = item.cohort
          AND p.degree_type = 'ENGINEER' AND p.active
          AND m.major_code = 'MAJ-IT' AND m.short_code = 'IT' AND m.active
          AND f.faculty_code = 'FAC-IT' AND f.short_code = 'IT' AND f.active;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Missing or inactive IT program %. Apply 009 and review parent catalog.', item.program_code;
        END IF;
        SELECT count(*), min(id) INTO matches, target_id FROM public.classes
        WHERE class_code = item.class_code
           OR (program_id = parent.program_id AND class_name = item.class_name);
        IF matches > 1 THEN
            RAISE EXCEPTION 'Multiple classes match %. Review manually.', item.class_code;
        ELSIF matches = 1 THEN
            IF NOT EXISTS (SELECT 1 FROM public.classes WHERE id = target_id
                AND class_code = item.class_code AND class_name = item.class_name
                AND program_id = parent.program_id AND major_id = parent.major_id
                AND cohort = item.cohort) THEN
                RAISE EXCEPTION 'Existing class % conflicts with seed. No classes changed.', item.class_code;
            END IF;
        ELSE
            INSERT INTO public.classes(class_code, class_name, major_id, program_id, cohort, active)
            VALUES (item.class_code, item.class_name, parent.major_id, parent.program_id, item.cohort, true);
        END IF;
        -- Never reset a previously allocated counter. API can continue from 04 or higher.
        INSERT INTO public.code_counters(scope, last_value)
        VALUES ('CLS-IT-' || item.cohort || '-', item.sequence_number)
        ON CONFLICT (scope) DO UPDATE
            SET last_value = greatest(public.code_counters.last_value, excluded.last_value);
    END LOOP;
END $$;
COMMIT;

-- Verify the complete parent chain after applying the seed.
SELECT c.class_code, c.class_name, c.cohort, p.program_code, m.major_code, f.faculty_code
FROM public.classes c
JOIN public.training_programs p ON p.id = c.program_id
JOIN public.majors m ON m.id = p.major_id
JOIN public.faculties f ON f.id = m.faculty_id
WHERE c.class_code IN ('CLS-IT-2024-01', 'CLS-IT-2024-02', 'CLS-IT-2024-03',
                       'CLS-IT-2025-01', 'CLS-IT-2025-02', 'CLS-IT-2025-03')
ORDER BY c.class_code;

-- Apply after 007 (006 faculties required). 4 majors; 26 explicit ENGINEER programs.
-- 41 programs await degree confirmation; all 67 rows in ../data/pbl4-transport_energy-programs.json.
-- Repeatable transaction: conflicting catalogs abort without overwriting IDs/FKs/data.
BEGIN;
LOCK TABLE public.faculties, public.majors, public.training_programs IN SHARE ROW EXCLUSIVE MODE;
DO $$
DECLARE
    item RECORD;
    faculty_key BIGINT;
    major_key BIGINT;
    target_key BIGINT;
    matches BIGINT;
    generated_code TEXT;
BEGIN
    SELECT id INTO faculty_key FROM public.faculties
    WHERE faculty_code = 'FAC-TEE' AND short_code = 'TEE' AND faculty_name = 'Khoa Cơ khí Giao thông và Năng lượng' AND active;
    IF faculty_key IS NULL THEN
        RAISE EXCEPTION 'Active FAC-TEE / Khoa Cơ khí Giao thông và Năng lượng is required. Apply 006 and review faculty first.';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('7520103', 'MEC', 'Kỹ thuật cơ khí'),
        ('7520118', 'ISE', 'Kỹ thuật hệ thống công nghiệp'),
        ('7520130', 'AUTO', 'Kỹ thuật ô tô'),
        ('7520122', 'NAV', 'Kỹ thuật tàu thủy')
    ) AS mapping(source_code, short_code, major_name)
    LOOP
        SELECT count(*), min(id) INTO matches, major_key FROM public.majors
        WHERE upper(trim(major_code)) = 'MAJ-' || item.short_code
           OR (faculty_id = faculty_key AND upper(trim(major_code)) = item.source_code)
           OR upper(trim(short_code)) = item.short_code
           OR (faculty_id = faculty_key AND lower(trim(major_name)) = lower(item.major_name));
        IF matches > 1 THEN
            RAISE EXCEPTION 'Multiple majors match %. Review manually.', item.short_code;
        END IF;
        IF matches = 0 THEN
            INSERT INTO public.majors (major_code, short_code, major_name, faculty_id, description, active)
            VALUES ('MAJ-' || item.short_code, item.short_code, item.major_name, faculty_key,
                    'Mã ngành nguồn: ' || item.source_code, true) RETURNING id INTO major_key;
        ELSE
            IF NOT EXISTS (SELECT 1 FROM public.majors WHERE id = major_key
                AND faculty_id = faculty_key AND major_code = 'MAJ-' || item.short_code
                AND short_code = item.short_code AND major_name = item.major_name AND active) THEN
                RAISE EXCEPTION 'Existing major % differs from the proposed mapping. Review manually; no codes/FKs changed.', item.short_code;
            END IF;
        END IF;
    END LOOP;
    FOR item IN SELECT * FROM (VALUES
        ('MEC', 'Cơ khí động lực K2020_ Kỹ sư', 2020, 'ENGINEER', NULL, 10, 180),
        ('MEC', 'Cơ khí động lực K2020CLC_Kỹ sư', 2020, 'ENGINEER', 'CLC', 10, 181),
        ('MEC', 'Cơ khí động lực K2021_ Kỹ sư', 2021, 'ENGINEER', NULL, 10, 180),
        ('MEC', 'Cơ khí động lực K2021CLC_Kỹ sư', 2021, 'ENGINEER', 'CLC', 10, 180),
        ('MEC', 'Cơ khí động lực K2022_Kỹ sư', 2022, 'ENGINEER', NULL, 10, 180),
        ('MEC', 'Cơ khí động lực K2023_Kỹ sư', 2023, 'ENGINEER', NULL, 10, 180),
        ('MEC', 'Cơ khí động lực K2024_Kỹ sư', 2024, 'ENGINEER', NULL, 10, 180),
        ('MEC', 'Cơ khí động lực K2025_Kỹ sư', 2025, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ sư tài năng Kỹ thuật ô tô K2026', 2026, 'ENGINEER', 'TALENT', 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2020_Kỹ sư', 2020, 'ENGINEER', NULL, 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2021_Kỹ sư', 2021, 'ENGINEER', NULL, 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2022_Kỹ sư', 2022, 'ENGINEER', NULL, 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2023_Kỹ sư', 2023, 'ENGINEER', NULL, 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2024_Kỹ sư', 2024, 'ENGINEER', NULL, 10, 180),
        ('ISE', 'Kỹ thuật hệ thống công nghiệp K2025_Kỹ sư', 2025, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ thuật ô tô K2021_Kỹ sư', 2021, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ thuật ô tô K2022_Kỹ sư', 2022, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ thuật ô tô K2023_Kỹ sư', 2023, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ thuật ô tô K2024_Kỹ sư', 2024, 'ENGINEER', NULL, 10, 180),
        ('AUTO', 'Kỹ thuật ô tô K2025_Kỹ sư', 2025, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2020_Kỹ sư', 2020, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2021_Kỹ sư', 2021, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2022_Kỹ sư', 2022, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2023_Kỹ sư', 2023, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2024_Kỹ sư', 2024, 'ENGINEER', NULL, 10, 180),
        ('NAV', 'Kỹ thuật Tàu thủy K2025_Kỹ sư', 2025, 'ENGINEER', NULL, 10, 180)
    ) AS mapping(short_code, program_name, cohort, degree_type, variant_code, semesters, credits)
    LOOP
        SELECT id INTO STRICT major_key FROM public.majors
        WHERE short_code = item.short_code AND faculty_id = faculty_key;
        generated_code := 'PRG-' || item.short_code || '-' || item.cohort || '-ENG'
            || CASE WHEN item.variant_code IS NULL THEN '' ELSE '-' || item.variant_code END;
        SELECT count(*), min(id) INTO matches, target_key FROM public.training_programs
        WHERE program_code = generated_code
           OR (major_id = major_key AND lower(trim(program_name)) = lower(item.program_name));
        IF matches > 1 THEN
            RAISE EXCEPTION 'Multiple programs match %. Review manually.', generated_code;
        END IF;
        IF matches = 0 THEN
            INSERT INTO public.training_programs
                (program_code, program_name, major_id, cohort, degree_type, variant_code,
                 number_of_semesters, total_credits, active)
            VALUES (generated_code, item.program_name, major_key, item.cohort, item.degree_type,
                    item.variant_code, item.semesters, item.credits, true);
        ELSE
            IF NOT EXISTS (SELECT 1 FROM public.training_programs WHERE id = target_key
                AND program_code = generated_code AND program_name = item.program_name
                AND major_id = major_key AND cohort = item.cohort AND degree_type = item.degree_type
                AND variant_code IS NOT DISTINCT FROM item.variant_code
                AND number_of_semesters = item.semesters AND total_credits = item.credits) THEN
                RAISE EXCEPTION 'Existing program % differs from source. Review manually; no record overwritten.', generated_code;
            END IF;
        END IF;
    END LOOP;
END $$;
COMMIT;

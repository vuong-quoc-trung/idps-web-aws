-- Apply after 007 (006 faculties required). 1 majors; 31 explicit ENGINEER programs.
-- 60 programs await degree confirmation; all 91 rows in ../data/pbl4-it-programs.json.
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
    WHERE faculty_code = 'FAC-IT' AND short_code = 'IT' AND faculty_name = 'Khoa Công nghệ Thông tin' AND active;
    IF faculty_key IS NULL THEN
        RAISE EXCEPTION 'Active FAC-IT / Khoa Công nghệ Thông tin is required. Apply 006 and review faculty first.';
    END IF;
    FOR item IN SELECT * FROM (VALUES
        ('7480201', 'IT', 'Công nghệ thông tin')
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
        ('IT', 'Công nghệ Thông tin K2020 Đặc thù _ Kỹ sư _CNPM', 2020, 'ENGINEER', 'DSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020 Đặc thù _ Kỹ sư _HTTT', 2020, 'ENGINEER', 'DIS', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_ATTT', 2020, 'ENGINEER', 'CSEC', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_CNPM', 2020, 'ENGINEER', 'CSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020CLC Đặc thù_Kỹ sư_HTTT', 2020, 'ENGINEER', 'CIS', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020CLC ĐT- KHDL_TTNT _ Kỹ Sư', 2020, 'ENGINEER', 'CDAI', 10, 180),
        ('IT', 'Công nghệ Thông tin K2020CLC Nhật _ Kỹ sư', 2020, 'ENGINEER', 'CLCJP', 10, 180),
        ('IT', 'Công nghệ Thông tin K2021 Đặc thù _ Kỹ sư_CNPM', 2021, 'ENGINEER', 'DSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2021CLC Đặc thù_Kỹ sư_CNPM', 2021, 'ENGINEER', 'CSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2021CLC ĐT- KHDL_TTNT _ Kỹ Sư', 2021, 'ENGINEER', 'CDAI', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư', 2022, 'ENGINEER', 'DT', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_ATTT', 2022, 'ENGINEER', 'DSEC', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_CNPM', 2022, 'ENGINEER', 'DSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_HTTT', 2022, 'ENGINEER', 'DIS', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Đặc thù _ Kỹ sư_KTMT', 2022, 'ENGINEER', 'DCE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 ĐT - KHDL_TTNT _ Kỹ Sư', 2022, 'ENGINEER', 'DDAI', 10, 180),
        ('IT', 'Công nghệ Thông tin K2022 Nhật _ Kỹ sư', 2022, 'ENGINEER', 'JP', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư', 2023, 'ENGINEER', 'DT', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_ATTT', 2023, 'ENGINEER', 'DSEC', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_CNPM', 2023, 'ENGINEER', 'DSE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_HTTT', 2023, 'ENGINEER', 'DIS', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Đặc thù _ Kỹ sư_KTMT', 2023, 'ENGINEER', 'DCE', 10, 180),
        ('IT', 'Công nghệ Thông tin K2023 Nhật _ Kỹ sư', 2023, 'ENGINEER', 'JP', 10, 180),
        ('IT', 'Công nghệ Thông tin K2024 Đặc thù _ Kỹ sư', 2024, 'ENGINEER', 'DT', 10, 180),
        ('IT', 'Công nghệ Thông tin K2024 Nhật _ Kỹ sư', 2024, 'ENGINEER', 'JP', 10, 180),
        ('IT', 'Công nghệ Thông tin K2025 Đặc thù _ Kỹ sư', 2025, 'ENGINEER', 'DT', 10, 180),
        ('IT', 'Công nghệ Thông tin K2025 Nhật _ Kỹ sư', 2025, 'ENGINEER', 'JP', 10, 180),
        ('IT', 'Khoa học dữ liệu và Trí tuệ nhân tạo K2023 _ Kỹ Sư', 2023, 'ENGINEER', 'DAI', 10, 180),
        ('IT', 'Khoa học dữ liệu và Trí tuệ nhân tạo K2024_ Kỹ Sư', 2024, 'ENGINEER', 'DAI', 10, 180),
        ('IT', 'Khoa học dữ liệu và Trí tuệ nhân tạo K2025_ Kỹ Sư', 2025, 'ENGINEER', 'DAI', 10, 180),
        ('IT', 'Kỹ sư tài năng Công nghệ thông tin K2026', 2026, 'ENGINEER', 'TALENT', 9, 150)
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

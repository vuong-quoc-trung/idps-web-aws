-- Apply after 005. Internal PBL4 names/codes, not official institutional codes.
-- No automatic merge/delete of existing faculties; IDs/FKs are preserved.
BEGIN;
LOCK TABLE public.faculties IN SHARE ROW EXCLUSIVE MODE;
DO $$
DECLARE
    item RECORD;
    target_id BIGINT;
    matches BIGINT;
    english_description TEXT;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('Cơ khí', 'Mechanical Engineering', 'ME'),
        ('Công nghệ Thông tin', 'Information Technology', 'IT'),
        ('Cơ khí Giao thông và Năng lượng', 'Transportation and Energy Engineering', 'TEE'),
        ('Cơ khí Giao thông và Năng lượng (N)', 'Transportation and Energy Engineering (N)', 'TEEN'),
        ('Điện', 'Electrical Engineering', 'EE'),
        ('Điện tử và Trí tuệ nhân tạo', 'Electronics and Artificial Intelligence', 'EAI'),
        ('Hóa, Môi trường và Khoa học sự sống', 'Chemical, Environmental and Life Sciences', 'CELS'),
        ('Cơ khí Giao thông và Năng lượng (SK)', 'Transportation and Energy Engineering (SK)', 'TEESK'),
        ('Xây dựng (X3)', 'Civil Engineering (X3)', 'CEX3'),
        ('Xây dựng', 'Civil Engineering', 'CE'),
        ('Xây dựng (X2)', 'Civil Engineering (X2)', 'CEX2'),
        ('Hóa, Môi trường và Khoa học sự sống (MT)', 'Chemical, Environmental and Life Sciences (MT)', 'CELSMT'),
        ('Quản lý dự án và Công nghiệp', 'Project and Industrial Management', 'PIM'),
        ('Kiến trúc', 'Architecture', 'ARCH'),
        ('Điện tử và Trí tuệ nhân tạo (122)', 'Electronics and Artificial Intelligence (122)', 'EAI122'),
        ('Điện tử và Trí tuệ nhân tạo (123)', 'Electronics and Artificial Intelligence (123)', 'EAI123')
    ) AS mapping(vietnamese_name, english_name, short_code)
    LOOP
        -- Names are explicit mappings, never inferred from class/major codes.
        SELECT count(*), min(f.id) INTO matches, target_id
        FROM public.faculties f
        WHERE upper(trim(f.faculty_code)) = 'FAC-' || item.short_code
           OR upper(trim(f.short_code)) = item.short_code
           OR lower(trim(f.faculty_name)) IN (
               lower(item.vietnamese_name), lower('K. ' || item.vietnamese_name),
               lower('Khoa ' || item.vietnamese_name),
               lower('Faculty of ' || item.english_name), lower(item.english_name));
        IF matches > 1 THEN
            RAISE EXCEPTION 'Multiple existing faculties match %. Review IDs manually; no automatic merge.', item.short_code;
        END IF;
        english_description := 'English name: Faculty of ' || item.english_name;
        IF matches = 1 THEN
            IF EXISTS (SELECT 1 FROM public.faculties f WHERE f.id = target_id
                       AND lower(trim(f.faculty_name)) NOT IN (
                           lower(item.vietnamese_name), lower('K. ' || item.vietnamese_name),
                           lower('Khoa ' || item.vietnamese_name),
                           lower('Faculty of ' || item.english_name), lower(item.english_name))) THEN
                RAISE EXCEPTION 'Code % is already assigned to a different faculty (id=%). Review manually.', item.short_code, target_id;
            END IF;
            UPDATE public.faculties f
            SET short_code = item.short_code,
                faculty_code = 'FAC-' || item.short_code,
                faculty_name = 'Khoa ' || item.vietnamese_name,
                description = CASE
                    WHEN position(english_description IN coalesce(f.description, '')) > 0 THEN f.description
                    ELSE concat_ws(E'\n', nullif(f.description, ''), english_description)
                END
            WHERE f.id = target_id;
            -- Preserve active state and existing description, appending English once.
        ELSE
            INSERT INTO public.faculties (short_code, faculty_code, faculty_name, description, active)
            VALUES (item.short_code, 'FAC-' || item.short_code,
                    'Khoa ' || item.vietnamese_name, english_description, true);
        END IF;
    END LOOP;
END $$;
COMMIT;

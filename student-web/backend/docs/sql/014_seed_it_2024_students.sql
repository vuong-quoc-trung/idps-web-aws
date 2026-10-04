-- Requires 005, 006, 007, 009, 012 and 013. Stop backend; run the ENTIRE script.
-- Only names and class assignment are imported. No student self-report fields/grades.
-- Accounts await password setup; no usable default password or activation token is shipped.
-- Admin issues activation tokens through the existing API when ready to onboard students.
BEGIN;
LOCK TABLE public.faculties, public.majors, public.training_programs, public.classes,
    public.students, public.users, public.code_counters IN SHARE ROW EXCLUSIVE MODE;
-- Persistent source mapping prevents duplicates on reruns, even after transfer or activation.
CREATE TABLE IF NOT EXISTS public.student_import_sources (
    source_dataset VARCHAR(80) NOT NULL,
    source_student_code VARCHAR(30) NOT NULL,
    student_id BIGINT NOT NULL REFERENCES public.students(id),
    PRIMARY KEY (source_dataset, source_student_code),
    UNIQUE (source_dataset, student_id)
);
LOCK TABLE public.student_import_sources IN SHARE ROW EXCLUSIVE MODE;
DO $$
DECLARE
    item RECORD;
    parent RECORD;
    student_key BIGINT;
    user_key BIGINT;
    sequence_number BIGINT;
    generated_code TEXT;
    generated_email TEXT;
BEGIN
    SELECT c.id AS class_id, c.major_id, c.program_id INTO parent
    FROM public.classes c
    JOIN public.training_programs p ON p.id = c.program_id AND p.major_id = c.major_id
    JOIN public.majors m ON m.id = p.major_id
    JOIN public.faculties f ON f.id = m.faculty_id
    WHERE c.class_code = 'CLS-IT-2024-01' AND c.cohort = 2024 AND c.active
      AND p.program_code = 'PRG-IT-2024-ENG-DT' AND p.cohort = 2024 AND p.active
      AND m.major_code = 'MAJ-IT' AND m.short_code = 'IT' AND m.active
      AND f.faculty_code = 'FAC-IT' AND f.active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active CNTT Đặc thù K2024 class with matching academic hierarchy is required. Apply 013 first.';
    END IF;
    INSERT INTO public.code_counters(scope, last_value) VALUES ('STU-2024-', 0)
    ON CONFLICT (scope) DO NOTHING;
    FOR item IN SELECT * FROM (VALUES
        ('102240124', 'Trần Hoài An', '$2b$10$Xxyj5JV.CodLAarCmZLpqOsM1dmGgRFLqFIh9gnFO7rWVwZ6cG2sG'),
        ('102240125', 'Lê Thị Ánh', '$2b$10$M85wHqE4zFcAmdK7bd/SsOuh5gOEh.vnGfr8/KUf56WeP7Vg.s.SS'),
        ('102240126', 'Văn Gia Bảo', '$2b$10$luYGWRn0Re5yj0NmncEW..nb.Jp7/hZr.zZb02TwQuR8Oa.3B/YzO'),
        ('102240127', 'Nguyễn Mạnh Cường', '$2b$10$8CFCODZTphpBcTLYYvvgVOC.U6HqzTyr0pjvC.HBH5mrdKEY9IhM.'),
        ('102240128', 'Hoàng Văn Dũng', '$2b$10$PKxfJvzslACil4wa.WIhBeDyYHyBFiIciXoNCHh/ZfQUUEWFaApSi'),
        ('102240129', 'Trần Trung Dũng', '$2b$10$i5DbpqBuPKv6axT1vSiHzuCnYwiAFXf.jMIG/S7z3VncniQNC1NkG'),
        ('102240130', 'Phan Thanh Duy', '$2b$10$SqKnx9XFiPXZpnj0CSU.O.8tVQGtENp/wFuUPalTm6SucXIMsxIwK'),
        ('102240131', 'Nguyễn Hữu Trần Đại', '$2b$10$AjNxZDUzVz4xSpC.eFAsU.yLthjJrBvTjY1VaaFBdsNoOzrfdFZ6y'),
        ('102240132', 'Nguyễn Tiến Đạt', '$2b$10$HaDSe3Hqu46yeIL/wfLTqeHWmgbjuwGY4EZ8snV7lGc7CpbID9trq'),
        ('102240133', 'Nguyễn Bá Giàu', '$2b$10$gejzb/c0fD8gcosZUM3o2OZaJy6IDHicD9wWKHiG9gKvivl2WAyom'),
        ('102240134', 'Lê Thị Hiền', '$2b$10$nJWI4UpYyCRkXhfxBFU1BOneb7/v831Wkgbcjl4KgGs.2Uuplap/a'),
        ('102240135', 'Nguyễn Hoàng Hiếu', '$2b$10$xzzfHrOPnmx4Ggr1vora4.1.eJHCk9yElnG7yR9veSqttXCfIz0gi'),
        ('102240136', 'Nguyễn Tất Hoàng', '$2b$10$Tu609vVvgt41wYPbAnhYjukbnLYORAZCREYCkqOONGZ6ZAuULZ70.'),
        ('102240137', 'Nguyễn Doãn Hùng', '$2b$10$IglgW7S8entmR5XSBgZV5Oy0sQECFH1QQH11guDtBp3uql9Cz3AkO'),
        ('102240139', 'Võ Phi Nhật Huy', '$2b$10$pulOo6hffrH/YK/OPvPaT.uEdM61QkyOggmd4iLBXU/TPPwtBV0FC'),
        ('102240140', 'Phạm Quốc Hưng', '$2b$10$xUpYRPrd0Lx6Xye2oRqIteI8..ee4q/B07pJBRvyYIISx4AZccAw.'),
        ('102240141', 'Đinh Huỳnh Nguyên Khang', '$2b$10$q7kCliYT/gIToraEzk/tYOW1oaZ6I3fc5kNjzCUzgXAZYafMqMkpy'),
        ('102240142', 'Lê Nam Khánh', '$2b$10$K7..F8qCspc5ZEdhhuHObOFliHUXpW9ngPuP.utjGjH0FA2i/9Aci'),
        ('102240143', 'Nguyễn Đăng Khoa', '$2b$10$QZL3eUk7Yo1HtrlIGPjYFeks/MVVnNfRUE1aXuBkeLeZpvONiqzRS'),
        ('102240144', 'Phan Đăng Khôi', '$2b$10$mY1J4M.NJ667hx7vyT8lLeZVVoKIs/0aiY.yFJdFxQ51GOfu1FKqS'),
        ('102240145', 'Trần Kim Lanh', '$2b$10$iNRMpBW2zWbeA8SbYsiOU.D3IubFy8tEhmYV/Og2CM.R9Mz7V3CvC'),
        ('102240146', 'Mai Quang Linh', '$2b$10$ODm7eCZpSQodD8dBvA31b.meiYpCdgoIAoANsIrKZlo.TY42.VtLO'),
        ('102240147', 'Trần Nguyễn Thành Long', '$2b$10$obYRlRvO6OOJFf1uHZ3QMeTClSVxNEoe0dkYA5F6U/iBTDLOCEQqm'),
        ('102240148', 'Trần Tấn Lộc', '$2b$10$Jnm2GPNwsK41jUMX.ADSJegmql8G7vcjEJLkkCTmQQmeNGcLOPsc6'),
        ('102240149', 'Phan Thành Lương', '$2b$10$Ro7cLHdxdrBkR8a5JuiDpuo5978Y5Y3BIxbCy4inphVNBgAarfF/C'),
        ('102240150', 'Phan Xuân Mạnh', '$2b$10$EvSrv1GvYMqkNXLjPR382uP5hg7sDXcaVCAi5w1t3y1tbKW1LNkxq'),
        ('102240151', 'Phạm Thanh Minh', '$2b$10$iSTjJRwakdP5m/YLUHTPc.kCy4Md5URlVuAeVWLHEpxewFW0Ab6PG'),
        ('102240152', 'Huỳnh Hiếu Nghĩa', '$2b$10$CsIAF1KN7elFkIpGNQDc4eMfQKC6yCXkrHORvMcySOkw4zqq7cK9K'),
        ('102240153', 'Hoàng Ngọc Nguyên', '$2b$10$LEMvwntbC0Es6clIAOTC8e2VwztQHdUXzUu0qwwwMabkSzrJoia2O'),
        ('102240154', 'Trần Thị Hạnh Nguyên', '$2b$10$0MsCZM9olBXWz86cNROfyuUOJfp5tUSGgFnFoYbx5QxzB6VWlMNuO'),
        ('102240155', 'Nguyễn Minh Nhật', '$2b$10$1xbBIAaYyenNER6S7LubAulF.aQpJ/4bUbOWCy.nQC7nrp7cZxNli'),
        ('102240156', 'Đinh Khang Ninh', '$2b$10$Uts7f7jXQUYLplRMzhkgreaDdVFd1FCdanNrBlCgmgK5njFxaRNNi'),
        ('102240157', 'Lê Nhật Phong', '$2b$10$lfMVdG4SRmNr9GJHZtEgIO6.TnNxwJOc7BvdDDpiLkIywTdPw7sEm'),
        ('102240158', 'Trần Quang Phước', '$2b$10$SX3y4YAgjxb6mLPnIFGgqufYCA7b3zAwwCys/Vomd7SZKaT2KJ3zS'),
        ('102240159', 'Trần Ngọc Thiện Quang', '$2b$10$r4CxpSQ.QGnb581DOSw.DOTZoe1oF78Tn/csCwVXEq8SJsPw6K1ES'),
        ('102240161', 'Võ Thanh Quân', '$2b$10$edDqQ.RnCXSBOKpscY/8WeAbVcCiz4MNdErlS.7pBtSI731aNlWxG'),
        ('102240162', 'Trần Xuân Quý', '$2b$10$10FC04Ky7YHd00cqChqDyuDKnyk/LYZbBcfWSKlBAOgouM536lwMK'),
        ('102240164', 'Lê Văn Tân', '$2b$10$1WMDyuuKI3GL15PqBHrLMe9SNSB7Rt1krQTNPc9MMD1vi66zVQQfa'),
        ('102240165', 'Nguyễn Văn Thắng', '$2b$10$S32pUAekkBB2RmKEqPg2re47bsV574.UB4RIK/cCgJrgok92vWy0a'),
        ('102240166', 'Phan Gia Thịnh', '$2b$10$TIlxAHpqKoHOn9/6SEHPreV73eb3M7sdGQi6EtmDwoaHN4x9i4ire'),
        ('102240167', 'Lê Viết Thương', '$2b$10$DXc6UDjMuBK2CUwlhklaz.tDptg8GCBGR.6QKRRLqyalDBF9x/GX2'),
        ('102240168', 'Lê Văn Tiến', '$2b$10$f.DKweMDVgmK38F3EZ4nB.LI9AaXUTxEX.yXA59ZdRXUo3MMXugr.'),
        ('102240169', 'Nguyễn Thái Toàn', '$2b$10$RGZq2qmmEjG/mcc7kl.F2./KfzpwduNNiEIaYPj5uPj3AU5ui6E6e'),
        ('102240170', 'Lê Minh Trí', '$2b$10$jNyl.c3KF7B3/BBptKUtBe3C5wqs/QC6mFBbUW5zjYVDI59WonAWS'),
        ('102240171', 'Võ Minh Triết', '$2b$10$FJho9hlyrNqOcXxcWBi5Deab54ecuQv51TLgI21gkEqLCpoK3DG5y'),
        ('102240172', 'Ngô Quốc Hoàng Trung', '$2b$10$duEnT3m5UZJJw9k3bZd1LeyLRKjyBVvmC0MC0R7lqSHuwLfuk.u0a'),
        ('102240173', 'Vương Quốc Trung', '$2b$10$BmELYEP8xD86TS77srmUNODXxJoGqa5.UCrynRDxXxFZefoZRjbyG'),
        ('102240174', 'Bùi Đức Tuấn', '$2b$10$Vvehq8PweJu9lU6tMdYvh.HpizhzoiorqkzzihjJ223g0eZ0W9yjK'),
        ('102240175', 'Hồ Đức Việt', '$2b$10$1Gu6Fl5Bwr1KDJRECQLUwOVXbV4GlgYrBrutJF2yFIRH37FWaJN0K'),
        ('102240176', 'Lê Khắc Việt', '$2b$10$5QBjLhN9GkrQIolKEmCG6.O3o5ej.yNlQ1NHlUjCyKC.YlU9DceoK'),
        ('102240177', 'Trần Lưu Hoàng Vũ', '$2b$10$TuO6ZP27jZx8hCT2JnwVYeRzZnYJBPH6sie.wan6tWgEb0B.Z/IPq'),
        ('102240178', 'Hoàng Như Ý', '$2b$10$0JLd3rcYHBuY1VYATOKEzuGtNIXPoIxfBZ1sM2TcL7bm3Zbh4dK1G')
    ) AS source(source_code, full_name, unusable_password_hash)
    LOOP
        SELECT student_id INTO student_key FROM public.student_import_sources
        WHERE source_dataset = 'pbl4-it-2024-dt3' AND source_student_code = item.source_code;
        IF FOUND THEN
            -- Do not reset passwords, activation, profile, names or class assignments on rerun.
            CONTINUE;
        END IF;
        -- Ambiguous preexisting students must be reviewed, never merged by name automatically.
        IF EXISTS (SELECT 1 FROM public.students WHERE student_code = item.source_code
                   OR (class_id = parent.class_id AND lower(btrim(full_name)) = lower(item.full_name))) THEN
            RAISE EXCEPTION 'Student source % may already exist; review and map explicitly before retrying.', item.source_code;
        END IF;
        LOOP
            UPDATE public.code_counters SET last_value = last_value + 1
            WHERE scope = 'STU-2024-' AND last_value < 999999
            RETURNING last_value INTO sequence_number;
            IF NOT FOUND THEN RAISE EXCEPTION 'Student code sequence exhausted for 2024'; END IF;
            generated_code := 'STU-2024-' || lpad(sequence_number::text, 6, '0');
            generated_email := lower(replace(generated_code, '-', '')) || '@sv.pbl4.edu.vn';
            EXIT WHEN NOT EXISTS (SELECT 1 FROM public.students WHERE student_code = generated_code OR school_email = generated_email)
                AND NOT EXISTS (SELECT 1 FROM public.users WHERE username = generated_code);
        END LOOP;
        INSERT INTO public.users(username, password_hash, role, enabled, password_setup_required, created_at, updated_at)
        VALUES (generated_code, item.unusable_password_hash, 'STUDENT', true, true, LOCALTIMESTAMP, LOCALTIMESTAMP)
        RETURNING id INTO user_key;
        INSERT INTO public.students(student_code, user_id, full_name, major_id, class_id, training_program_id,
            school_email, free_health_insurance, profile_status, status, created_at, updated_at)
        VALUES (generated_code, user_key, item.full_name, parent.major_id, parent.class_id, parent.program_id,
            generated_email, false, 'INCOMPLETE', 'ACTIVE', LOCALTIMESTAMP, LOCALTIMESTAMP)
        RETURNING id INTO student_key;
        INSERT INTO public.student_import_sources(source_dataset, source_student_code, student_id)
        VALUES ('pbl4-it-2024-dt3', item.source_code, student_key);
    END LOOP;
END $$;
COMMIT;

SELECT i.source_student_code, s.id AS student_id, s.full_name, s.student_code, s.school_email,
       c.class_code, u.id AS user_id, u.password_setup_required, s.profile_status
FROM public.student_import_sources i
JOIN public.students s ON s.id = i.student_id
JOIN public.users u ON u.id = s.user_id
JOIN public.classes c ON c.id = s.class_id
WHERE i.source_dataset = 'pbl4-it-2024-dt3'
ORDER BY i.source_student_code;

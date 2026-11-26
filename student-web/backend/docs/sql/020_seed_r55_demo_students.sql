-- Staging demonstration only. Identities are synthetic and accounts are disabled.
-- Run with psql -X -v ON_ERROR_STOP=1 -v demo_password_hash=... -f <file>.
-- Generate the BCrypt value from a discarded random secret on the target.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';
LOCK TABLE public.users, public.students, public.emergency_contacts
    IN SHARE ROW EXCLUSIVE MODE;
SELECT set_config('websentinel.demo_password_hash', :'demo_password_hash', true) IS NOT NULL
    AS demo_hash_available;

CREATE TEMP TABLE r55_import (
    student_id bigint PRIMARY KEY,
    student_code text NOT NULL
) ON COMMIT DROP;

DO $$
DECLARE
    index_no integer;
    code text;
    email text;
    class_key text;
    parent record;
    old record;
    account_id bigint;
    student_key bigint;
    random_hash text := current_setting('websentinel.demo_password_hash');
    prefixes text[] := ARRAY['An', 'Bình', 'Chi', 'Dung', 'Giang', 'Hà', 'Khánh', 'Lan',
                              'Minh', 'Nam', 'Phương', 'Quân', 'Trang'];
    suffixes text[] := ARRAY['Mai', 'Sơn', 'Linh', 'Vân'];
BEGIN
    IF random_hash !~ '^[$]2[aby][$]12[$][./A-Za-z0-9]{53}$' THEN
        RAISE EXCEPTION 'Require a BCrypt cost-12 hash';
    END IF;
    FOR index_no IN 1..52 LOOP
        code := 'DEMO-R55-' || lpad(index_no::text, 3, '0');
        email := lower(code) || '@example.invalid';
        SELECT s.id, s.student_code, s.school_email, u.username, u.role INTO old
        FROM public.students s JOIN public.users u ON u.id = s.user_id
        WHERE s.student_code = code;
        IF FOUND THEN
            IF old.username <> code OR old.school_email <> email OR old.role <> 'STUDENT' THEN
                RAISE EXCEPTION 'Conflicting demo identity %', code;
            END IF;
            CONTINUE;
        END IF;
        IF EXISTS (SELECT 1 FROM public.users WHERE username = code)
           OR EXISTS (SELECT 1 FROM public.students WHERE school_email = email) THEN
            RAISE EXCEPTION 'Conflicting demo key %', code;
        END IF;
        class_key := 'CLS-IT-2024-0' || (1 + (index_no - 1) % 3)::text;
        SELECT c.id, c.major_id, c.program_id INTO STRICT parent
        FROM public.classes c
        JOIN public.training_programs p ON p.id = c.program_id AND p.major_id = c.major_id
        JOIN public.majors m ON m.id = c.major_id
        JOIN public.faculties f ON f.id = m.faculty_id
        WHERE c.class_code = class_key AND c.cohort = 2024 AND p.cohort = c.cohort
          AND m.major_code = 'MAJ-IT' AND f.faculty_code = 'FAC-IT'
          AND c.active AND p.active AND m.active AND f.active;

        INSERT INTO public.users (username, password_hash, role, enabled,
                                  password_setup_required, created_at, updated_at)
        VALUES (code, random_hash, 'STUDENT', false, true, LOCALTIMESTAMP, LOCALTIMESTAMP)
        RETURNING id INTO account_id;
        INSERT INTO public.students (
            student_code, user_id, full_name, date_of_birth, gender, class_id, major_id,
            training_program_id, school_email, personal_email, profile_status, status,
            created_at, updated_at
        ) VALUES (
            code, account_id,
            'Sinh viên mẫu ' || prefixes[1 + (index_no - 1) % 13] || ' ' ||
                suffixes[1 + (index_no - 1) / 13],
            DATE '2006-01-01' + (index_no * 6), CASE WHEN index_no % 2 = 0 THEN 'FEMALE' ELSE 'MALE' END,
            parent.id, parent.major_id, parent.program_id, email, 'contact-' || email,
            'INCOMPLETE', 'ACTIVE', LOCALTIMESTAMP, LOCALTIMESTAMP
        ) RETURNING id INTO student_key;
        INSERT INTO public.emergency_contacts (
            student_id, full_name, phone_number, relationship, priority, created_at, updated_at
        ) VALUES (
            student_key, 'Người liên hệ mẫu ' || index_no, '+120255501' || lpad(index_no::text, 2, '0'),
            'Người giám hộ', 1, LOCALTIMESTAMP, LOCALTIMESTAMP
        );
        INSERT INTO r55_import VALUES (student_key, code);
    END LOOP;
END $$;

SELECT json_build_object('students_added', count(*), 'accounts_added', count(*),
                         'emergency_contacts_added', count(*)) FROM r55_import;
COMMIT;

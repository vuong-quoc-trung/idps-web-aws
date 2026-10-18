-- Stop backend before applying on production (ddl-auto=validate).
BEGIN;
CREATE TABLE IF NOT EXISTS public.admin_creation_lock (id INTEGER PRIMARY KEY);
INSERT INTO public.admin_creation_lock (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
COMMIT;
-- This does not remove existing admins. All application admin-creation paths share this lock.

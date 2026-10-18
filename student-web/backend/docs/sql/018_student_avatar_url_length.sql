-- Allow long direct image links (including signed CDN query parameters).
BEGIN;
ALTER TABLE public.students ALTER COLUMN avatar_url TYPE VARCHAR(4096);
COMMIT;

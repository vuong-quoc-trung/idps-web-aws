-- Preserve deployed V1; add correlation without changing existing audit rows.
ALTER TABLE public.access_logs ADD COLUMN IF NOT EXISTS request_id varchar(128);
CREATE INDEX IF NOT EXISTS idx_access_logs_request_id ON public.access_logs (request_id);
